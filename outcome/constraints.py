"""Deciding whether an offer is actually acceptable.

This is the part that makes the agent argue with a successful phone call. A
call that ends with a cheerful "yes we can do that" is a *success* to the
telephony layer and may still be a failure to the user, because it costs $60
over their limit or lands two days after they needed it. The engine replans on
this verdict, not on the call status.

Evaluation is deterministic on purpose. A model decides what was said; a
comparison operator decides whether it is good enough. Putting the money and
the deadline behind a rule rather than a prompt is what makes the approval
screen trustworthy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

from .models import Constraint, ConstraintKind, Offer


class Judgement(str, Enum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class ConstraintResult:
    constraint: Constraint
    judgement: Judgement
    detail: str

    @property
    def blocking(self) -> bool:
        """A soft constraint never blocks; an unknown never blocks either.

        Refusing to accept an offer because a field was not mentioned would
        strand every run behind a detail nobody asked about on the call. Unknown
        is surfaced to the user at the approval step instead.
        """
        return self.judgement is Judgement.VIOLATED and self.constraint.hard

    def to_dict(self) -> dict[str, Any]:
        return {
            "constraint_id": self.constraint.id,
            "kind": self.constraint.kind.value,
            "description": self.constraint.description,
            "hard": self.constraint.hard,
            "judgement": self.judgement.value,
            "detail": self.detail,
        }


@dataclass
class Evaluation:
    offer: Offer
    results: list[ConstraintResult]

    @property
    def acceptable(self) -> bool:
        return not any(r.blocking for r in self.results)

    @property
    def violations(self) -> list[ConstraintResult]:
        return [r for r in self.results if r.judgement is Judgement.VIOLATED]

    @property
    def unknowns(self) -> list[ConstraintResult]:
        return [r for r in self.results if r.judgement is Judgement.UNKNOWN]

    def score(self) -> tuple[int, float, float]:
        """Sort key for picking between acceptable offers: fewest soft
        violations, then cheapest, then earliest. Unknown price sorts last
        rather than free."""
        soft = sum(1 for r in self.violations if not r.constraint.hard)
        price = self.offer.price if self.offer.price is not None else float("inf")
        eta = _parse_date(self.offer.eta)
        eta_key = eta.toordinal() if eta else float("inf")
        return (soft, price, eta_key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "offer": self.offer.to_dict(),
            "acceptable": self.acceptable,
            "results": [r.to_dict() for r in self.results],
        }


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text[: len(fmt) + 6], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _evaluate_one(constraint: Constraint, offer: Offer) -> ConstraintResult:
    kind = constraint.kind

    if kind is ConstraintKind.BUDGET:
        limit = _as_float(constraint.value)
        if limit is None:
            return ConstraintResult(constraint, Judgement.UNKNOWN, "No numeric limit set.")
        if offer.price is None:
            return ConstraintResult(
                constraint, Judgement.UNKNOWN, "No price was quoted on the call."
            )
        if offer.price > limit:
            over = offer.price - limit
            return ConstraintResult(
                constraint,
                Judgement.VIOLATED,
                f"{offer.currency} {offer.price:.2f} is {offer.currency} {over:.2f} over the "
                f"{offer.currency} {limit:.2f} limit.",
            )
        return ConstraintResult(
            constraint,
            Judgement.SATISFIED,
            f"{offer.currency} {offer.price:.2f} is within the {offer.currency} {limit:.2f} limit.",
        )

    if kind is ConstraintKind.DEADLINE:
        deadline = _parse_date(constraint.value)
        eta = _parse_date(offer.eta)
        if deadline is None:
            return ConstraintResult(constraint, Judgement.UNKNOWN, "No parseable deadline set.")
        if eta is None:
            return ConstraintResult(
                constraint, Judgement.UNKNOWN, "No dated commitment was given on the call."
            )
        if eta > deadline:
            return ConstraintResult(
                constraint,
                Judgement.VIOLATED,
                f"{eta.isoformat()} is after the {deadline.isoformat()} deadline.",
            )
        return ConstraintResult(
            constraint,
            Judgement.SATISFIED,
            f"{eta.isoformat()} is on or before the {deadline.isoformat()} deadline.",
        )

    if kind is ConstraintKind.REQUIRED_FACT:
        field_name = str(constraint.value or "reference")
        present = getattr(offer, field_name, None) if hasattr(offer, field_name) else None
        if present:
            return ConstraintResult(constraint, Judgement.SATISFIED, f"{field_name}={present}")
        return ConstraintResult(
            constraint, Judgement.VIOLATED, f"The call did not produce a {field_name}."
        )

    if kind is ConstraintKind.FORBIDDEN:
        needle = str(constraint.value or "").lower().strip()
        if not needle:
            return ConstraintResult(constraint, Judgement.NOT_APPLICABLE, "No term configured.")
        if needle in offer.summary.lower():
            return ConstraintResult(
                constraint, Judgement.VIOLATED, f"Offer mentions {needle!r}."
            )
        return ConstraintResult(constraint, Judgement.SATISFIED, f"No mention of {needle!r}.")

    if kind is ConstraintKind.PREFERENCE:
        needle = str(constraint.value or "").lower().strip()
        if not needle:
            return ConstraintResult(constraint, Judgement.NOT_APPLICABLE, "No preference set.")
        if needle in offer.summary.lower():
            return ConstraintResult(constraint, Judgement.SATISFIED, f"Matches {needle!r}.")
        return ConstraintResult(
            constraint, Judgement.VIOLATED, f"Does not match preferred {needle!r}."
        )

    return ConstraintResult(constraint, Judgement.NOT_APPLICABLE, "Unhandled constraint kind.")


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate(offer: Offer, constraints: list[Constraint]) -> Evaluation:
    return Evaluation(offer=offer, results=[_evaluate_one(c, offer) for c in constraints])


def best_acceptable(
    offers: list[Offer], constraints: list[Constraint]
) -> tuple[Evaluation | None, list[Evaluation]]:
    """Return the best acceptable offer and every evaluation considered.

    The rejected evaluations are returned too because the user's report needs
    to say what the agent turned down and why — an outcome that only shows the
    winner reads like luck.
    """
    evaluations = [evaluate(o, constraints) for o in offers]
    acceptable = [e for e in evaluations if e.acceptable]
    if not acceptable:
        return None, evaluations
    return min(acceptable, key=lambda e: e.score()), evaluations
