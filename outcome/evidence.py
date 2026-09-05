"""Turning a finished call into evidence the planner can reason about.

Everything here is defensive. `structured_result` is filled in by a model on
the other side of a phone conversation, so it is the least trustworthy input in
the system: fields go missing, a price arrives as the string "$438", a referral
comes back with a name and no number. The engine must not crash on any of that,
and — more importantly — must not silently invent the missing half.
"""

from __future__ import annotations

import re
from typing import Any

from .calle import CallOutcome
from .models import Action, CallVerdict, Evidence, Offer, Referral

_E164 = re.compile(r"^\+[1-9]\d{6,14}$")
_MONEY = re.compile(r"-?\d+(?:[\d,]*\d)?(?:\.\d+)?")


def parse_money(value: Any) -> float | None:
    """Accept 438, "438", "$438.00", "USD 1,438" — reject anything else.

    A price the agent cannot read is `None`, which the budget check reports as
    unknown. Guessing zero here would let a free-of-charge reading sail past a
    budget limit.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str):
        return None
    match = _MONEY.search(value.replace(" ", ""))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _parse_verdict(structured: dict[str, Any], call: CallOutcome) -> CallVerdict:
    raw = str(structured.get("verdict", "")).strip().lower()
    try:
        verdict = CallVerdict(raw)
    except ValueError:
        verdict = None

    reached = structured.get("reached")
    if not call.succeeded:
        # A call the provider could not complete is never testimony, whatever
        # the structured block claims.
        return CallVerdict.NO_ANSWER
    if reached is False:
        return CallVerdict.NO_ANSWER
    if verdict is not None:
        return verdict
    if structured.get("offer"):
        return CallVerdict.OFFER
    if _as_str_list(structured.get("blockers")):
        return CallVerdict.BLOCKED
    return CallVerdict.PARTIAL


def _parse_referrals(structured: dict[str, Any]) -> list[Referral]:
    """A referral without a usable E.164 number is dropped.

    The agent's whole advantage is that it can follow a pointer given on a
    call. A pointer it cannot dial is not one, and keeping it would put a
    frontier entry in front of the planner that can never be actioned.
    """
    out: list[Referral] = []
    for item in structured.get("referrals") or []:
        if not isinstance(item, dict):
            continue
        phone = str(item.get("phone") or "").strip().replace(" ", "").replace("-", "")
        name = str(item.get("org_name") or "").strip()
        if not name or not _E164.match(phone):
            continue
        out.append(
            Referral(
                org_name=name,
                phone=phone,
                role=str(item.get("role") or "").strip(),
                reason=str(item.get("reason") or "").strip(),
            )
        )
    return out


def _parse_offer(structured: dict[str, Any], org_id: str | None) -> Offer | None:
    raw = structured.get("offer")
    if not isinstance(raw, dict):
        return None
    summary = str(raw.get("summary") or "").strip()
    price = parse_money(raw.get("price"))
    eta = raw.get("eta")
    eta = str(eta).strip() if eta else None
    reference = raw.get("reference")
    reference = str(reference).strip() if reference else None
    if not summary and price is None and not eta:
        # An empty offer object is not an offer.
        return None
    return Offer(
        summary=summary or "Unnamed offer",
        org_id=org_id or "",
        price=price,
        currency=str(raw.get("currency") or "USD").strip().upper() or "USD",
        eta=eta,
        reference=reference,
    )


def extract(action: Action, call: CallOutcome) -> Evidence:
    structured = call.structured if isinstance(call.structured, dict) else {}
    verdict = _parse_verdict(structured, call)
    offer = _parse_offer(structured, action.target_org_id) if verdict in (
        CallVerdict.OFFER,
        CallVerdict.CONFIRMED,
    ) else None

    facts = _as_str_list(structured.get("facts"))
    blockers = _as_str_list(structured.get("blockers"))
    if verdict is CallVerdict.NO_ANSWER and not blockers:
        blockers = ["Nobody answered."]

    return Evidence(
        action_id=action.id,
        org_id=action.target_org_id,
        verdict=verdict,
        facts=facts,
        blockers=blockers,
        referrals=_parse_referrals(structured),
        offer=offer,
        call_id=call.call_id,
    )
