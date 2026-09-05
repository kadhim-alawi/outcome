"""Data model for an outcome.

The shape of this module is the product argument. A user does not create a
call, they create an `Outcome`: a goal in their own words plus the constraints
that decide whether any given answer is actually acceptable. Everything else
here exists to let a planner reason about that goal across more than one
conversation.

`Evidence` is the load-bearing type. A finished CALL-E call is not a result, it
is testimony: some facts, maybe a commitment, maybe a blocker, and — the part
that makes the agent go somewhere new — maybe a `Referral`, a different
organisation the person on the phone told us to try instead. Referrals are how
the frontier grows during a run, and they are the reason this is a planning
problem rather than a list of numbers to dial.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# --------------------------------------------------------------------------
# Constraints
# --------------------------------------------------------------------------


class ConstraintKind(str, Enum):
    DEADLINE = "deadline"
    BUDGET = "budget"
    MINIMUM = "minimum"
    REQUIRED_FACT = "required_fact"
    PREFERENCE = "preference"
    FORBIDDEN = "forbidden"


@dataclass
class Constraint:
    """One rule an acceptable resolution has to satisfy.

    `hard` is the difference between "this answer is wrong, keep working" and
    "this answer is worse than I hoped, take it". A soft constraint that is
    violated ranks an option lower; a hard one disqualifies it outright and
    sends the planner back out to find something else.
    """

    kind: ConstraintKind
    description: str
    value: Any = None
    hard: bool = True
    id: str = field(default_factory=lambda: new_id("con"))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Constraint":
        return cls(
            kind=ConstraintKind(d["kind"]),
            description=d["description"],
            value=d.get("value"),
            hard=bool(d.get("hard", True)),
            id=d.get("id") or new_id("con"),
        )


# --------------------------------------------------------------------------
# Directory: who we can call
# --------------------------------------------------------------------------


@dataclass
class Organization:
    """A callable party.

    `discovered_by` is empty for the parties the user supplied and set to the
    action id that produced the referral for everyone the agent found itself.
    The demo leans on that distinction: the interesting lines in the timeline
    are the ones the user never typed in.
    """

    name: str
    phone: str
    role: str = ""
    discovered_by: str | None = None
    id: str = field(default_factory=lambda: new_id("org"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Organization":
        return cls(
            name=d["name"],
            phone=d["phone"],
            role=d.get("role", ""),
            discovered_by=d.get("discovered_by"),
            id=d.get("id") or new_id("org"),
        )


E164 = re.compile(r"^\+[1-9]\d{6,14}$")


def is_e164(phone: str) -> bool:
    """Strict. A number that needs normalising to pass is a number we are
    guessing at, and a guessed digit dials a stranger."""
    return bool(E164.match((phone or "").strip()))


def mask_phone(phone: str) -> str:
    """Phone numbers are masked everywhere they are shown or logged.

    Required by the awesome-phone-call-agents safety rules, and a good idea
    regardless: an outcome record is a document users forward to other people.
    """
    digits = [c for c in phone if c.isdigit()]
    if len(digits) <= 4:
        return "*" * len(digits)
    tail = "".join(digits[-4:])
    lead = "+" if phone.strip().startswith("+") else ""
    return f"{lead}{'*' * (len(digits) - 4)}{tail}"


# --------------------------------------------------------------------------
# Actions
# --------------------------------------------------------------------------


class ActionType(str, Enum):
    CALL = "call"
    VERIFY = "verify"
    ASK_USER = "ask_user"
    COMPLETE = "complete"
    ABANDON = "abandon"


class ActionStatus(str, Enum):
    PLANNED = "planned"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclass
class Action:
    """One step the planner wants to take.

    A CALL action carries the whole CALL-E request with it — objective, spoken
    task, and the result schema the conversation has to fill in. That is
    deliberate: the planner decides what a call is *for*, and the adapter only
    decides how to place it.
    """

    type: ActionType
    purpose: str
    target_org_id: str | None = None
    task_prompt: str = ""
    result_schema: dict[str, Any] = field(default_factory=dict)
    commits_user: bool = False
    commitment_summary: str = ""
    approved: bool = False
    status: ActionStatus = ActionStatus.PLANNED
    attempt: int = 1
    created_at: str = field(default_factory=utc_now)
    id: str = field(default_factory=lambda: new_id("act"))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Action":
        return cls(
            type=ActionType(d["type"]),
            purpose=d["purpose"],
            target_org_id=d.get("target_org_id"),
            task_prompt=d.get("task_prompt", ""),
            result_schema=d.get("result_schema") or {},
            commits_user=bool(d.get("commits_user", False)),
            commitment_summary=d.get("commitment_summary", ""),
            approved=bool(d.get("approved", False)),
            status=ActionStatus(d.get("status", "planned")),
            attempt=int(d.get("attempt", 1)),
            created_at=d.get("created_at") or utc_now(),
            id=d.get("id") or new_id("act"),
        )


# --------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------


class CallVerdict(str, Enum):
    NO_ANSWER = "no_answer"
    REFUSED = "refused"
    BLOCKED = "blocked"
    PARTIAL = "partial"
    OFFER = "offer"
    CONFIRMED = "confirmed"


@dataclass
class Referral:
    """Someone on a call telling us to try somebody else."""

    org_name: str
    phone: str
    reason: str = ""
    role: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Offer:
    """A concrete proposal that constraints can be evaluated against.

    Kept separate from free-text facts because this is the only part of a call
    the constraint checker can rule on mechanically. `price` and `eta` are
    optional: a call that names a date but no price still produces an offer,
    and a missing field is unknown rather than zero.
    """

    summary: str
    org_id: str
    # The amount at stake. Which direction is *better* is decided by the
    # constraints, not by this field: a `budget` makes it a cost to stay under,
    # a `minimum` makes it a value to clear. An outcome that recovers a refund
    # and one that buys a replacement are the same shape with the comparison
    # reversed.
    price: float | None = None
    currency: str = "USD"
    eta: str | None = None
    reference: str | None = None
    id: str = field(default_factory=lambda: new_id("off"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Offer":
        return cls(
            summary=d["summary"],
            org_id=d["org_id"],
            price=d.get("price"),
            currency=d.get("currency", "USD"),
            eta=d.get("eta"),
            reference=d.get("reference"),
            id=d.get("id") or new_id("off"),
        )


@dataclass
class Evidence:
    """What one call actually established.

    Written once per completed action and never edited. The planner reads the
    evidence log rather than raw call payloads, which is what lets the same
    planner run against the live adapter and the mock one.
    """

    action_id: str
    org_id: str | None
    verdict: CallVerdict
    facts: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    referrals: list[Referral] = field(default_factory=list)
    offer: Offer | None = None
    call_id: str | None = None
    recorded_at: str = field(default_factory=utc_now)
    id: str = field(default_factory=lambda: new_id("ev"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action_id": self.action_id,
            "org_id": self.org_id,
            "verdict": self.verdict.value,
            "facts": list(self.facts),
            "blockers": list(self.blockers),
            "referrals": [r.to_dict() for r in self.referrals],
            "offer": self.offer.to_dict() if self.offer else None,
            "call_id": self.call_id,
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Evidence":
        return cls(
            action_id=d["action_id"],
            org_id=d.get("org_id"),
            verdict=CallVerdict(d["verdict"]),
            facts=list(d.get("facts") or []),
            blockers=list(d.get("blockers") or []),
            referrals=[Referral(**r) for r in (d.get("referrals") or [])],
            offer=Offer.from_dict(d["offer"]) if d.get("offer") else None,
            call_id=d.get("call_id"),
            recorded_at=d.get("recorded_at") or utc_now(),
            id=d.get("id") or new_id("ev"),
        )


# --------------------------------------------------------------------------
# Outcome
# --------------------------------------------------------------------------


class OutcomeStatus(str, Enum):
    DRAFT = "draft"
    WORKING = "working"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_USER = "awaiting_user"
    RESOLVED = "resolved"
    FAILED = "failed"
    ABANDONED = "abandoned"


TERMINAL_STATUSES = {
    OutcomeStatus.RESOLVED,
    OutcomeStatus.FAILED,
    OutcomeStatus.ABANDONED,
}


@dataclass
class Budget:
    """The hard stops.

    `max_calls` is not a tuning knob, it is the product's safety story. A CALL-E
    hackathon account has 20 calls in it, and an agent that decides for itself
    how many people to phone needs a number it cannot talk its way past.
    """

    max_calls: int = 6
    max_calls_per_org: int = 2
    max_actions: int = 20

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Budget":
        return cls(
            max_calls=int(d.get("max_calls", 6)),
            max_calls_per_org=int(d.get("max_calls_per_org", 2)),
            max_actions=int(d.get("max_actions", 20)),
        )


@dataclass
class Outcome:
    goal: str
    constraints: list[Constraint] = field(default_factory=list)
    organizations: list[Organization] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    budget: Budget = field(default_factory=Budget)
    declined_offer_ids: list[str] = field(default_factory=list)
    status: OutcomeStatus = OutcomeStatus.DRAFT
    resolution: dict[str, Any] | None = None
    pending_approval_action_id: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    id: str = field(default_factory=lambda: new_id("out"))

    # -- lookups ---------------------------------------------------------

    def org(self, org_id: str | None) -> Organization | None:
        if org_id is None:
            return None
        return next((o for o in self.organizations if o.id == org_id), None)

    def action(self, action_id: str) -> Action | None:
        return next((a for a in self.actions if a.id == action_id), None)

    def evidence_for(self, action_id: str) -> Evidence | None:
        return next((e for e in self.evidence if e.action_id == action_id), None)

    def calls_placed(self) -> int:
        return sum(
            1
            for a in self.actions
            if a.type == ActionType.CALL and a.status in (ActionStatus.DONE, ActionStatus.FAILED)
        )

    def calls_to_org(self, org_id: str) -> int:
        return sum(
            1
            for a in self.actions
            if a.type == ActionType.CALL
            and a.target_org_id == org_id
            and a.status in (ActionStatus.DONE, ActionStatus.FAILED)
        )

    def offers(self) -> list[Offer]:
        return [e.offer for e in self.evidence if e.offer is not None]

    def open_offers(self) -> list[Offer]:
        """Offers the planner may still act on.

        An offer the user rejected at the approval step stays in `offers()` so
        the final report can show it was considered, but it must never come
        back round as the planner's next suggestion — otherwise declining an
        option just re-proposes it.
        """
        return [o for o in self.offers() if o.id not in self.declined_offer_ids]

    def pending_approval(self) -> "Action | None":
        return next(
            (a for a in self.actions if a.status is ActionStatus.AWAITING_APPROVAL), None
        )

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    # -- mutation --------------------------------------------------------

    def add_organization(self, org: Organization) -> Organization:
        """Idempotent on phone number, so two referrals to the same depot do
        not become two entries the planner will call twice."""
        existing = next((o for o in self.organizations if o.phone == org.phone), None)
        if existing:
            return existing
        self.organizations.append(org)
        self.updated_at = utc_now()
        return org

    def record(self, evidence: Evidence) -> None:
        self.evidence.append(evidence)
        self.updated_at = utc_now()

    # -- serialisation ---------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status.value,
            "constraints": [c.to_dict() for c in self.constraints],
            "organizations": [o.to_dict() for o in self.organizations],
            "actions": [a.to_dict() for a in self.actions],
            "evidence": [e.to_dict() for e in self.evidence],
            "budget": self.budget.to_dict(),
            "declined_offer_ids": list(self.declined_offer_ids),
            "resolution": self.resolution,
            "pending_approval_action_id": self.pending_approval_action_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Outcome":
        return cls(
            goal=d["goal"],
            constraints=[Constraint.from_dict(c) for c in d.get("constraints") or []],
            organizations=[Organization.from_dict(o) for o in d.get("organizations") or []],
            actions=[Action.from_dict(a) for a in d.get("actions") or []],
            evidence=[Evidence.from_dict(e) for e in d.get("evidence") or []],
            budget=Budget.from_dict(d.get("budget") or {}),
            declined_offer_ids=list(d.get("declined_offer_ids") or []),
            status=OutcomeStatus(d.get("status", "draft")),
            resolution=d.get("resolution"),
            pending_approval_action_id=d.get("pending_approval_action_id"),
            created_at=d.get("created_at") or utc_now(),
            updated_at=d.get("updated_at") or utc_now(),
            id=d.get("id") or new_id("out"),
        )
