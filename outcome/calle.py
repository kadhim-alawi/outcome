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


class CalleCreateError(CalleError):
    """CALL-E never accepted the request, so no call exists and no phone rang.

    Worth its own type because it is the one failure where the safe assumption
    flips. Everywhere else "we do not know whether it rang" means assume it
    did; here we know it did not, so the ledger claim can be released and the
    action costs nothing against the budget.
    """


class CallePollError(CalleError):
    """The call was created and we could not learn how it ended.

    Carries the id so a human can go and look it up rather than guess.
    """

    def __init__(self, message: str, call_id: str) -> None:
        super().__init__(message)
        self.call_id = call_id


# --------------------------------------------------------------------------
# The evidence schema OUTCOME asks every call to fill in
# --------------------------------------------------------------------------

# CALL-E accepts a documented subset of JSON Schema, and three of its rules
# shaped this structure. Learned from a live 400, then confirmed against the
# calls guide:
#
# 1. A `type` is one value. `["object", "null"]` is `anyOf` wearing a hat, and
#    is rejected. Absence is expressed as an empty string or an empty array.
# 2. `summary`, `status`, `transcript`, `call_id` and timing fields are
#    reserved recipient response names. Hence `what_is_offered`.
# 3. "If CALL-E cannot produce a schema-valid result from the evidence, the
#    public structured_result is null" — all or nothing. So `required` holds
#    the single field a call cannot be useful without. Requiring `facts` would
#    trade a partial answer for no answer at all whenever a caller came back
#    with a verdict and nothing quotable.
#
# Prices and dates are strings rather than numbers, for the same reason: a
# number has no way to say "they never quoted one", and 0 is a lie a budget
# check would happily accept. `evidence.parse_money` reads them back.
EVIDENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["verdict"],
    "properties": {
        "reached": {
            "type": "string",
            "enum": ["yes", "no", "unknown"],
            "description": (
                "yes only if a person actually spoke with you. no if nobody did. "
                "unknown if you cannot tell."
            ),
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
                "summarise or add anything they did not say. Empty if nothing was said."
            ),
        },
        "blockers": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Reasons given for why the objective cannot be met here. Empty if none."
            ),
        },
        "referrals": {
            "type": "array",
            "description": (
                "Other organisations or departments they told you to contact, with the "
                "number they gave. Empty if none were offered. Never invent a number."
            ),
            "items": {
                "type": "object",
                "required": ["org_name"],
                "properties": {
                    "org_name": {"type": "string", "description": "Who they told you to call."},
                    "phone": {
                        "type": "string",
                        "description": (
                            "The number they read out, in E.164 such as +447700900123. "
                            "Empty string if they did not give one."
                        ),
                    },
                    "role": {"type": "string", "description": "What that organisation does."},
                    "reason": {"type": "string", "description": "Why they sent you there."},
                },
                "additionalProperties": False,
            },
        },
        "offer": {
            "type": "object",
            "description": (
                "A concrete proposal, if one was made. Leave every field empty if none was."
            ),
            "properties": {
                "what_is_offered": {
                    "type": "string",
                    "description": (
                        "What they proposed, in a few words. Empty string if they "
                        "proposed nothing."
                    ),
                },
                "price": {
                    "type": "string",
                    "description": (
                        "The total amount only, digits and decimal point, such as 438.00. "
                        "No currency symbol. Empty string if no price was quoted."
                    ),
                },
                "currency": {
                    "type": "string",
                    "description": "Three-letter code such as USD. Empty string if not stated.",
                },
                "eta": {
                    "type": "string",
                    "description": (
                        "The date they committed to, as YYYY-MM-DD. Empty string if no "
                        "date was given."
                    ),
                },
                "reference": {
                    "type": "string",
                    "description": (
                        "Any reference, order or booking number they gave. Empty string "
                        "if none."
                    ),
                },
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}

# --------------------------------------------------------------------------
# Checking a schema against what CALL-E documents as supported
# --------------------------------------------------------------------------

SUPPORTED_TYPES = frozenset(
    {"object", "string", "number", "integer", "boolean", "array"}
)
UNSUPPORTED_KEYWORDS = (
    "$ref", "oneOf", "anyOf", "allOf", "not", "patternProperties",
    "additionalItems", "format", "if", "then", "else", "dependencies",
)
# Reserved recipient response field names, per the calls guide.
RESERVED_RECIPIENT_FIELDS = frozenset(
    {"summary", "status", "transcript", "call_id", "started_at", "ended_at", "duration"}
)


def validate_result_schema(schema: Any, path: str = "$", top_level: bool = True) -> list[str]:
    """Check a result schema against the subset CALL-E documents as supported.

    Written after a live run was refused with HTTP 400 for a nullable type. The
    request never reached the phone, which is the good case; the bad case is
    finding out at all, when the rules are published and checkable in advance.
    Preflight runs this, so a bad schema costs nothing and no waiting.
    """
    problems: list[str] = []
    if not isinstance(schema, dict):
        return [f"{path}: expected a schema object, got {type(schema).__name__}."]

    for keyword in UNSUPPORTED_KEYWORDS:
        if keyword in schema:
            problems.append(f"{path}: {keyword!r} is not supported by CALL-E.")

    declared = schema.get("type")
    if isinstance(declared, list):
        problems.append(
            f"{path}.type: {declared!r} is a union. CALL-E takes one type; express "
            "absence with an empty string or an empty array instead of null."
        )
    elif isinstance(declared, str) and declared not in SUPPORTED_TYPES:
        problems.append(f"{path}.type: {declared!r} is not one of {sorted(SUPPORTED_TYPES)}.")
    elif declared is None:
        problems.append(f"{path}: no 'type' declared.")

    if schema.get("additionalProperties") is True:
        problems.append(f"{path}: additionalProperties must be false.")

    if declared == "object":
        properties = schema.get("properties") or {}
        if not isinstance(properties, dict):
            problems.append(f"{path}.properties: expected an object.")
            return problems
        if top_level:
            for name in sorted(set(properties) & RESERVED_RECIPIENT_FIELDS):
                problems.append(
                    f"{path}.properties.{name}: {name!r} is a reserved recipient "
                    "response field name. Use a different one."
                )
        for name in sorted(schema.get("required") or []):
            if name not in properties:
                problems.append(f"{path}.required: {name!r} is not in properties.")
        for name, child in properties.items():
            problems.extend(validate_result_schema(child, f"{path}.{name}", top_level=False))

    if declared == "array":
        items = schema.get("items")
        if items is None:
            problems.append(f"{path}.items: an array needs items.")
        else:
            problems.extend(validate_result_schema(items, f"{path}[]", top_level=False))

    return problems


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
    # CALL-E routes and language-checks per recipient. Omitted entirely when
    # unset rather than sent as null, because the recipient object is strict.
    locale: str | None = None
    region: str | None = None

    def payload(self) -> dict[str, Any]:
        recipient: dict[str, Any] = {"phones": [self.phone]}
        if self.locale:
            recipient["locale"] = self.locale
        if self.region:
            recipient["region"] = self.region
        return {
            "task": self.task,
            "recipients": [recipient],
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
        """Dial, and be precise about which half failed if it does.

        Everything before CALL-E accepts the request means no phone rang;
        everything after means one did and we may not know how it went. Callers
        act on that difference, so it is carried in the exception type rather
        than left for them to infer from a message.
        """
        self.assert_dialable(request.phone)
        try:
            created = self.create_call(request)
        except CalleError as exc:
            raise CalleCreateError(str(exc)) from exc
        call_id = str(created.get("id") or "")
        if not call_id:
            raise CalleCreateError(f"CALL-E did not return a call id: {created!r}")
        try:
            final = self._wait(call_id)
        except CalleError as exc:
            raise CallePollError(str(exc), call_id) from exc
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
