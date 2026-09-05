"""Turning a sentence into a goal with constraints.

The user types one line — "get a replacement pallet before Friday, under $500"
— and the engine needs a goal plus a machine-checkable budget and deadline. The
parse matters more than it looks: a budget that fails to parse is a budget that
never blocks an offer, so a miss here silently disables the safety net further
down.

Two implementations. `RuleInterpreter` is regex over money and dates and runs
everywhere with no credential. `LLMInterpreter` asks a model and falls back to
the rules on any failure, because a goal the user can see is better than an
exception. Both return the constraints they are confident about and leave the
rest to the form, which is why the UI always shows the parsed constraints back
to the user as editable fields rather than acting on them silently.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import date, timedelta
from typing import Any

from .models import Constraint, ConstraintKind

_CURRENCY = re.compile(
    r"(?:(?P<sym>[$£€])\s*(?P<amt1>\d[\d,]*(?:\.\d{1,2})?)"
    r"|(?P<code>USD|EUR|GBP|SGD|AUD)\s*(?P<amt2>\d[\d,]*(?:\.\d{1,2})?)"
    r"|(?P<amt3>\d[\d,]*(?:\.\d{1,2})?)\s*(?P<code2>usd|dollars|euros|pounds))",
    re.IGNORECASE,
)
_UNDER = re.compile(
    r"\b(?:under|below|less than|no more than|at most|max(?:imum)?|within|budget of|up to)\b",
    re.IGNORECASE,
)
_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}
_SYMBOL_TO_CODE = {"$": "USD", "£": "GBP", "€": "EUR"}


def _next_weekday(name: str, today: date) -> date:
    target = _WEEKDAYS[name]
    ahead = (target - today.weekday()) % 7
    return today + timedelta(days=ahead or 7)


def parse_budget(text: str) -> tuple[float, str] | None:
    """Only reads an amount that sits behind a limit phrase.

    "under $500" is a budget. "$500 of stock was damaged" is not, and treating
    it as one would cap the replacement at the value of the loss.
    """
    for match in _CURRENCY.finditer(text):
        prefix = text[max(0, match.start() - 40) : match.start()]
        if not _UNDER.search(prefix):
            continue
        amount = match.group("amt1") or match.group("amt2") or match.group("amt3")
        code = (
            _SYMBOL_TO_CODE.get(match.group("sym") or "")
            or (match.group("code") or "").upper()
            or {"usd": "USD", "dollars": "USD", "euros": "EUR", "pounds": "GBP"}.get(
                (match.group("code2") or "").lower(), "USD"
            )
        )
        try:
            return float(amount.replace(",", "")), code
        except ValueError:
            continue
    return None


def parse_deadline(text: str, today: date | None = None) -> date | None:
    today = today or date.today()
    iso = _ISO_DATE.search(text)
    if iso:
        try:
            return date.fromisoformat(iso.group(1))
        except ValueError:
            pass
    lowered = text.lower()
    if "today" in lowered:
        return today
    if "tomorrow" in lowered:
        return today + timedelta(days=1)
    if re.search(r"\bthis week\b", lowered):
        return _next_weekday("friday", today)
    for name in _WEEKDAYS:
        if re.search(rf"\b(?:by|before|on)\s+(?:next\s+)?{name}\b", lowered):
            return _next_weekday(name, today)
    match = re.search(r"\bwithin (\d+) (day|days|week|weeks)\b", lowered)
    if match:
        count = int(match.group(1))
        days = count * (7 if match.group(2).startswith("week") else 1)
        return today + timedelta(days=days)
    return None


class RuleInterpreter:
    """Deterministic. Runs with no credential and no network."""

    def interpret(self, text: str, today: date | None = None) -> dict[str, Any]:
        today = today or date.today()
        constraints: list[Constraint] = []

        budget = parse_budget(text)
        if budget:
            amount, code = budget
            constraints.append(
                Constraint(
                    kind=ConstraintKind.BUDGET,
                    description=f"Total cost at or under {code} {amount:.2f}",
                    value=amount,
                    hard=True,
                )
            )

        deadline = parse_deadline(text, today)
        if deadline:
            constraints.append(
                Constraint(
                    kind=ConstraintKind.DEADLINE,
                    description=f"Resolved on or before {deadline.isoformat()}",
                    value=deadline.isoformat(),
                    hard=True,
                )
            )

        return {"goal": text.strip(), "constraints": constraints, "source": "rules"}


ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-5"

_SYSTEM = """You convert a user's request into a goal and machine-checkable constraints.

Return ONLY a JSON object:
{"goal": "<one sentence, imperative, no constraints in it>",
 "constraints": [{"kind": "budget"|"deadline"|"required_fact"|"preference"|"forbidden",
                  "description": "<short, human-readable>",
                  "value": <number for budget, "YYYY-MM-DD" for deadline, string otherwise>,
                  "hard": true|false}]}

Rules:
- Only emit a constraint the user actually stated. Do not invent a budget or a deadline.
- budget value is a bare number. deadline value is an ISO date.
- A stated limit ("under $500", "by Friday") is hard. A stated liking ("ideally", "prefer") is soft.
- Today's date is {today}. Resolve relative dates against it."""


class LLMInterpreter:
    """Asks a model, and falls back to the rules on any failure.

    The fallback is not defensive padding: goal interpretation runs on the
    critical path of creating an outcome, and a network blip there should cost
    the user a rough parse, not the run.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        timeout: float = 20.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model
        self.timeout = timeout
        self.fallback = RuleInterpreter()

    def interpret(self, text: str, today: date | None = None) -> dict[str, Any]:
        today = today or date.today()
        if not self.api_key:
            return self.fallback.interpret(text, today)
        try:
            parsed = self._ask(text, today)
        except Exception:
            return self.fallback.interpret(text, today)
        if not parsed:
            return self.fallback.interpret(text, today)
        return parsed

    def _ask(self, text: str, today: date) -> dict[str, Any] | None:
        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "system": _SYSTEM.replace("{today}", today.isoformat()),
            "messages": [{"role": "user", "content": text}],
        }
        request = urllib.request.Request(
            ANTHROPIC_URL,
            data=json.dumps(payload).encode(),
            headers={
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode())
        blocks = [b for b in body.get("content", []) if b.get("type") == "text"]
        if not blocks:
            return None
        raw = blocks[0]["text"].strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        data = json.loads(raw)
        goal = str(data.get("goal") or "").strip()
        if not goal:
            return None
        constraints = []
        for item in data.get("constraints") or []:
            try:
                constraints.append(Constraint.from_dict(item))
            except (KeyError, ValueError):
                continue
        return {"goal": goal, "constraints": constraints, "source": f"llm:{self.model}"}


def default_interpreter() -> RuleInterpreter | LLMInterpreter:
    return LLMInterpreter() if os.environ.get("ANTHROPIC_API_KEY") else RuleInterpreter()
