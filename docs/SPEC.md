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

"Read the requirements out of this" parses the sentence into a goal plus
constraint rows (`interpret.py`, `POST /api/interpret`). **The parse is never
acted on silently.** It lands in editable fields — kind, description, value,
must/prefer — because a budget that quietly failed to parse is a budget that
will never block anything, and the user is the only one who can catch it.

The parse **replaces** the requirement rows rather than merging with them, for
the same reason the API does (§12): a stale requirement sitting beside a fresh
reading of the sentence is a limit the user thinks they removed.

Below it, the phone book (name, E.164, role) and the call budget are editable
too. One organisation is enough — that is the point of the product.

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

`kind` ∈ `budget` · `minimum` · `deadline` · `required_fact` · `preference` · `forbidden`.
`hard: true` disqualifies an offer; `hard: false` only ranks it. `value` is a
bare number for `budget` and `minimum`, an ISO date for `deadline`, a field name
for `required_fact`, a term for the rest.

`budget` is a ceiling, `minimum` a floor. Which one is present also decides what
"better" means when ranking acceptable offers — see §9.

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
quoted*, which reads as unknown — never as free, and never as generous.

`price` is *the amount at stake*, not *the cost*. Whether more or less is better
is decided by the constraints, so an outcome that recovers a refund and one that
buys a replacement are the same shape with the comparison reversed.

### SQLite schema (`outcome/store.py`)

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
unit. `events` is separate because the UI replays it.

`calls` is the one that matters, and it is written **before** the dial, not
after. A process that forgets what it dialled will dial again, and the person on
the other end has no way to know the second call is a bug. Recording it
afterwards leaves exactly the window that matters uncovered: the crash that
happens while the phone is ringing.

The sequence is claim, dial, complete, and each state means something specific
on restart:

| Ledger row | Meaning | What the engine does |
|---|---|---|
| absent | never dialled | dial |
| claimed, no result | started, outcome unknown | **refuse to dial**; park on `AWAITING_USER` |
| claimed + result | finished | replay the stored result; dial nothing |

A parked action stays `RUNNING`, not `FAILED`. `FAILED` is not resumable, so
marking it failed would make the operator's `--resolve` a no-op and throw away a
call that was already paid for.

Clearing an unresolved entry is a human decision with two answers, and
`outcome calls` names both. `--resolve` records it as `blocked`, deliberately
not `no_answer`: `no_answer` is retryable, and re-ringing somebody who may have
just spent five minutes with the agent is the wrong move. `--forget` deletes the
claim so the number can be dialled, and is only correct when the operator has
established that no call was placed.

---

## 5. Outcome state machine

```
                    ┌─────────┐
                    │  DRAFT  │
                    └────┬────┘
                         │ run()
                         ▼
   ┌───────────────► WORKING ◄──────────────┐
   │                 │ │ │ │                │
   │      approve()  │ │ │ │  reject()      │
   │                 │ │ │ └────────────────┘
   │                 │ │ │
   │                 │ │ └──► AWAITING_WINDOW  (the recipients' working day
   │                 │ │      ▲   │             has not started; run() resumes)
   │                 │ │      └───┘
   │                 │ │
   │                 │ └────► AWAITING_USER    (an action the engine cannot
   │                 │                          execute alone, or a call whose
   │                 ▼                          outcome is unknown)
   └──────── AWAITING_APPROVAL
                     │
      ┌──────────────┼──────────────┐
      ▼              ▼              ▼
  RESOLVED       ABANDONED        FAILED
```

`RESOLVED` · `ABANDONED` · `FAILED` are terminal; `resolution` is written once
on entry and never revised. `AWAITING_WINDOW` and `AWAITING_USER` are **not**
terminal — the run is a value, parked, and `run()` picks it up where it stopped.

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

### 7.3 The number allowlist

