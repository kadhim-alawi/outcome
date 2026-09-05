"""Deciding what to do next.

The planner never talks to CALL-E and never mutates the outcome. It reads the
evidence log and returns one `Action`. That separation is what lets the same
planner drive a mock run in a unit test and a live run on real phone numbers,
and it is what makes the agent's behaviour reviewable: every decision is a pure
function of what has been established so far.

`FrontierPlanner` is deterministic and is the default. The frontier is the set
of organisations that are worth calling — the ones the user supplied, plus the
ones earlier calls pointed us to — and planning is choosing from it under the
call budget. There is an LLM planner in `llm.py` for goal interpretation and
script wording, but the control flow deliberately stays here, in code you can
read, because this is the loop that spends the user's money and the user's
credits.
"""

from __future__ import annotations

from typing import Protocol

from .calle import EVIDENCE_SCHEMA
from .constraints import Evaluation, best_acceptable
from .models import (
    Action,
    ActionStatus,
    ActionType,
    CallVerdict,
    Constraint,
    ConstraintKind,
    Offer,
    Outcome,
    Organization,
)

DISCLOSURE = (
    "You are an AI assistant placing this call on behalf of a customer. "
    "Say so clearly at the start of the conversation, before asking anything. "
    "If the person asks to speak to a human, or asks you to stop, apologise, "
    "end the call politely, and record that in your result."
)

BASE_RULES = (
    "Rules for this call:\n"
    "- Be brief and polite. You are asking for help, not conducting an interview.\n"
    "- Record only what the person actually said. Never fill a field with a guess.\n"
    "- If they cannot help, ask who can, and ask for that number. Record it as a referral.\n"
    "- Do not read out payment card details, passwords, or any credential.\n"
    "- Do not give medical, legal or financial advice.\n"
)

NO_COMMIT_RULE = (
    "- You are NOT authorised to agree to anything, accept any price, place any order, "
    "or cancel anything on this call. If they offer something, record it as an offer and "
    "say you will confirm shortly. Saying yes is not your decision to make.\n"
)


class Planner(Protocol):
    def next_action(self, outcome: Outcome) -> Action: ...


def describe_constraints(constraints: list[Constraint]) -> str:
    if not constraints:
        return "No constraints were set."
    lines = []
    for c in constraints:
        marker = "must" if c.hard else "prefer"
        detail = f" ({c.value})" if c.value not in (None, "") else ""
        lines.append(f"- {marker}: {c.description}{detail}")
    return "\n".join(lines)


def build_gathering_task(outcome: Outcome, org: Organization, objective: str) -> str:
    """The script for a call that is allowed to ask but not to agree."""
    referral_note = ""
    if org.discovered_by:
        prior = outcome.evidence_for(org.discovered_by)
        if prior:
            source = outcome.org(prior.org_id)
            if source:
                referral_note = (
                    f"\nYou were given this number by {source.name}. "
                    "It is reasonable to mention that.\n"
                )
    return (
        f"{DISCLOSURE}\n\n"
        f"You are calling {org.name}"
        + (f" ({org.role})" if org.role else "")
        + ".\n\n"
        f"What the customer needs overall: {outcome.goal}\n\n"
        f"Their requirements:\n{describe_constraints(outcome.constraints)}\n"
        f"{referral_note}\n"
        f"Your objective on THIS call: {objective}\n\n"
        f"{BASE_RULES}{NO_COMMIT_RULE}"
        "\nFill in the result schema before you hang up. If nobody can help you, "
        "set verdict to 'blocked' and record why."
    )


