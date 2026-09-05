"""CALL-E adapter — the only module in OUTCOME that can reach the network.

Written against the CALL-E Developer API contract v0.6.0:

    POST /v1/calls              {task, recipients, recipient_result_schema, metadata}
    GET  /v1/calls/{call_id}    -> {id, status, recipients:[{phones, status, structured_result}]}

Three implementations behind one protocol:

* `CalleClient`      places real calls, and is the only one that costs credits.
* `DryRunCalleClient` renders the exact request that would be sent and stops.
* `MockCalleClient`  replays a scripted scenario, which is how the tests and the
  offline demo exercise the whole engine without a credential.

The engine only ever sees `CallOutcome`, so the planner cannot tell which one
it is talking to. That is the point: the run you rehearse offline is the run
that happens on the phone.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

API_VERSION = "0.6.0"
DEFAULT_BASE_URL = "https://api.heycall-e.com"
CREATE_CALL_PATH = "/v1/calls"
GET_CALL_PATH = "/v1/calls/{call_id}"

# The bearer token goes out on every request, so the destination is not a free
# parameter. CALLE_BASE_URL exists to reach a CALL-E staging host, not to point
# a live credential at an arbitrary collector.
ALLOWED_HOSTS = frozenset({"api.heycall-e.com", "api.staging.heycall-e.com"})

TERMINAL_STATUSES = frozenset({"completed", "failed", "canceled", "cancelled"})
E164 = re.compile(r"^\+[1-9]\d{6,14}$")
POLL_INTERVAL_SECONDS = 5.0
POLL_TIMEOUT_SECONDS = 900.0


class CalleError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# The evidence schema OUTCOME asks every call to fill in
# --------------------------------------------------------------------------

EVIDENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["reached", "verdict", "facts"],
    "properties": {
        "reached": {
            "type": "boolean",
            "description": "True only if a person actually spoke with you.",
        },
        "verdict": {
            "type": "string",
            "enum": ["no_answer", "refused", "blocked", "partial", "offer", "confirmed"],
            "description": (
                "no_answer if nobody picked up. refused if they declined to help. "
                "blocked if they cannot do it and named an obstacle. partial if you "
                "learned something but the objective is unmet. offer if they proposed "
                "something concrete. confirmed if the objective is now met and they "
                "committed to it."
            ),
        },
        "facts": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Short statements of what the person actually said. Do not infer, "
                "summarise or add anything they did not say."
            ),
        },
        "blockers": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Reasons given for why the objective cannot be met here.",
        },
        "referrals": {
            "type": "array",
            "description": (
                "Other organisations or departments they told you to contact, with the "
                "number they gave. Leave empty if none were offered. Never invent a number."
            ),
            "items": {
                "type": "object",
                "required": ["org_name"],
                "properties": {
                    "org_name": {"type": "string"},
                    "phone": {"type": "string", "description": "E.164 if they gave one, else empty."},
                    "role": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
        "offer": {
            "type": ["object", "null"],
            "description": "A concrete proposal, if one was made. Null otherwise.",
            "properties": {
                "summary": {"type": "string"},
                "price": {"type": ["number", "null"], "description": "Total, in the stated currency."},
                "currency": {"type": "string"},
                "eta": {"type": ["string", "null"], "description": "YYYY-MM-DD if a date was given."},
                "reference": {"type": ["string", "null"], "description": "Any reference or order number."},
            },
        },
    },
    "additionalProperties": False,
}


# --------------------------------------------------------------------------
# Request / result types
# --------------------------------------------------------------------------


@dataclass
class CallRequest:
    """One outbound call, fully specified by the planner."""

    phone: str
    task: str
    metadata: dict[str, Any] = field(default_factory=dict)
    result_schema: dict[str, Any] = field(default_factory=lambda: dict(EVIDENCE_SCHEMA))

    def payload(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "recipients": [{"phones": [self.phone]}],
            "recipient_result_schema": self.result_schema,
            "metadata": dict(self.metadata),
        }

    def idempotency_key(self) -> str:
        """Derived from the request, so a retried submission of an unchanged
        action cannot place a second call to the same person."""
        blob = json.dumps(self.payload(), sort_keys=True, separators=(",", ":"))
        return "outcome-" + hashlib.sha256(blob.encode()).hexdigest()[:32]


@dataclass
class CallOutcome:
    """A finished call, normalised.

    `structured` is the recipient's `structured_result` — the evidence schema
    above, as filled in by the conversation.
    """

    call_id: str
    status: str
    structured: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status == "completed"


class CalleTransport(Protocol):
    # Whether `place` actually rings a phone. The engine keys its real-world
    # guards off this: a calling window protects the person being called, so it
    # applies to a live client and not to a replay. Enforcing it on the mock
    # would make the demo unrunnable at weekends and the tests dependent on the
    # day they are run, without protecting anybody.
    places_real_calls: bool

    def place(self, request: CallRequest) -> CallOutcome: ...


# --------------------------------------------------------------------------
# Live client
# --------------------------------------------------------------------------


def assert_trusted_base_url(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme != "https":
        raise CalleError(
            f"CALL-E base URL must use https, got {parsed.scheme or 'no scheme'!r}. "
            "The API key travels as a bearer token and will not go over an "
            "unencrypted connection."
        )
    if parsed.hostname not in ALLOWED_HOSTS:
        raise CalleError(
            f"Refusing to send the CALL-E credential to {parsed.hostname!r}. "
            f"Allowed hosts: {', '.join(sorted(ALLOWED_HOSTS))}."
        )
    return base_url.rstrip("/")


def parse_allowed_numbers(raw: str | None) -> frozenset[str]:
    """Read CALLE_ALLOWED_NUMBERS: a comma-separated E.164 allowlist."""
    if not raw or not raw.strip():
        return frozenset()
    numbers = set()
    for chunk in raw.replace(";", ",").split(","):
        number = chunk.strip().replace(" ", "").replace("-", "")
        if not number:
            continue
        if not E164.match(number):
            raise CalleError(
                f"CALLE_ALLOWED_NUMBERS contains {chunk.strip()!r}, which is not E.164. "
                "An allowlist entry that cannot match is an allowlist entry that "
                "silently blocks the number you meant to permit."
            )
        numbers.add(number)
    return frozenset(numbers)


class CalleClient:
    """Places real calls. Every instantiation of this class costs credits."""

    places_real_calls = True

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        poll_interval: float = POLL_INTERVAL_SECONDS,
        poll_timeout: float = POLL_TIMEOUT_SECONDS,
        allowed_numbers: frozenset[str] | None = None,
    ) -> None:
        if not api_key:
            raise CalleError(
                "CALLE_API_KEY is required for a live run. OUTCOME reads it from the "
                "environment only and never writes it to disk."
            )
        self.api_key = api_key
        self.base_url = assert_trusted_base_url(base_url)
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        # The last line before the network. Enforced here rather than in the
        # planner so that no planning bug, bad referral, or hand-edited phone
        # book can reach a number the operator did not sanction. An empty
        # allowlist means unrestricted, which is why the CLI makes the operator
        # opt out of it explicitly rather than by leaving a variable unset.
        self.allowed_numbers = allowed_numbers or frozenset()

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        req = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise CalleError(f"CALL-E returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise CalleError(f"Could not reach CALL-E: {exc.reason}") from exc

    def create_call(self, request: CallRequest) -> dict[str, Any]:
        return self._request(
            "POST", CREATE_CALL_PATH, request.payload(), request.idempotency_key()
        )

    def get_call(self, call_id: str) -> dict[str, Any]:
        return self._request("GET", GET_CALL_PATH.format(call_id=call_id))

    def assert_dialable(self, phone: str) -> None:
        if not E164.match(phone):
            raise CalleError(f"{phone!r} is not an E.164 number; refusing to dial it.")
        if self.allowed_numbers and phone not in self.allowed_numbers:
            raise CalleError(
                f"{phone} is not in CALLE_ALLOWED_NUMBERS. Refusing to dial it. "
                "Add it to the allowlist if you meant to call it."
            )

    def ping(self) -> dict[str, Any]:
        """Verify the credential without spending a call.

        `GET /v1/goals` is read-only and is the documented way to check
        authentication against CALL-E. Reaching for `POST /v1/calls` to find out
        whether a key works costs a phone call and somebody's afternoon.
        """
        return self._request("GET", "/v1/goals?limit=1")

    def place(self, request: CallRequest) -> CallOutcome:
        self.assert_dialable(request.phone)
        created = self.create_call(request)
        call_id = str(created.get("id") or "")
        if not call_id:
            raise CalleError(f"CALL-E did not return a call id: {created!r}")
        final = self._wait(call_id)
        return CallOutcome(
            call_id=call_id,
            status=str(final.get("status", "failed")).lower(),
            structured=_first_structured_result(final),
            raw=final,
        )

    def _wait(self, call_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.poll_timeout
        while True:
            result = self.get_call(call_id)
            if str(result.get("status", "")).lower() in TERMINAL_STATUSES:
                return result
            if time.monotonic() >= deadline:
                raise CalleError(
                    f"Polling timed out for call {call_id}. The call may still be running. "
                    "Reuse this call id rather than creating a second one."
                )
            time.sleep(self.poll_interval)


def _first_structured_result(call: dict[str, Any]) -> dict[str, Any]:
    for recipient in call.get("recipients") or []:
        structured = recipient.get("structured_result")
        if isinstance(structured, dict):
            return structured
    structured = call.get("structured_result")
    return structured if isinstance(structured, dict) else {}


# --------------------------------------------------------------------------
# Dry run
# --------------------------------------------------------------------------


class DryRunCalleClient:
    """Renders the request that would be sent and refuses to send it.

    The default mode for a first run against real phone numbers: the operator
    reads the exact task text the caller will speak before any credit is spent.
    """

    places_real_calls = False

    def __init__(self) -> None:
        self.requests: list[CallRequest] = []

    def place(self, request: CallRequest) -> CallOutcome:
        self.requests.append(request)
        return CallOutcome(
            call_id=f"dryrun_{request.idempotency_key()[-8:]}",
            status="failed",
            structured={
                "reached": False,
                "verdict": "no_answer",
                "facts": ["Dry run: no call was placed."],
                "blockers": ["dry_run"],
                "referrals": [],
                "offer": None,
            },
            raw={"dry_run": True, "payload": request.payload()},
        )


# --------------------------------------------------------------------------
# Mock
# --------------------------------------------------------------------------


class MockCalleClient:
    """Replays a scripted scenario.

    A scenario entry matches on phone number and on how many times that number
    has already been dialled, so a scenario can say "nobody answers the first
    time, and on the second attempt they pick up" without the engine knowing it
    is being played to.
    """

    places_real_calls = False

    def __init__(self, scenario: dict[str, Any]) -> None:
        self.scenario = scenario
        self.responses: list[dict[str, Any]] = list(scenario.get("responses") or [])
        self.attempts: dict[str, int] = {}
        self.placed: list[CallRequest] = []

    @classmethod
    def from_file(cls, path: str) -> "MockCalleClient":
        with open(path, encoding="utf-8") as handle:
            return cls(json.load(handle))

    def place(self, request: CallRequest) -> CallOutcome:
        self.placed.append(request)
        attempt = self.attempts.get(request.phone, 0) + 1
        self.attempts[request.phone] = attempt
        entry = self._match(request.phone, attempt)
        if entry is None:
            return CallOutcome(
                call_id=f"mock_{len(self.placed):03d}",
                status="failed",
                structured={
                    "reached": False,
                    "verdict": "no_answer",
                    "facts": [],
                    "blockers": ["No scripted response for this number."],
                    "referrals": [],
                    "offer": None,
                },
                raw={"mock": True, "unmatched": True},
            )
        return CallOutcome(
            call_id=entry.get("call_id") or f"mock_{len(self.placed):03d}",
            status=str(entry.get("status", "completed")),
            structured=dict(entry.get("structured") or {}),
            raw={"mock": True, "entry": entry, "payload": request.payload()},
        )

    def _match(self, phone: str, attempt: int) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        for entry in self.responses:
            if entry.get("phone") != phone:
                continue
            wanted = entry.get("attempt")
            if wanted is None:
                best = best or entry
            elif int(wanted) == attempt:
                return entry
        return best
