"""Building an `Outcome` from a scenario file or from a typed request.

This is the boundary where untrusted input becomes a run, so it is where phone
numbers and budgets are checked. A malformed number that gets past here becomes
a call to somebody, and a budget that gets past here becomes a bill.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from .interpret import default_interpreter
from .models import Budget, Constraint, ConstraintKind, Organization, Outcome, is_e164

# A ceiling on the ceiling. The form is user input, and "call up to 500 people"
# should not be one keystroke away from "call up to 5".
MAX_CALLS_CEILING = 25
MAX_CALLS_PER_ORG_CEILING = 5


class DefinitionError(ValueError):
    """The request cannot be turned into a runnable outcome."""


def _organizations(raw: Any) -> list[Organization]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise DefinitionError("'organizations' must be a list.")
    seen: set[str] = set()
    out: list[Organization] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise DefinitionError(f"organizations[{index}] must be an object.")
        name = str(item.get("name") or "").strip()
        phone = str(item.get("phone") or "").strip().replace(" ", "").replace("-", "")
        if not name:
            raise DefinitionError(f"organizations[{index}] needs a name.")
        if not is_e164(phone):
            raise DefinitionError(
                f"{name}: {phone or '(blank)'} is not an E.164 number "
                "(a leading + and 7-15 digits, e.g. +15550100001)."
            )
        if phone in seen:
            raise DefinitionError(f"{name}: {phone} is listed twice.")
        seen.add(phone)
        # Ids are always freshly minted here. A caller-supplied id would let a
        # request collide with another run's organisation, and nothing outside
        # this process has a legitimate reason to name one.
        out.append(
            Organization(name=name, phone=phone, role=str(item.get("role") or "").strip())
        )
    return out


def _constraints(raw: Any) -> list[Constraint]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise DefinitionError("'constraints' must be a list.")
    out: list[Constraint] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise DefinitionError(f"constraints[{index}] must be an object.")
        try:
            kind = ConstraintKind(str(item.get("kind")))
        except ValueError:
            allowed = ", ".join(k.value for k in ConstraintKind)
            raise DefinitionError(
                f"constraints[{index}]: unknown kind {item.get('kind')!r}. One of: {allowed}."
            ) from None
        description = str(item.get("description") or "").strip()
        if not description:
            raise DefinitionError(f"constraints[{index}] needs a description.")
        value = item.get("value")
        if kind in (ConstraintKind.BUDGET, ConstraintKind.MINIMUM):
            try:
                value = float(str(value).replace(",", "").lstrip("$£€"))
            except (TypeError, ValueError):
                raise DefinitionError(
                    f"{description}: {value!r} is not a number. A {kind.value} that cannot "
                    "be parsed would never block anything."
                ) from None
        elif kind is ConstraintKind.DEADLINE:
            try:
                value = date.fromisoformat(str(value)).isoformat()
            except ValueError:
                raise DefinitionError(
                    f"{description}: {value!r} is not a YYYY-MM-DD date. A deadline that "
                    "cannot be parsed would never block anything."
                ) from None
        out.append(
            Constraint(
                kind=kind,
                description=description,
                value=value,
                hard=bool(item.get("hard", True)),
            )
        )
    return out


def _budget(raw: Any) -> Budget:
    budget = Budget.from_dict(raw or {})
    if not 1 <= budget.max_calls <= MAX_CALLS_CEILING:
        raise DefinitionError(f"max_calls must be between 1 and {MAX_CALLS_CEILING}.")
    if not 1 <= budget.max_calls_per_org <= MAX_CALLS_PER_ORG_CEILING:
        raise DefinitionError(
            f"max_calls_per_org must be between 1 and {MAX_CALLS_PER_ORG_CEILING}."
        )
    if budget.max_calls_per_org > budget.max_calls:
        raise DefinitionError("max_calls_per_org cannot exceed max_calls.")
    return budget


def outcome_from_definition(definition: dict[str, Any]) -> Outcome:
    goal = str(definition.get("goal") or "").strip()
    if not goal:
        raise DefinitionError("An outcome needs a goal.")
    return Outcome(
        goal=goal,
        constraints=_constraints(definition.get("constraints")),
        organizations=_organizations(definition.get("organizations")),
        budget=_budget(definition.get("budget")),
    )


def load_scenario(path: str) -> tuple[dict[str, Any], Outcome]:
    with open(path, encoding="utf-8") as handle:
        scenario = json.load(handle)
    if "outcome" not in scenario:
        raise DefinitionError(f"{path} has no 'outcome' block.")
    return scenario, outcome_from_definition(scenario["outcome"])


def interpret_request(text: str, today: date | None = None) -> dict[str, Any]:
    """One sentence in, a goal and constraints out — for the form to show back.

    Never used to start a run directly. The parse is offered to the user as
    editable fields, because a limit that failed to parse is a limit that will
    never block anything and the user is the only one who can catch it.
    """
    parsed = default_interpreter().interpret(text, today)
    return {
        "goal": parsed["goal"],
        "constraints": [c.to_dict() for c in parsed["constraints"]],
        "source": parsed["source"],
    }


def outcome_from_request(
    text: str,
    organizations: list[dict[str, Any]] | None = None,
    budget: dict[str, Any] | None = None,
    today: date | None = None,
) -> Outcome:
    parsed = default_interpreter().interpret(text, today)
    return outcome_from_definition(
        {
            "goal": parsed["goal"],
            "constraints": [c.to_dict() for c in parsed["constraints"]],
            "organizations": organizations or [],
            "budget": budget or {},
        }
    )