def build_commit_task(outcome: Outcome, org: Organization, offer: Offer) -> str:
    """The script for the one call that is allowed to say yes.

    The authorisation is written as an explicit envelope — this thing, at this
    price, on this date — because the user approved that specific offer and not
    a renegotiated version of it. If the terms have moved by the time the call
    connects, the caller is told to walk away rather than to use its judgement.
    """
    price = (
        f"{offer.currency} {offer.price:.2f}" if offer.price is not None else "the quoted amount"
    )
    eta = f" for delivery on {offer.eta}" if offer.eta else ""
    return (
        f"{DISCLOSURE}\n\n"
        f"You are calling {org.name} back to confirm something the customer has approved.\n\n"
        f"What the customer needs overall: {outcome.goal}\n\n"
        f"YOU ARE AUTHORISED TO ACCEPT EXACTLY THIS AND NOTHING ELSE:\n"
        f"  {offer.summary}\n"
        f"  Price: {price}\n"
        f"  Delivery: {offer.eta or 'as previously discussed'}\n\n"
        "If the terms have changed in any way — a different price, a later date, an added "
        "fee, a different item — do NOT accept. Record the new terms as an offer, set "
        "verdict to 'offer', and end the call politely. The customer will decide again.\n\n"
        f"If the terms are unchanged, accept{eta}, and ask for a reference or order number. "
        "Record it in the offer's reference field, and set verdict to 'confirmed'.\n\n"
        f"{BASE_RULES}"
    )


