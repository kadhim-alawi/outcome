# OUTCOME

**Don't tell it who to call. Tell it what needs to happen.**

OUTCOME is an autonomous phone-work agent built on [CALL-E](https://www.heycall-e.com/).
You give it a goal and the rules an answer has to satisfy. It works out who to
call, calls them, reads what it was told, checks it against your rules, and —
when the answer is "we can't help, try these people" — calls those people
instead. It stops when your goal is met, when you decline, or when it runs out
of the call budget you gave it.

CALL-E is a tool inside this agent. It is not the agent.

```
     goal + constraints
             │
             ▼
      ┌─────────────┐
      │   PLANNER   │◄──────────────┐
      └──────┬──────┘               │
             │ one action           │
             ▼                      │
      ┌─────────────┐               │
      │  APPROVAL   │ commits you?  │
      │    GATE     │──── yes ──► you decide
      └──────┬──────┘               │
             │ no                   │
             ▼                      │
      ┌─────────────┐               │
      │   CALL-E    │               │
      └──────┬──────┘               │
             ▼                      │
      ┌─────────────┐               │
      │  EVIDENCE   │ facts, blockers, referrals, offer
      └──────┬──────┘               │
             ▼                      │
      ┌─────────────┐               │
      │ CONSTRAINTS │ acceptable? ──┘
      └──────┬──────┘
             ▼
     resolved / abandoned
```

## What the demo actually does

A wholesale bakery takes delivery of a pallet of insulated shipping boxes.
They arrive crushed. Replacement needed before Friday, under $500. The user
supplies one phone number: the supplier.

Five calls later, without another word from the user:

| # | Who | What happened |
|---|---|---|
| 1 | Halden Packaging | Nobody answers |
| 2 | Halden Packaging | Out of stock until the 30th — *"try Northgate"* |
| 3 | Northgate Distribution | $612 with courier — **$112 over the limit, rejected** — *"our depot can do it locally"* |
| 4 | Brightwater Depot | $438, Thursday van — **meets every requirement** |
| — | you | *Accept $438 from Brightwater?* → Approve |
| 5 | Brightwater Depot | Confirmed. Reference BWD-48291 |

Two of the three organisations called were never given to the agent. It found
them on the phone.

## Quickstart

Python 3.11+, no credential, and nothing here places a call unless you ask for
`--live`.

```bash
python3 -m outcome.cli run scenarios/supplier-replacement.json     # terminal
python3 -m outcome.cli run scenarios/bill-dispute.json             # a different shape
python3 -m outcome.server                                          # http://127.0.0.1:8765
python3 -m unittest discover -s tests                              # 142 tests
```

**On Windows, first run `pip install tzdata`.** Windows ships no IANA timezone
database, so `zoneinfo` has nothing to resolve `Europe/London` against and the
calling window cannot be evaluated. `tzdata` is that database as pure data,
maintained by the CPython core developers — it is the only thing this project
needs beyond the standard library, and only there. Linux and macOS need
nothing; `pip install -r requirements.txt` is a no-op on them.

The CLI stops at the approval gate and asks. `--approve auto` answers yes,
`--approve never` answers no — the run then goes back out to look for something
else, which is worth watching once.

### Before your first live call

Four guards stand between the planner and somebody's ringing phone. Work
through them in order; none of the first three costs a credit.

**1. Read the script.** `--dry-run` renders the exact CALL-E request, including
the words the caller will speak, and places nothing.

```bash
python3 -m outcome.cli run scenarios/supplier-replacement.json --dry-run
```

**2. Preflight.** Verifies the credential with a read-only `GET /v1/goals`,
checks every number against the allowlist, reports whether the calling window
is open, and prints the first call's script in full.

```bash
export CALLE_API_KEY=...                            # dashboard.heycall-e.com/account/api-keys
export CALLE_ALLOWED_NUMBERS="+447700900123"        # your own number, to begin with
python3 -m outcome.cli preflight scenarios/supplier-replacement.json
```

**3. The allowlist.** Enforced inside `CalleClient.place`, not beside it — a
number the agent was handed mid-call reaches the dialler without passing
through any form, so the check has to sit on the last line before the network.
`--live` refuses to start without one unless you pass `--allow-any-number`.

**4. The calling window.** Per-outcome, in the recipients' own timezone. A run
started outside it **parks** rather than failing, and resumes at the same call
when the window opens. `--live` refuses to start on an outcome that has none.

```json
"call_window": {"timezone": "Europe/London", "start": "09:00",
                "end": "17:30", "weekdays": [0, 1, 2, 3, 4]}
```

Then, with a store so a crash cannot cost you a second call to the same person:

```bash
python3 -m outcome.cli run scenarios/supplier-replacement.json --live --store runs.sqlite3
```

The credential is read from the environment, never written to disk, and only
ever sent to `api.heycall-e.com` (see `ALLOWED_HOSTS` in `outcome/calle.py`).
Phone numbers in this repository are all in the `+1-555-01xx` range reserved
for fiction.

### If it crashes mid-call

The ledger is written **before** the dial, not after, because the window that
matters is the one where the phone is ringing and nothing has been recorded yet.

```bash
python3 -m outcome.cli calls --store runs.sqlite3
```

An unfinished entry means a call was started and never recorded a result, so it
may have connected. The engine refuses to dial that number again until you say
which happened:

- `--resolve KEY` — it happened. Recorded as `blocked`, not `no_answer`:
  `no_answer` is retryable, and re-ringing somebody who may have just spent five
  minutes with the agent is the wrong move. The credit is spent, the frontier
  advances, nobody is called twice for one crash.
- `--forget KEY` — it never happened. Clears the claim so the number can be
  dialled. Only correct if you actually established that.

A restart with a completed ledger entry replays the stored result and dials
nothing.

## The second scenario

The same engine, a different shape, no special casing. A sole trader's mobile bill is $87.32
higher than usual. Part of it is legitimate roaming; part is an add-on that was applied
twice. Getting the wrong part back means climbing an escalation chain *inside one company* —
customer service can only authorise $50, billing offers a $40 goodwill credit, and only
retentions can reverse the charge in full.

The constraint that drives it is a **floor**, not a ceiling: at least the $62.50 identified
as incorrect. Billing's $40 offer is a perfectly successful phone call and an unacceptable
outcome, so the agent keeps climbing.

```bash
python3 -m outcome.cli run scenarios/bill-dispute.json
```

## How it decides

**Evidence, not transcripts.** Every call returns a structured verdict —
`no_answer`, `refused`, `blocked`, `partial`, `offer`, `confirmed` — plus the
facts stated, the blockers named, any referral given, and any concrete offer.
The planner reads that log. It never reads a transcript, which is why the same
planner drives a mock run and a live one identically.

**Constraints are code, not prompts.** "Under $500" is a comparison operator in
`outcome/constraints.py`, not a sentence in a system prompt. A call that ends
happily and costs $612 is a *failed* outcome, and the agent goes back out. Hard
constraints disqualify; soft ones only rank.

**The frontier grows.** A call that ends "we can't, try Northgate on
+1-555-0100-002" adds Northgate to the set of parties worth calling. That is
the difference between an agent and a dialler, and it is the reason the run
can't be written down in advance.

**Asking is free, agreeing is not.** Information-gathering calls run
unattended and are explicitly told they have no authority to agree to anything.
Exactly one call per run can say yes, it is gated on your approval, and its
script names the price and the date it is allowed to accept — if the terms have
moved by the time it connects, it is told to walk away rather than use its
judgement.

**It stops.** The call budget is checked immediately before every dial, not
after, so an approval that sat overnight cannot spend a credit the budget no
longer has. A CALL-E hackathon account holds 20 calls; the default budget is 6
per outcome and 2 per organisation.

**It waits rather than ringing at 03:00.** The calling window is the failure an
autonomous agent falls into most easily, because nothing in the loop knows what
time it is where the phone is. A closed window parks the run — including an
approval already given, which is kept rather than re-asked.

**Which direction is "better" comes from the constraints.** A `budget` makes
cheaper better; a `minimum` makes larger better. Buying a replacement and
recovering a refund are the same machinery pointed the other way — which is
what the second scenario is there to prove.

## Layout

```
outcome/
  models.py       Outcome, Constraint, Action, Evidence, Offer, Organization
  constraints.py  deterministic accept/reject, and why
  evidence.py     structured_result -> Evidence, defensively
  planner.py      frontier search + the call scripts
  approval.py     what needs a human, and the negation-aware safety net
  window.py       when it is acceptable to dial, in the recipients' timezone
  engine.py       the loop
  calle.py        CALL-E v0.6.0 adapter: live, dry-run, mock, number allowlist
  store.py        SQLite, and the write-ahead call ledger
  interpret.py    one sentence -> goal + constraints (rules, or an LLM)
  cli.py          run, preflight, calls
  server.py       watch a run in a browser
scenarios/        scripted runs for the mock transport
web/index.html    the form and the timeline UI
contrib/skills/   the outcome-completion-agent skill, for the upstream PR
docs/SPEC.md      the build specification
```

## The upstream contribution

The hackathon requires a PR to
[`CALLE-AI/awesome-phone-call-agents`](https://github.com/CALLE-AI/awesome-phone-call-agents).
`contrib/skills/outcome-completion-agent/` is that contribution, ready to copy into a
checkout of that repository. It packages the *pattern* — evidence, constraints, frontier,
approval gate — rather than this demo, because 40 skills and 75 apps there are already
one-workflow entries.

It passes the upstream `scripts/validate_repository.py` and carries its own tests:

```bash
python3 contrib/skills/outcome-completion-agent/scripts/test_check_evidence_schema.py
```

## Documents

- [`docs/SPEC.md`](docs/SPEC.md) — the build specification: state machine, API,
  data model, prompts, failure handling, and what remains to be built.
- [`docs/competitive-landscape.md`](docs/competitive-landscape.md) — what is
  already in `awesome-phone-call-agents`, and where this is actually different.
- [`docs/demo-script.md`](docs/demo-script.md) — the three-minute demo, shot by shot.

## Status

The engine, the CALL-E adapter, the CLI, the server and the UI work and are
tested end to end against the mock transport, across two scenarios of different
shapes. The upstream skill package is written and passes that repository's own
validator.

`--live` is implemented against the documented v0.6.0 contract but has **not yet
been run against a real account**. See the SPEC's
[what is not built yet](docs/SPEC.md#14-what-is-not-built-yet).

MIT licensed.
