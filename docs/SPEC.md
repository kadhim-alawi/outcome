# OUTCOME — build specification

Status: the engine, adapter, CLI, server and UI described here are built and
tested. Sections marked **not built** are specified but not implemented; they
are listed together in [§14](#14-what-is-not-built-yet).

---

## 1. The one-sentence product

> A user creates an *outcome*, not a call. The agent decides who to phone, phones
> them, and keeps going until the user's stated conditions are met or its call
> budget runs out.

Everything below follows from three commitments:

1. **The set of people to call is not known when the run starts.** It grows from
   what earlier calls said. This is the technical centre of the project.
2. **A successful call is not a successful outcome.** Acceptance is decided by
   deterministic rules over the user's constraints, not by the caller's mood.
3. **Asking is free; agreeing is not.** Information gathering is unattended.
   Commitment is gated on a human, every time, with no exception path.

---

## 2. Decisions already taken

| Decision | Chosen | Why |
|---|---|---|
| Front end | Server-rendered single page, vanilla JS | The deliverable is a 3-minute video and a reviewable repo. A Flutter target adds a toolchain to every reviewer's machine and buys nothing on screen. Revisit only if a mobile build is wanted after the hackathon. |
| Backend | Python 3.11, standard library only | Zero install for a judge. `urllib` is enough for CALL-E; `http.server` is enough for one demo viewer. |
| Planner | Deterministic frontier search, LLM optional | The loop that spends the user's money and CALL-E credits should be readable and testable. An LLM writes goal interpretation (`interpret.py`); it does not choose who to dial. |
| Persistence | In-memory + JSON round trip; SQLite specified | A run is a value object that serialises cleanly (proven in `tests/test_engine.py::Persistence`). SQLite is a drop-in behind the same shape when runs need to outlive a process. |
| Transport | One protocol, three implementations | The mock is not a test double bolted on afterwards — it is how the demo runs. The engine cannot tell the difference. |

---

## 3. Screens

Three, and only three. The whole product is one page.

### 3.1 Create outcome

```
WHAT NEEDS TO HAPPEN?
┌────────────────────────────────────────────────────┐
│ Get a replacement pallet of 500 insulated shipping  │
│ boxes for the crushed delivery on order BK-7741.    │
└────────────────────────────────────────────────────┘

[ budget · Total cost at or under USD 500 ]  [ deadline · on or before 2026-09-11 ]

SCENARIO  ▾ Damaged pallet, replacement needed before Friday        [ Start ]
```

The free-text box is parsed into a goal plus constraint chips
(`interpret.py`). **The chips are always shown before the run starts.** A
budget that silently failed to parse is a budget that never blocks anything, so
the parse is surfaced rather than trusted.

*Not built:* the chips are display-only. They must become editable, and the
form must accept a starting phone book (name + E.164 + role) rather than taking
it from the scenario file. See §14.

### 3.2 Timeline

One row per thing that happened, in the order it happened:

| Row | Shows |
|---|---|
| `☎ Call X — can they fix this?` | masked number, attempt count, a **commits you** badge where relevant |
| `X — blocked` | the facts stated, blockers in red |
| `New lead: Y` | masked number and the reason the last call gave for it |
| offer card | summary, price, ETA, and a per-constraint ✓ / ✗ / ~ verdict |
| approval card | the question, the checks, and what was turned down |
| result card | headline, reference, constraint report, calls used, every party touched |

Rules the UI must keep:

- **Never show an unmasked phone number.** `mask_phone` at the boundary; the
  engine emits masked numbers in events already.
- **A soft violation is `~` in amber, not `✗` in red.** Rendering "no reference
  number was given" with the same mark as "$112 over your limit" teaches the
  user that the marks mean nothing, on the one screen where they must.
- **A lead renders after the call that produced it.** Emitting it first reads as
  though the agent already knew where to go.
- **No chain of thought.** Rows are actions and evidence. The planner's
  reasoning is not a user-facing artefact.

### 3.3 Approval

```
APPROVAL NEEDED
Accept 500 insulated shipping boxes, local van delivery from
Brightwater Depot for USD 438.00, arriving 2026-09-10?

  ✓ USD 438.00 is within the USD 500.00 limit.
  ✓ 2026-09-10 is on or before the 2026-09-11 deadline.
  ~ The call did not produce a reference.

  Turned down: 500 insulated shipping boxes, next-day courier — USD 612.00

  [ Approve ]  [ Decline ]
```

`Turned down` is required, not decoration. An approval screen showing only the
winner asks the user to trust a search they cannot see.

---

## 4. Domain model

`outcome/models.py`. Field names below are the wire format: the JSON in
`Outcome.to_dict()` is what the API returns and what a database row would hold.

### Outcome

| Field | Type | Notes |
|---|---|---|
| `id` | `out_<hex12>` | |
| `goal` | text | One sentence, imperative, constraints stripped out |
| `status` | enum | §5 |
| `constraints` | Constraint[] | |
| `organizations` | Organization[] | The phone book, user-supplied and discovered |
| `actions` | Action[] | Append-only |
| `evidence` | Evidence[] | Append-only, one per completed call |
| `budget` | Budget | `max_calls`, `max_calls_per_org`, `max_actions` |
| `declined_offer_ids` | string[] | So "no" cannot be re-proposed |
| `resolution` | object \| null | Written once, at a terminal state |
| `pending_approval_action_id` | string \| null | |

### Constraint

`kind` ∈ `budget` · `deadline` · `required_fact` · `preference` · `forbidden`.
`hard: true` disqualifies an offer; `hard: false` only ranks it. `value` is a
bare number for `budget`, an ISO date for `deadline`, a field name for
`required_fact`, a term for the rest.

### Organization

`name`, `phone` (E.164), `role`, `discovered_by` — the action id of the call
that produced the referral, or `null` for a party the user supplied. That field
is what lets the report say *"found by the agent"*.

### Action

`type` ∈ `call` · `verify` · `ask_user` · `complete` · `abandon`.
`status` ∈ `planned` · `awaiting_approval` · `running` · `done` · `failed` · `rejected`.
A `call` carries the entire CALL-E request: `task_prompt`, `result_schema`,
`target_org_id`, plus `commits_user` / `commitment_summary` / `approved`.

### Evidence

One per completed call, never edited.

`verdict` ∈ `no_answer` · `refused` · `blocked` · `partial` · `offer` · `confirmed`,
plus `facts[]`, `blockers[]`, `referrals[]`, `offer`, `call_id`.

### Offer

`summary`, `org_id`, `price`, `currency`, `eta` (ISO date), `reference`. The
only structure a constraint can be evaluated against. `price: null` means *not
quoted*, which reads as unknown — never as free.

### SQLite schema (specified, **not built**)

```sql
CREATE TABLE outcomes (
  id TEXT PRIMARY KEY, goal TEXT NOT NULL, status TEXT NOT NULL,
  document JSON NOT NULL,                       -- Outcome.to_dict()
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  outcome_id TEXT NOT NULL REFERENCES outcomes(id),
  seq INTEGER NOT NULL, at TEXT NOT NULL, kind TEXT NOT NULL, payload JSON NOT NULL);
CREATE UNIQUE INDEX events_seq ON events (outcome_id, seq);

CREATE TABLE calls (                            -- credit ledger, one row per dial
  call_id TEXT PRIMARY KEY, outcome_id TEXT NOT NULL, action_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,         -- the duplicate-dial guard
  status TEXT NOT NULL, placed_at TEXT NOT NULL);
```

The document column holds the whole outcome because it is read and written as a
unit. `events` is separate because the UI replays it. `calls` exists so the
budget survives a restart: a process that forgets what it dialled will dial again.

---

## 5. Outcome state machine

```
                    ┌─────────┐
                    │  DRAFT  │
                    └────┬────┘
                         │ run()
                         ▼
   ┌───────────────► WORKING ◄──────────────┐
   │                 │  │  │                │
   │      approve()  │  │  │  reject()      │
   │                 │  │  └────────────────┘
   │                 │  │
   │                 │  └──────────► AWAITING_USER   (an action the engine
   │                 │                                cannot execute alone)
   │                 ▼
   └──────── AWAITING_APPROVAL
                     │
      ┌──────────────┼──────────────┐
      ▼              ▼              ▼
  RESOLVED       ABANDONED        FAILED
```

`RESOLVED` · `ABANDONED` · `FAILED` are terminal; `resolution` is written once
on entry and never revised.

`run()` is re-entrant. Calling it while parked on approval must place no call —
that is `ApprovalGate::test_no_call_is_placed_while_waiting_for_approval`.

The engine never blocks waiting for a human. An approval may take a day; the run
is a value, not a thread.

---

## 6. The planner contract

```python
class Planner(Protocol):
    def next_action(self, outcome: Outcome) -> Action: ...
```

Pure. Reads the outcome, returns one action, mutates nothing, and never touches
the network. That is what allows the same planner to drive a unit test and a
live run, and what makes every decision reviewable after the fact.

`FrontierPlanner`, highest priority first:

1. **A confirmed offer exists** → `COMPLETE`.
2. **An acceptable offer exists and is not locked in** → a `CALL` back to accept
   it, `commits_user=True`. Finding a good answer and failing to secure it is
   the one result worse than finding nothing.
3. **Budget exhausted** → `ABANDON`, naming the budget.
4. **Somebody never called** → `CALL` them. Insertion order, so a referral from
   the call that just happened lands ahead of a user-supplied party not yet
   reached — the warm lead is the better next move.
5. **Somebody who did not answer, under the per-party cap** → retry.
6. **Nothing left** → `ABANDON`, reporting everything learned.

`shop_all_leads=False` by default: stop at the first offer satisfying every hard
constraint rather than canvassing for a better one. With a 20-call account,
exhaustive search is not a neutral default. Set `True` when credits are cheap.

---

## 7. CALL-E integration

Developer API **v0.6.0**, base `https://api.heycall-e.com`.

```
POST /v1/calls          Authorization: Bearer $CALLE_API_KEY
                        Idempotency-Key: outcome-<sha256(payload)[:32]>
  { "task": "<spoken instruction>",
    "recipients": [{"phones": ["+15550100001"]}],
    "recipient_result_schema": <evidence schema §7.1>,
    "metadata": {"workflow": "outcome", "outcome_id": ..., "action_id": ...} }

GET /v1/calls/{call_id} -> { "id", "status", "recipients": [
                               {"phones": [...], "status", "structured_result": {...}} ] }
```

`status` ∈ `queued` · `in_progress` · `completed` · `failed` · `canceled`.
Poll every 5s to a 900s ceiling; a timeout raises rather than re-creating the
call, because a second `POST` is a second phone ringing.

**Idempotency key is derived from the request payload, not from the attempt.**
Re-submitting an unchanged action cannot place a second call. A deliberate
retry differs in `attempt`, which changes the task text, which changes the key.

**Host allowlist.** `api.heycall-e.com` and `api.staging.heycall-e.com`, https
only. The bearer token is on every request, so the destination is not a free
parameter — `CALLE_BASE_URL` exists to reach staging, not to point a live
credential at a collector.

### 7.1 The evidence schema

Every call is asked to fill the same structure (`calle.EVIDENCE_SCHEMA`). This
is the contract that makes calls composable, and the part most worth reusing:

```jsonc
{
  "reached":   true,                       // did a person actually speak
  "verdict":   "blocked",                  // no_answer|refused|blocked|partial|offer|confirmed
  "facts":     ["Out of stock until the 30th."],
  "blockers":  ["No stock of insulated boxes until 30 September."],
  "referrals": [{"org_name": "Northgate Distribution",
                 "phone": "+15550100002",  // E.164 or dropped
                 "role": "Regional distributor",
                 "reason": "They hold the identical box."}],
  "offer":     {"summary": "...", "price": 438.0, "currency": "USD",
                "eta": "2026-09-10", "reference": "BWD-48291"}
}
```

Parsing is defensive (`evidence.py`), because this is the least trustworthy
input in the system — a model's reading of a phone conversation:

- `price` accepts `438`, `"438"`, `"$438.00"`, `"USD 1,438"`; anything else is
  `None`, i.e. *unknown*. Guessing `0` would sail a quote past a budget limit.
- A referral without a valid E.164 number is **dropped**. A pointer that cannot
  be dialled is not a lead, and keeping it puts an unactionable entry in front
  of the planner forever.
- A call the provider did not complete is never read as testimony, whatever the
  structured block claims.
- An empty `offer: {}` is not an offer.

### 7.2 Credits

A hackathon account starts with 20 calls. Defaults: `max_calls=6` per outcome,
`max_calls_per_org=2`. The budget is checked **immediately before dialling**,
not when planning, so an approval that sat overnight cannot spend a credit the
budget no longer has.

---

## 8. Call scripts

Two shapes, both in `planner.py`, both opening with the AI disclosure.

### 8.1 Gathering — may ask, may not agree

Disclosure · who is being called · the overall goal · the user's requirements ·
*"you were given this number by X"* when following a referral · the objective
for this call · base rules · and:

> You are NOT authorised to agree to anything, accept any price, place any
> order, or cancel anything on this call. If they offer something, record it as
> an offer and say you will confirm shortly. Saying yes is not your decision to
> make.

### 8.2 Commit — the one call that may say yes

> YOU ARE AUTHORISED TO ACCEPT EXACTLY THIS AND NOTHING ELSE:
>   500 insulated shipping boxes, local van delivery
>   Price: USD 438.00
>   Delivery: 2026-09-10
>
> If the terms have changed in any way — a different price, a later date, an
> added fee, a different item — do NOT accept. Record the new terms as an offer,
> set verdict to 'offer', and end the call politely. The customer will decide
> again.

The authorisation is an envelope because the user approved *that* offer, not a
renegotiated one. A caller told to "use its judgement" on changed terms is a
caller that can spend more than the user agreed to.

Base rules on every call: be brief; record only what was said; if they cannot
help, ask who can and ask for the number; never read out a credential; no
medical, legal or financial advice; if asked to stop, apologise, end the call,
and record it.

---

## 9. Constraint evaluation

`constraints.py`. Deterministic — a model decides what was said, a comparison
operator decides whether it is good enough.

| Judgement | Meaning | Blocks? |
|---|---|---|
| `satisfied` | Checked and met | no |
| `violated` | Checked and not met | **only if `hard`** |
| `unknown` | Not enough information (e.g. no price quoted) | no — surfaced at approval |
| `not_applicable` | Constraint not configured | no |

`unknown` deliberately does not block: refusing every offer that failed to
mention a detail nobody asked about would strand every run.

Ranking among acceptable offers: fewest soft violations, then cheapest, then
earliest. An unquoted price sorts **last**, not free.

---

## 10. Approval system

`commits_user`, set by the planner, is the gate. Underneath it sits a keyword
net over the call script for a planner that forgets to set it.

The net is **negation-aware**, and this is not a detail. Every gathering script
ends with "you are NOT authorised to *agree to* anything, *accept* any price, or
*cancel* anything" — three committing verbs. A naive net flags every call in the
run, the user approves six times, and the gate has taught them to click through
it. Lines carrying a negation cue (`not authorised`, `do not`, `never`, `must
not`, `cannot`, `without approval`, …) are excluded before matching.

Declining records the offer in `declined_offer_ids`, so the planner cannot
immediately re-propose it. Without that, "no" is a loop.

---

## 11. Failure and retry

| Situation | Response |
|---|---|
| Nobody answered | Retry that party once (`max_calls_per_org=2`), then move on |
| Provider returned `failed`/`canceled` | Treated as `no_answer`; never as testimony |
| They refuse or are blocked | Record the blocker, take any referral, move to the next lead |
| Offer violates a **hard** constraint | Rejected; keep working. The call succeeded, the outcome did not |
| Offer violates only **soft** constraints | Acceptable; ranked lower; the violation is shown at approval |
| Terms changed on the commit call | Caller does not accept; new terms return as an offer; user decides again |
| Referral with no dialable number | Dropped |
| Polling timeout | Raise. Never re-`POST` — that is a second phone ringing |
| Call budget reached | `ABANDON` with the full report. Never "one more try" |
| Every lead exhausted | `ABANDON` with every fact, blocker and rejected offer |

There is no silent failure mode. Both terminal states write a `resolution`
carrying the parties called, the calls used against the budget, and every offer
considered with the reason it lost.

---

## 12. HTTP API

`outcome/server.py`, standard library, mock-backed by default.

| Method | Path | Body | Returns |
|---|---|---|---|
| `GET` | `/` | | the single page |
| `GET` | `/api/mode` | | `{live: bool}` — the UI badge |
| `GET` | `/api/scenarios` | | `[{name, title, description, goal}]` |
| `POST` | `/api/runs` | `{scenario, text?}` | `{outcome, events, event_count, live}` |
| `GET` | `/api/runs/{id}` | | same snapshot |
| `POST` | `/api/decide` | `{run_id, approve, reason?}` | snapshot of **events since the decision** |

A run advances to completion or to the approval gate inside one request; the
page animates the returned event list. Streaming would look identical on screen
and would mean holding a socket open for the length of a phone call.

`scenario` is resolved inside `scenarios/` and re-checked after resolution —
it arrives from an HTTP request, and `../../etc/passwd` is otherwise a file read.

*Not built:* no auth. Bind to localhost. See §14.

---

## 13. Repository structure

```
outcome/{models,constraints,evidence,planner,approval,engine,calle,interpret,loader,cli,server}.py
scenarios/*.json         outcome definition + scripted responses for the mock
web/index.html           the timeline UI
tests/                   39 tests, stdlib unittest, no network
docs/                    this file, the landscape teardown, the demo script
```

---

## 14. What is not built yet

Honest list, in the order it should be closed.

1. **A live call has never been placed.** `--live` is implemented against the
   documented v0.6.0 contract and exercised only through `DryRunCalleClient`.
   The first live run needs `--dry-run` read line by line first, then a single
   call to a number we control, then the full scenario. Budget 6 of the 20
   free credits for this and request the additional 200 now — the form takes
   one to five business days.
2. **Constraint chips are display-only.** They must be editable before Start,
   and the form must take a starting phone book instead of reading it from the
   scenario file.
3. **SQLite.** Schema in §4. Needed before any run outlives a process — in
   particular the `calls` ledger, without which a restart re-dials.
4. **Server has no auth.** Localhost only until it does.
5. **`ASK_USER` parks the run and nothing resumes it.** The planner never emits
   one today; the moment it does, the UI needs the matching input.
6. **`LLMInterpreter` is untested against the live API.** It falls back to rules
   on any failure, so a break degrades the parse rather than the run — but the
   success path has only been exercised offline.
7. **One scenario.** A second (bill dispute or appointment hunt) would prove the
   engine is not shaped around this one story.

---

## 15. The `awesome-phone-call-agents` contribution

The hackathon requires a PR to
[`CALLE-AI/awesome-phone-call-agents`](https://github.com/CALLE-AI/awesome-phone-call-agents).
Judged partly on whether the contribution is *reusable by the community*, so it
should not be a copy of this demo.

**Proposal — a skill, not an app.** `skills/outcome-completion-agent/`, packaging
the pattern rather than the bakery story:

```
skills/outcome-completion-agent/
├── SKILL.md                          the loop, the gate, the budget
├── references/
│   ├── evidence-schema.md            §7.1 — the reusable part
│   ├── constraint-evaluation.md      §9, incl. why unknown does not block
│   ├── approval-gate.md              §10, incl. the negation problem
│   └── safety.md                     disclosure, masking, E.164, cancellation
└── scripts/
    └── check_evidence_schema.py      validates a structured_result, no network
```

Repository rules to honour (from its `CONTRIBUTING.md` and `AGENTS.md`):
English only; no `README.md` inside a skill directory; `name` matches the
directory and is lowercase-hyphenated; fictional or masked numbers only; a
dry-run path by default; explicit cancellation behaviour; branch named
`<type>/<short-kebab-summary>`, validated with `scripts/check_branch_name.py`;
and `python3 scripts/validate_repository.py` must pass before the PR opens.

Why a skill beats an app here: 40 skills and 75 apps are already in that
repository, and almost all of them are one workflow, one call. The transferable
thing we have is the *shape* — evidence, constraints, frontier, gate — which any
of those workflows could adopt. That is a contribution to the repository rather
than another entry in it.

---

## 16. Open questions

- **Time-of-day windows.** Calling a depot at 03:00 is legal and awful. `concord`
  in the reference repo gates calls on the recipient's local opening hours; this
  should too, before any live run against a business.
- **Recording and disclosure by jurisdiction.** Disclosure is in every script,
  but the wording is not jurisdiction-aware.
- **Where a soft constraint should stop being soft.** Three soft violations on
  an otherwise acceptable offer probably deserves the approval screen even when
  nothing hard is breached. Currently it does not.
- **Whether the user should be able to raise the budget mid-run.** Today the
  answer is no: the run abandons and reports. That is the safe default, and it
  may be the wrong product.
