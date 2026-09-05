"""The line between what the agent may do alone and what needs a human.

The rule is not "ask before every call". Asking before every call would make an
autonomous agent pointless, and users stop reading prompts they see six times a
run. The rule is about *commitment*: asking a question costs nothing and can be
undone by hanging up, whereas agreeing to a price, cancelling a booking or
placing an order binds the user to something.

So: information-gathering runs unattended, and anything that would bind the
user stops and waits. The planner marks its own actions, and `classify` keeps a
keyword safety net underneath that — a planner that forgets to set the flag on
a call whose script says "confirm the order" gets caught here rather than on
the phone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .constraints import Evaluation
from .models import Action, Offer, Organization, mask_phone

COMMITTING_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\baccept(ing|s)?\b",
        r"\bconfirm(ing|s)? (the )?(order|booking|purchase|replacement|shipment|payment)\b",
        r"\bplace (the |an )?order\b",
        r"\bpurchas(e|ing)\b",
        r"\bpay(ment)?\b",
        r"\bcancel(ling|ing|s)?\b",
        r"\bagree(ing)? to\b",
        r"\bsign\b",
        r"\bauthoris(e|ing)\b|\bauthoriz(e|ing)\b",
        r"\bcommit(ting|s)?\b",
    )
)


@dataclass
class ApprovalDecision:
    required: bool
    reason: str


# A committing verb inside a prohibition is the opposite of a commitment. Every
# information-gathering script this planner writes ends with "you are NOT
# authorised to agree to anything, accept any price, or cancel anything", and a
# net that reads those words as intent flags every call in the run — which is
# how a safety net turns into a habit of clicking approve.
NEGATION_CUES: tuple[str, ...] = (
    "not authorised",
    "not authorized",
    "do not",
    "don't",
    "never",
    "must not",
    "cannot",
    "no authority",
    "without approval",
)


def _authorising_lines(text: str) -> list[str]:
    """The lines of a script that grant authority rather than withhold it.

    Line-level, not sentence-level, because these scripts are written as
    bulleted rules and a bullet is the unit that carries one instruction. A
    committing verb sharing a line with a negation cue is read as prohibited.
    This is a backstop, not the mechanism: `commits_user`, set by the planner,
    is what actually gates the call.
    """
    lines = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(cue in lowered for cue in NEGATION_CUES):
            continue
        lines.append(line)
    return lines


def classify(action: Action) -> ApprovalDecision:
    if action.commits_user:
        return ApprovalDecision(
            True, action.commitment_summary or "This call would commit you to something."
        )
    for line in _authorising_lines(f"{action.purpose}\n{action.task_prompt}"):
        for pattern in COMMITTING_PATTERNS:
            match = pattern.search(line)
            if match:
                return ApprovalDecision(
                    True,
                    f"The call script says {match.group(0)!r} outside any prohibition, which "
                    "would bind you. Escalated for approval even though the planner did not "
                    "flag it.",
                )
    return ApprovalDecision(False, "Information gathering only; nothing is committed.")


@dataclass
class ApprovalRequest:
    """Everything the user needs on one screen to answer yes or no.

    Deliberately includes `rejected`: an approval screen that shows only the
    winning option asks the user to trust a search they cannot see. Showing what
    was turned down, and on which constraint, is what makes a one-tap approval
    an informed one.
    """

    action: Action
    organization: Organization | None
    offer: Offer | None
    evaluation: Evaluation | None
    rejected: list[Evaluation]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action.id,
            "reason": self.reason,
            "organization": (
                {
                    "name": self.organization.name,
                    "phone": mask_phone(self.organization.phone),
                    "role": self.organization.role,
                }
                if self.organization
                else None
            ),
            "offer": self.offer.to_dict() if self.offer else None,
            "evaluation": self.evaluation.to_dict() if self.evaluation else None,
            "rejected": [e.to_dict() for e in self.rejected],
            "prompt": self.prompt(),
        }

    def prompt(self) -> str:
        if not self.offer:
            return self.reason
        where = self.organization.name if self.organization else "the other party"
        price = (
            f"{self.offer.currency} {self.offer.price:.2f}"
            if self.offer.price is not None
            else "an unquoted amount"
        )
        when = f", arriving {self.offer.eta}" if self.offer.eta else ""
        return f"Accept {self.offer.summary} from {where} for {price}{when}?"
