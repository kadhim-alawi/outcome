"""Building an `Outcome` from a scenario file or from a typed request."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from .interpret import default_interpreter
from .models import Budget, Constraint, Organization, Outcome


def outcome_from_definition(definition: dict[str, Any]) -> Outcome:
    return Outcome(
        goal=definition["goal"],
        constraints=[Constraint.from_dict(c) for c in definition.get("constraints") or []],
        organizations=[
            Organization.from_dict(o) for o in definition.get("organizations") or []
        ],
        budget=Budget.from_dict(definition.get("budget") or {}),
    )


def load_scenario(path: str) -> tuple[dict[str, Any], Outcome]:
    with open(path, encoding="utf-8") as handle:
        scenario = json.load(handle)
    if "outcome" not in scenario:
        raise ValueError(f"{path} has no 'outcome' block.")
    return scenario, outcome_from_definition(scenario["outcome"])


def outcome_from_request(
    text: str,
    organizations: list[dict[str, Any]] | None = None,
    budget: dict[str, Any] | None = None,
    today: date | None = None,
) -> Outcome:
    """The path the product uses: one sentence plus who to start with."""
    parsed = default_interpreter().interpret(text, today)
    return Outcome(
        goal=parsed["goal"],
        constraints=list(parsed["constraints"]),
        organizations=[Organization.from_dict(o) for o in organizations or []],
        budget=Budget.from_dict(budget or {}),
    )
