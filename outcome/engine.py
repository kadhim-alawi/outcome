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

from typing import Any, Callable

from . import approval as approval_mod
from .calle import CalleTransport, CallRequest
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
    ) -> None:
        self.transport = transport
        self.planner = planner or FrontierPlanner()
        self.on_event = on_event or (lambda event: None)

    # -- public API ------------------------------------------------------

    def run(self, outcome: Outcome) -> Outcome:
        """Advance the outcome as far as it can go without a human.

        Returns when the goal is resolved, abandoned, or blocked on approval.
        Safe to call again after an approval decision.
        """
        if outcome.status is OutcomeStatus.DRAFT:
            outcome.status = OutcomeStatus.WORKING
            self._emit(outcome, "started", {"goal": outcome.goal})

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
            metadata={
                "workflow": "outcome",
                "outcome_id": outcome.id,
                "action_id": action.id,
                "objective": action.purpose[:200],
            },
        )
        call = self.transport.place(request)
        evidence = extract(action, call)
        action.status = ActionStatus.DONE if call.succeeded else ActionStatus.FAILED
        outcome.record(evidence)
        # Evidence first, then the leads it produced. A referral emitted before
        # the call it came out of reads, on the timeline, as though the agent
        # already knew where to go next.
        self._emit(outcome, "evidence", self._evidence_event(outcome, action, evidence))
        self._absorb_referrals(outcome, evidence)
        return True

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
        self.on_event({"at": utc_now(), "outcome_id": outcome.id, "kind": kind, **data})