class FrontierPlanner:
    """Deterministic frontier search over the organisations worth calling.

    Priority order, highest first:

    1. An acceptable offer exists and has not been locked in -> call back and
       accept it. Finding a good answer and failing to secure it is the one
       outcome worse than not finding one.
    2. Somebody we have never called -> call them. User-supplied parties come
       before discovered ones only because they were added first; a referral
       from a call that just happened is usually the warmer lead, and it lands
       ahead of any party the user listed but we have not reached yet.
    3. Somebody who did not pick up, under the per-party retry cap -> try again.
    4. Nothing left -> abandon, and report what was learned.
    """

    def __init__(self, shop_all_leads: bool = False) -> None:
        # False means "stop at the first offer that satisfies every hard
        # constraint" rather than canvassing every lead for a better one. With
        # a 20-call account, exhaustive search is not a neutral default.
        self.shop_all_leads = shop_all_leads

    # -- helpers ---------------------------------------------------------

    def _confirmed_offer(self, outcome: Outcome) -> Offer | None:
        for ev in outcome.evidence:
            if ev.verdict is not CallVerdict.CONFIRMED:
                continue
            action = outcome.action(ev.action_id)
            if action and action.commits_user:
                return ev.offer or self._offer_for_org(outcome, ev.org_id)
        return None

    def _offer_for_org(self, outcome: Outcome, org_id: str | None) -> Offer | None:
        if not org_id:
            return None
        return next((o for o in outcome.open_offers() if o.org_id == org_id), None)

    def _uncalled(self, outcome: Outcome) -> list[Organization]:
        return [o for o in outcome.organizations if outcome.calls_to_org(o.id) == 0]

    def _retryable(self, outcome: Outcome) -> list[Organization]:
        out = []
        for org in outcome.organizations:
            attempts = outcome.calls_to_org(org.id)
            if attempts == 0 or attempts >= outcome.budget.max_calls_per_org:
                continue
            last = self._last_evidence_for_org(outcome, org.id)
            if last and last.verdict is CallVerdict.NO_ANSWER:
                out.append(org)
        return out

    def _last_evidence_for_org(self, outcome: Outcome, org_id: str):
        found = [e for e in outcome.evidence if e.org_id == org_id]
        return found[-1] if found else None

    def _budget_exhausted(self, outcome: Outcome) -> bool:
        return (
            outcome.calls_placed() >= outcome.budget.max_calls
            or len(outcome.actions) >= outcome.budget.max_actions
        )

    def _objective_for(self, outcome: Outcome, org: Organization) -> str:
        """What this particular call is for.

        A first call to a party we were referred to already knows why we are
        ringing, so it asks the narrower question. A cold call has to establish
        the situation first.
        """
        goal = outcome.goal.rstrip(".")
        ceiling = next(
            (c for c in outcome.constraints if c.kind is ConstraintKind.BUDGET), None
        )
        floor = next(
            (c for c in outcome.constraints if c.kind is ConstraintKind.MINIMUM), None
        )
        deadline = next(
            (c for c in outcome.constraints if c.kind is ConstraintKind.DEADLINE), None
        )
        bounds = []
        if deadline and deadline.value:
            bounds.append(f"by {deadline.value}")
        if ceiling and ceiling.value is not None:
            bounds.append(f"for no more than {ceiling.value}")
        # The floor has to reach the caller too. A caller that does not know the
        # customer needs at least 62.50 back will hear "we can do 40" as good news
        # and stop pushing.
        if floor and floor.value is not None:
            bounds.append(f"for at least {floor.value}")
        bound_text = (" " + " and ".join(bounds)) if bounds else ""
        if org.discovered_by:
            return (
                f"Find out whether they can do this{bound_text}: {goal}. "
                "Get a price and a date if they can."
            )
        return (
            f"Establish whether they can resolve this{bound_text}: {goal}. "
            "If they cannot, find out exactly why, and who else could."
        )

    # -- the decision ----------------------------------------------------

    def next_action(self, outcome: Outcome) -> Action:
        if self._confirmed_offer(outcome) is not None:
            return Action(
                type=ActionType.COMPLETE,
                purpose="An acceptable option has been confirmed by the other party.",
            )

        best, _all = best_acceptable(outcome.open_offers(), outcome.constraints)
        uncalled = self._uncalled(outcome)

        if best is not None and (not self.shop_all_leads or not uncalled):
            org = outcome.org(best.offer.org_id)
            if org is not None and outcome.calls_to_org(org.id) < outcome.budget.max_calls_per_org:
                return self._commit_action(outcome, org, best)

        if self._budget_exhausted(outcome):
            return Action(
                type=ActionType.ABANDON,
                purpose=(
                    f"Call budget reached ({outcome.calls_placed()} of "
                    f"{outcome.budget.max_calls} calls). Stopping rather than dialling on."
                ),
            )

        if uncalled:
            return self._gathering_action(outcome, uncalled[0])

        retryable = self._retryable(outcome)
        if retryable:
            org = retryable[0]
            action = self._gathering_action(outcome, org)
            action.attempt = outcome.calls_to_org(org.id) + 1
            action.purpose = f"Nobody answered at {org.name}. Trying again."
            return action

        return Action(
            type=ActionType.ABANDON,
            purpose=(
                "Every lead has been followed and nothing meets the requirements. "
                "Reporting what was found so the user can decide."
            ),
        )

    # -- action builders -------------------------------------------------

    def _short_purpose(self, org: Organization) -> str:
        """What the timeline says, as opposed to what the caller is told.

        The objective handed to CALL-E restates the goal and every constraint,
        because the caller has no other context. A user watching the run
        already knows all of that, so the label stays at the level of the
        decision being made.
        """
        if org.discovered_by:
            return f"Call {org.name} — can they do it within your limits?"
        return f"Call {org.name} — can they fix this, and if not, who can?"

    def _gathering_action(self, outcome: Outcome, org: Organization) -> Action:
        objective = self._objective_for(outcome, org)
        return Action(
            type=ActionType.CALL,
            purpose=self._short_purpose(org),
            target_org_id=org.id,
            task_prompt=build_gathering_task(outcome, org, objective),
            result_schema=dict(EVIDENCE_SCHEMA),
            commits_user=False,
            attempt=outcome.calls_to_org(org.id) + 1,
        )

    def _commit_action(
        self, outcome: Outcome, org: Organization, evaluation: Evaluation
    ) -> Action:
        offer = evaluation.offer
        price = (
            f"{offer.currency} {offer.price:.2f}" if offer.price is not None else "an unquoted amount"
        )
        return Action(
            type=ActionType.CALL,
            purpose=f"Call {org.name} back to accept: {offer.summary} at {price}.",
            target_org_id=org.id,
            task_prompt=build_commit_task(outcome, org, offer),
            result_schema=dict(EVIDENCE_SCHEMA),
            commits_user=True,
            commitment_summary=(
                f"Accepting {offer.summary} from {org.name} at {price}"
                + (f", delivery {offer.eta}" if offer.eta else "")
                + "."
            ),
            status=ActionStatus.PLANNED,
            attempt=outcome.calls_to_org(org.id) + 1,
        )
