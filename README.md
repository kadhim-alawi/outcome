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

No dependencies beyond Python 3.11 and no credential. Nothing here places a
call unless you ask for `--live`.

```bash
python3 -m outcome.cli run scenarios/supplier-replacement.json     # terminal
python3 -m outcome.server                                          # http://127.0.0.1:8765
python3 -m unittest discover -s tests                              # 39 tests
```

The CLI stops at the approval gate and asks. `--approve auto` answers yes,
`--approve never` answers no — the run then goes back out to look for something
else, which is worth watching once.

### Placing real calls

```bash
export CALLE_API_KEY=...            # from dashboard.heycall-e.com/account/api-keys
python3 -m outcome.cli run scenarios/supplier-replacement.json --dry-run   # see the script first
python3 -m outcome.cli run scenarios/supplier-replacement.json --live      # spends credits
```

`--dry-run` renders the exact CALL-E request — including the words the caller
will speak — and places nothing. Run it before `--live`, every time. The
credential is read from the environment, never written to disk, and only ever
sent to `api.heycall-e.com` (see `ALLOWED_HOSTS` in `outcome/calle.py`).

Phone numbers in this repository are all in the `+1-555-01xx` range reserved
for fiction.

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

## Layout

```
outcome/
  models.py       Outcome, Constraint, Action, Evidence, Offer, Organization
  constraints.py  deterministic accept/reject, and why
  evidence.py     structured_result -> Evidence, defensively
  planner.py      frontier search + the call scripts
  approval.py     what needs a human, and the negation-aware safety net
  engine.py       the loop
  calle.py        CALL-E v0.6.0 adapter: live, dry-run, mock
  interpret.py    one sentence -> goal + constraints (rules, or an LLM)
  cli.py          watch a run in a terminal
  server.py       watch a run in a browser
scenarios/        scripted runs for the mock transport
web/index.html    the timeline UI
docs/SPEC.md      the build specification
```

## Documents

- [`docs/SPEC.md`](docs/SPEC.md) — the build specification: state machine, API,
  data model, prompts, failure handling, and what remains to be built.
- [`docs/competitive-landscape.md`](docs/competitive-landscape.md) — what is
  already in `awesome-phone-call-agents`, and where this is actually different.
- [`docs/demo-script.md`](docs/demo-script.md) — the three-minute demo, shot by shot.

## Status

The engine, the CALL-E adapter, the CLI, the server and the UI work and are
tested end to end against the mock transport. `--live` is implemented against
the documented v0.6.0 contract but has **not yet been run against a real
account**. See the SPEC's "What is not built yet" section.

MIT licensed.
