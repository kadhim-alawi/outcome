"""The loop that owns the goal.

    plan -> (approve?) -> call -> read as evidence -> check constraints -> plan

Everything the engine does is appended to the outcome and emitted as an event,
so the timeline the user watches and the record the user keeps are the same
object. There is no separate log.

Two properties matter more than the loop itself:

* it stops. The call budget is checked before every dial, not after, and the
  planner's own abandon decision is honoured rather than retried.
* it never commits without being told to. A call flagged as committing parks
  the whole run in `awaiting_approval` and returns; the engine does not hold a
  thread or a timer waiting for an answer, because the answer may take a day.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from . import approval as approval_mod
from .calle import (
    CalleCreateError,
    CalleError,
    CalleTransport,
    CallOutcome,
    CallRequest,
)
from .constraints import best_acceptable, evaluate
from .evidence import extract
from .models import (
    Action,
    ActionStatus,
    ActionType,
    CallVerdict,
    Evidence,
    Organization,
    Outcome,
    OutcomeStatus,
    mask_phone,
    utc_now,
)
from .planner import FrontierPlanner, Planner

if TYPE_CHECKING:  # pragma: no cover - import cycle: store imports calle types
    from .store import Store

EventSink = Callable[[dict[str, Any]], None]


def _same_offer(a, b) -> bool:
    """Two offers are the same deal even with different ids.

    The confirming call re-states the terms and so produces a second `Offer`
    object for the deal that was already on the table. Comparing ids would list
    the winning option in the report's "also considered" section, which reads
    as though the agent turned down the thing it accepted.
    """
    return (a.org_id, a.summary, a.price, a.eta) == (b.org_id, b.summary, b.price, b.eta)


class Engine:
    def __init__(
        self,
        transport: CalleTransport,
        planner: Planner | None = None,
        on_event: EventSink | None = None,
        store: "Store | None" = None,
    ) -> None:
        self.transport = transport
        self.planner = planner or FrontierPlanner()
        self.on_event = on_event or (lambda event: None)
        # Optional. Without it the engine is a pure value-transformer and a
        # crash loses the run; with it, every event is durable and no number is
        # dialled twice across a restart.
        self.store = store

    # -- public API ------------------------------------------------------

    def run(self, outcome: Outcome) -> Outcome:
        """Advance the outcome as far as it can go without a human.

        Returns when the goal is resolved, abandoned, or blocked on approval.
        Safe to call again after an approval decision.
        """
        if outcome.status is OutcomeStatus.DRAFT:
            outcome.status = OutcomeStatus.WORKING
            self._emit(outcome, "started", {"goal": outcome.goal})
        elif outcome.status is OutcomeStatus.AWAITING_WINDOW:
            outcome.status = OutcomeStatus.WORKING

        while not outcome.is_terminal():
            action = self._next_action(outcome)
            if action is None:
                break  # parked on approval
            if action.type is ActionType.COMPLETE:
                self._resolve(outcome, action)
                break
            if action.type is ActionType.ABANDON:
                self._abandon(outcome, action)
                break
            if action.type is ActionType.CALL:
                if not self._execute_call(outcome, action):
                    break  # parked on approval
                continue
            # An action type the engine does not execute (ASK_USER, VERIFY as a
            # standalone step) parks the run rather than silently dropping it.
            outcome.status = OutcomeStatus.AWAITING_USER
            self._emit(outcome, "awaiting_user", {"action_id": action.id, "purpose": action.purpose})
            break

        return outcome

    def approve(self, outcome: Outcome, action_id: str) -> Outcome:
        action = outcome.action(action_id)
        if action is None or action.status is not ActionStatus.AWAITING_APPROVAL:
            raise ValueError(f"No action awaiting approval with id {action_id!r}.")
        # The status stays AWAITING_APPROVAL so `_next_action` picks this exact
        # action back up. Clearing it here would send the planner round again,
        # and it would propose the same commitment as a fresh, unapproved action.
        action.approved = True
        outcome.status = OutcomeStatus.WORKING
        self._emit(outcome, "approved", {"action_id": action.id, "purpose": action.purpose})
        return self.run(outcome)

    def reject(self, outcome: Outcome, action_id: str, reason: str = "") -> Outcome:
        """Decline a proposed commitment and send the agent back out.

        The offer is recorded as declined so the planner cannot immediately
        propose it again, which would turn "no" into a loop.
        """
        action = outcome.action(action_id)
        if action is None or action.status is not ActionStatus.AWAITING_APPROVAL:
            raise ValueError(f"No action awaiting approval with id {action_id!r}.")
        action.status = ActionStatus.REJECTED
        outcome.pending_approval_action_id = None
        outcome.status = OutcomeStatus.WORKING

        best, _ = best_acceptable(outcome.open_offers(), outcome.constraints)
        if best is not None:
            outcome.declined_offer_ids.append(best.offer.id)
        self._emit(
            outcome,
            "rejected",
            {"action_id": action.id, "reason": reason or "Declined by the user."},
        )
        return self.run(outcome)

    # -- internals -------------------------------------------------------

    def _next_action(self, outcome: Outcome) -> Action | None:
        pending = outcome.pending_approval()
        if pending is not None:
            if not pending.approved:
                return None
            pending.status = ActionStatus.PLANNED
            outcome.pending_approval_action_id = None
            return pending
        # Two states mean "this action was chosen and never finished":
        #
        #   PLANNED - parked before dialling, because the calling window shut.
        #   RUNNING - interrupted during the dial. Only ever seen after a crash,
        #             because nothing else leaves an action in it.
        #
        # Both resume the same action rather than planning a fresh one.
        # Re-planning would append a duplicate; for an approved commit action it
        # would throw away the approval and ask the user again; and for a RUNNING
        # action it would mint a new action id, which changes the idempotency key
        # and walks straight past the ledger entry for the call that may already
        # have happened.
        resumable = next(
            (
                a
                for a in outcome.actions
                if a.status in (ActionStatus.PLANNED, ActionStatus.RUNNING)
            ),
            None,
        )
        if resumable is not None:
            return resumable
        action = self.planner.next_action(outcome)
        outcome.actions.append(action)
        outcome.updated_at = utc_now()
        self._emit(
            outcome,
            "planned",
            {
                "action_id": action.id,
                "type": action.type.value,
                "purpose": action.purpose,
                "target": self._org_label(outcome, action),
                "commits_user": action.commits_user,
            },
        )
        return action

    def _execute_call(self, outcome: Outcome, action: Action) -> bool:
        """Place one call. Returns False if the run parked on approval."""
        org = outcome.org(action.target_org_id)
        if org is None:
            action.status = ActionStatus.FAILED
            self._emit(outcome, "error", {"action_id": action.id, "detail": "Unknown target."})
            outcome.status = OutcomeStatus.FAILED
            return False

        if not action.approved:
            decision = approval_mod.classify(action)
            if decision.required:
                self._park_for_approval(outcome, action, org, decision.reason)
                return False

        # Budget is checked immediately before dialling, so an approval that sat
        # overnight cannot spend a credit the budget no longer has.
        if outcome.calls_placed() >= outcome.budget.max_calls:
            action.status = ActionStatus.REJECTED
            self._abandon(
                outcome,
                Action(
                    type=ActionType.ABANDON,
                    purpose=(
                        f"Call budget reached ({outcome.budget.max_calls} calls) before this "
                        "call could be placed."
                    ),
                ),
            )
            return False

        # Unknown transports default to enforcing: a guard that fails open is
        # not a guard.
        dials = getattr(self.transport, "places_real_calls", True)
        window = outcome.call_window
        if dials and window is not None and not window.is_open():
            # Parked, not abandoned. The action stays PLANNED so the next run()
            # picks up this one, with its approval if it had one.
            outcome.status = OutcomeStatus.AWAITING_WINDOW
            self._emit(
                outcome,
                "awaiting_window",
                {
                    "action_id": action.id,
                    "org": org.name,
                    "detail": window.explain_closed(),
                    "window": window.describe(),
                    "opens_at": window.next_open().isoformat(timespec="minutes"),
                },
            )
            return False

        action.status = ActionStatus.RUNNING
        self._emit(
            outcome,
            "calling",
            {
                "action_id": action.id,
                "org": org.name,
                "phone": mask_phone(org.phone),
                "attempt": action.attempt,
                "purpose": action.purpose,
                "commits_user": action.commits_user,
            },
        )

        request = CallRequest(
            phone=org.phone,
            task=action.task_prompt,
            result_schema=action.result_schema,
            locale=org.locale,
            region=org.region,
            metadata={
                "workflow": "outcome",
                "outcome_id": outcome.id,
                "action_id": action.id,
                "objective": action.purpose[:200],
            },
        )
        call = self._place(outcome, action, request)
        if call is None:
            return False
        evidence = extract(action, call)
        action.status = ActionStatus.DONE if call.succeeded else ActionStatus.FAILED
        outcome.record(evidence)
        # Evidence first, then the leads it produced. A referral emitted before
        # the call it came out of reads, on the timeline, as though the agent
        # already knew where to go next.
        self._emit(outcome, "evidence", self._evidence_event(outcome, action, evidence))
        self._absorb_referrals(outcome, evidence)
        return True

    def _place(
        self, outcome: Outcome, action: Action, request: CallRequest
    ) -> CallOutcome | None:
        """Dial, consulting the ledger first. Returns None if the run parked.

        Without a store this is just `transport.place`. With one, the sequence is
        claim, dial, complete — in that order, because a crash while the phone is
        ringing has to leave evidence that it might have rung.
        """
        if self.store is None:
            return self.transport.place(request)

        key = request.idempotency_key()
        prior = self.store.find_call(key)
        if prior is None:
            # Validate before claiming. A refusal here (bad number, not on the
            # allowlist) means nothing was dialled, and a claim left behind for
            # it would block this action forever.
            check = getattr(self.transport, "assert_dialable", None)
            if check is not None:
                check(request.phone)
            if not self.store.claim_call(key, outcome.id, action.id, request.phone):
                prior = self.store.find_call(key)  # lost a race; fall through

        if prior is not None:
            if prior.finished:
                self._emit(
                    outcome,
                    "replayed",
                    {
                        "action_id": action.id,
                        "call_id": prior.call_id,
                        "detail": "This call was already placed. Replaying its stored "
                        "result rather than dialling again.",
                    },
                )
                return prior.replay()
            # The action stays RUNNING. It has not failed — it is unresolved,
            # and the difference decides whether clearing the ledger entry can
            # ever help: a FAILED action is not resumable, so the operator's
            # `--resolve` would land on a run that has already moved past it and
            # the paid-for call would be thrown away.
            outcome.status = OutcomeStatus.AWAITING_USER
            self._emit(
                outcome,
                "unresolved_call",
                {
                    "action_id": action.id,
                    "claimed_at": prior.claimed_at,
                    "phone": mask_phone(prior.phone),
                    "detail": (
                        "A call to this number was started and never recorded a result, "
                        "so it may have connected. Refusing to dial again. Check whether "
                        "it happened, then clear it with: outcome calls --resolve "
                        f"{prior.idempotency_key}"
                    ),
                },
            )
            return None

        try:
            call = self.transport.place(request)
        except CalleCreateError as exc:
            # CALL-E never accepted the request, so nothing rang. Release the
            # claim: leaving it would strand the action behind a ledger entry
            # for a call that does not exist, and make the operator clear a
            # phantom. The action is REJECTED rather than FAILED so it does not
            # count against a call budget it never spent.
            self.store.forget_call(key)
            action.status = ActionStatus.REJECTED
            outcome.status = OutcomeStatus.AWAITING_USER
            self._emit(
                outcome,
                "error",
                {
                    "action_id": action.id,
                    "phone": mask_phone(request.phone),
                    "detail": f"CALL-E refused the request, so no call was placed. {exc}",
                },
            )
            return None
        except CalleError as exc:
            # The claim stays, and so does RUNNING. A call exists and we could
            # not learn how it ended; the safe reading of "do not know" is
            # "assume it rang" — but the action must stay resumable so that
            # clearing the ledger entry can put the run back on its feet.
            call_id = getattr(exc, "call_id", None)
            outcome.status = OutcomeStatus.AWAITING_USER
            self._emit(
                outcome,
                "unresolved_call",
                {
                    "action_id": action.id,
                    "phone": mask_phone(request.phone),
                    "call_id": call_id,
                    "detail": (
                        f"The call was created but its outcome is unknown: {exc} "
                        "Refusing to retry it automatically. Clear it with: "
                        f"outcome calls --resolve {key}"
                    ),
                },
            )
            return None
        self.store.complete_call(key, call)
        return call

    def _park_for_approval(
        self, outcome: Outcome, action: Action, org: Organization, reason: str
    ) -> None:
        action.status = ActionStatus.AWAITING_APPROVAL
        outcome.pending_approval_action_id = action.id
        outcome.status = OutcomeStatus.AWAITING_APPROVAL

        best, all_evals = best_acceptable(outcome.open_offers(), outcome.constraints)
        request = approval_mod.ApprovalRequest(
            action=action,
            organization=org,
            offer=best.offer if best else None,
            evaluation=best,
            rejected=[e for e in all_evals if not e.acceptable],
            reason=reason,
        )
        self._emit(outcome, "approval_required", request.to_dict())

    def _absorb_referrals(self, outcome: Outcome, evidence: Evidence) -> None:
        """Grow the frontier from what the call just told us.

        This is the line that makes OUTCOME an agent rather than a dialler: the
        set of people worth calling is not fixed when the run starts.
        """
        for referral in evidence.referrals:
            before = len(outcome.organizations)
            org = outcome.add_organization(
                Organization(
                    name=referral.org_name,
                    phone=referral.phone,
                    role=referral.role or referral.reason,
                    discovered_by=evidence.action_id,
                )
            )
            if len(outcome.organizations) > before:
                self._emit(
                    outcome,
                    "lead_discovered",
                    {
                        "org": org.name,
                        "phone": mask_phone(org.phone),
                        "reason": referral.reason,
                        "from_action": evidence.action_id,
                    },
                )

    def _evidence_event(
        self, outcome: Outcome, action: Action, evidence: Evidence
    ) -> dict[str, Any]:
        event = {
            "action_id": action.id,
            "org": self._org_label(outcome, action),
            "verdict": evidence.verdict.value,
            "facts": evidence.facts,
            "blockers": evidence.blockers,
            "call_id": evidence.call_id,
        }
        if evidence.offer is not None:
            ev = evaluate(evidence.offer, outcome.constraints)
            event["offer"] = evidence.offer.to_dict()
            event["acceptable"] = ev.acceptable
            event["constraint_report"] = [r.to_dict() for r in ev.results]
        return event

    def _org_label(self, outcome: Outcome, action: Action) -> str | None:
        org = outcome.org(action.target_org_id)
        return org.name if org else None

    # -- terminal states -------------------------------------------------

    def _resolve(self, outcome: Outcome, action: Action) -> None:
        action.status = ActionStatus.DONE
        confirmation = next(
            (e for e in reversed(outcome.evidence) if e.verdict is CallVerdict.CONFIRMED), None
        )
        offer = confirmation.offer if confirmation else None
        if offer is None and confirmation is not None:
            offer = next(
                (o for o in outcome.offers() if o.org_id == confirmation.org_id), None
            )
        org = outcome.org(offer.org_id) if offer else None
        evaluation = evaluate(offer, outcome.constraints) if offer else None

        outcome.status = OutcomeStatus.RESOLVED
        outcome.resolution = {
            "status": "resolved",
            "headline": self._headline(offer, org),
            "offer": offer.to_dict() if offer else None,
            "party": org.name if org else None,
            "reference": offer.reference if offer else None,
            "constraint_report": (
                [r.to_dict() for r in evaluation.results] if evaluation else []
            ),
            "calls_placed": outcome.calls_placed(),
            "call_budget": outcome.budget.max_calls,
            "parties": self._party_report(outcome),
            "considered": [
                evaluate(o, outcome.constraints).to_dict()
                for o in outcome.offers()
                if offer is None or not _same_offer(o, offer)
            ],
            "resolved_at": utc_now(),
        }
        self._emit(outcome, "resolved", outcome.resolution)

    def _abandon(self, outcome: Outcome, action: Action) -> None:
        if action not in outcome.actions:
            outcome.actions.append(action)
        action.status = ActionStatus.DONE
        outcome.status = OutcomeStatus.ABANDONED
        outcome.resolution = {
            "status": "abandoned",
            "headline": "Not resolved. Here is everything that was established.",
            "why": action.purpose,
            "calls_placed": outcome.calls_placed(),
            "call_budget": outcome.budget.max_calls,
            "parties": self._party_report(outcome),
            "considered": [
                evaluate(o, outcome.constraints).to_dict() for o in outcome.offers()
            ],
            "blockers": sorted({b for e in outcome.evidence for b in e.blockers}),
            "resolved_at": utc_now(),
        }
        self._emit(outcome, "abandoned", outcome.resolution)

    def _headline(self, offer, org) -> str:
        if offer is None:
            return "Resolved."
        price = (
            f" for {offer.currency} {offer.price:.2f}" if offer.price is not None else ""
        )
        when = f", {offer.eta}" if offer.eta else ""
        where = f" with {org.name}" if org else ""
        return f"{offer.summary}{where}{price}{when}."

    def _party_report(self, outcome: Outcome) -> list[dict[str, Any]]:
        report = []
        for org in outcome.organizations:
            calls = outcome.calls_to_org(org.id)
            last = next((e for e in reversed(outcome.evidence) if e.org_id == org.id), None)
            report.append(
                {
                    "name": org.name,
                    "phone": mask_phone(org.phone),
                    "role": org.role,
                    "discovered": bool(org.discovered_by),
                    "calls": calls,
                    "verdict": last.verdict.value if last else "not_called",
                    "facts": last.facts if last else [],
                }
            )
        return report

    def _emit(self, outcome: Outcome, kind: str, data: dict[str, Any]) -> None:
        event = {"at": utc_now(), "outcome_id": outcome.id, "kind": kind, **data}
        if self.store is not None:
            # Persist before handing the event out, so what a caller has seen is
            # never more than what survived a crash.
            self.store.append_events(outcome.id, [event])
            self.store.save(outcome)
        self.on_event(event)