`CALLE_ALLOWED_NUMBERS`, enforced inside `CalleClient.place` rather than beside
it. The frontier grows from numbers given on calls, so a referral reaches the
dialler without passing through any form the operator filled in — the check has
to sit on the last line before the network, where no planning bug, bad referral
or hand-edited phone book can get past it. An entry that is not E.164 is an
error rather than a silent drop: an allowlist entry that cannot match is one
that silently blocks the number you meant to permit.

`--live` refuses to start without an allowlist unless `--allow-any-number` is
passed explicitly. For a first live run, put only your own number in it.

### 7.4 The calling window

`outcome/window.py`. Hours, days and an IANA timezone — the **recipients'**
timezone, not the operator's. Calling a depot at 03:00 is legal and awful, and
it is the failure an autonomous agent falls into most easily, because nothing in
the loop knows what time it is where the phone is.

Checked immediately before every dial. A closed window **parks** the run on
`AWAITING_WINDOW` rather than failing it, and the action stays `PLANNED` so the
next `run()` resumes that exact call — including an approval already given,
which is kept rather than re-asked. `next_open` walks forward a day at a time
rather than doing arithmetic on an offset, because the answer has to survive a
DST transition.

The guard keys off `transport.places_real_calls`, so it applies to the live
client and not to a replay. Enforcing a Mon–Fri window on the mock would make
the demo unrunnable at weekends and the test suite dependent on the day it runs,
while protecting nobody. Unknown transports default to enforcing: a guard that
fails open is not a guard.

`--live` refuses to start on an outcome with no window.

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

Ranking among acceptable offers: fewest soft violations, then the better
amount, then the earlier date. "Better" follows the constraints — a `budget`
makes cheaper better, a `minimum` makes larger better. With both, or neither,
cheaper wins: a cost ceiling is the commoner case, and a run carrying both is
asking for a price inside a band rather than at an extreme.

An unquoted amount sorts **last in either direction**.

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
| Outside the calling window | Park on `AWAITING_WINDOW`. Resume the same call, with its approval, when it opens |
| Number not on the allowlist | Refuse at the transport. In `--live`, caught before the run starts |
| Crash mid-call | The ledger claim survives without a result. Refuse to re-dial; a human says which happened |
| Restart after a completed call | Replay the stored result. Dial nothing |
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
| `GET` | `/api/scenarios` | | `[{name, title, description, featured, outcome}]`, featured first |
| `POST` | `/api/interpret` | `{text}` | `{goal, constraints, source}` — for the form to show back |
| `POST` | `/api/runs` | `{scenario, outcome?}` | `{outcome, events, event_count, live}` |
| `GET` | `/api/runs/{id}` | | same snapshot |
| `POST` | `/api/decide` | `{run_id, approve, reason?}` | snapshot of **events since the decision** |

The server is mock-backed and has no store; the CLI is the surface that carries
`--store`, `preflight` and `calls`.

A run advances to completion or to the approval gate inside one request; the
page animates the returned event list. Streaming would look identical on screen
and would mean holding a socket open for the length of a phone call.

`scenario` is resolved inside `scenarios/` and re-checked after resolution —
it arrives from an HTTP request, and `../../etc/passwd` is otherwise a file read.

When `outcome` is present it **replaces** the scenario's definition rather than
merging into it. A partial merge would let a form that dropped a constraint
inherit it back from the file, and the user would be running against limits they
believed they had deleted.

`outcome/loader.py` is where untrusted input becomes a run, so it is where phone
numbers are checked as strict E.164 (no normalising — a guessed digit dials a
stranger), duplicates are rejected, budget and minimum values must parse as
numbers, deadlines as ISO dates, and the call budget is capped at 25 total and 5
per organisation. A limit that fails to parse is a limit that never blocks
anything, so it is an error rather than a warning.

*Not built:* no auth. Bind to localhost. See §14.

---

## 13. Repository structure

```
outcome/{models,constraints,evidence,planner,approval,window,engine,calle,store,
         interpret,loader,cli,server}.py
scenarios/*.json         outcome definition + scripted responses for the mock
web/index.html           the form and the timeline UI
contrib/skills/          the outcome-completion-agent package for the upstream PR
tests/                   85 tests, stdlib unittest, no network
docs/                    this file, the landscape teardown, the demo script
```

CLI surface: `run` (with `--dry-run` / `--live` / `--store`), `preflight`
(checks a live run without placing one), `calls` (the ledger, after a crash).

---

## 14. What is not built yet

Honest list, in the order it should be closed.

1. **A live call has never been placed.** `--live` is implemented against the
   documented v0.6.0 contract and exercised only through `DryRunCalleClient`.
   The first live run needs `--dry-run` read line by line first, then a single
   call to a number we control, then the full scenario. Budget 6 of the 20
   free credits for this and request the additional 200 now — the form takes
   one to five business days.
2. **Server has no auth, and no store.** Localhost only. The browser demo does
   not persist runs; the CLI does.
3. **`ASK_USER` parks the run and nothing in the UI resumes it.** The engine
   reaches it after an unresolved call; the CLI's `calls` command is the way
   out, and the browser has no equivalent.
4. **`LLMInterpreter` is untested against the live API.** It falls back to rules
   on any failure, so a break degrades the parse rather than the run — but the
   success path has only been exercised offline.
5. **One window per outcome, not per organisation.** Per-organisation is right
   the first time a run spans two continents. Until then one window keeps the
   model honest, and a single wrong timezone is easier to spot than five.

Closed since the first draft: the form is editable and takes a phone book (§3.1);
a second scenario of a different shape runs on the same engine (`bill-dispute`,
which added the `minimum` constraint kind and nothing else); the upstream skill
package is written and passes that repository's validator (§15); SQLite and the
write-ahead call ledger (§4); the number allowlist (§7.3); the calling window
(§7.4); and `preflight`, which checks everything checkable about a live run
without placing one.

---

## 15. The `awesome-phone-call-agents` contribution

The hackathon requires a PR to
[`CALLE-AI/awesome-phone-call-agents`](https://github.com/CALLE-AI/awesome-phone-call-agents).
Judged partly on whether the contribution is *reusable by the community*, so it
should not be a copy of this demo.

**Built.** `contrib/skills/outcome-completion-agent/` — a skill, not an app,
packaging the pattern rather than the bakery story:

```
outcome-completion-agent/
├── SKILL.md                            the loop, the gate, the budget
├── references/
│   ├── evidence-schema.md              §7.1 — the reusable part
│   ├── constraint-evaluation.md        §9, incl. why unknown does not block
│   ├── approval-gate.md                §10, incl. the negation problem
│   ├── safety.md                       disclosure, masking, E.164, cancellation
│   └── examples.md                     a full run, a budget stop, two failure modes
└── scripts/
    ├── check_evidence_schema.py        validates a structured_result, no network
    └── test_check_evidence_schema.py   19 tests
```

Verified against a fresh clone of the upstream repository at `100eb25`:

```
$ cp -r contrib/skills/outcome-completion-agent <clone>/skills/
$ python3 scripts/validate_repository.py
Repository validation passed.
$ python3 scripts/check_branch_name.py --branch feat/outcome-completion-agent
Branch name follows docs/git-naming-conventions.md
```

**Still to do:** fork, copy the directory in, commit on
`feat/outcome-completion-agent`, open the PR, and put its URL in the Devpost
submission. This session has read-only access to that repository.

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

- **Recording and disclosure by jurisdiction.** Disclosure is in every script,
  but the wording is not jurisdiction-aware.
- **Where a soft constraint should stop being soft.** Three soft violations on
  an otherwise acceptable offer probably deserves the approval screen even when
  nothing hard is breached. Currently it does not.
- **Whether the user should be able to raise the budget mid-run.** Today the
  answer is no: the run abandons and reports. That is the safe default, and it
  may be the wrong product.
