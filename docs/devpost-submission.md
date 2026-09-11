# Devpost submission — OUTCOME

Copy each section into the matching Devpost field. Placeholders marked **[TBD]**.

---

## Project name

**OUTCOME**

## Tagline

Don't tell it who to call. Tell it what needs to happen.

## Elevator pitch (Devpost's short field)

An autonomous AI phone agent that owns goals to resolution. Give it an outcome and constraints, and it dynamically finds contacts, follows referrals, and self-navigates calls until resolved.

---

## Inspiration

The tedious part of phone bureaucracy is not the talking. It is that **you do not
know who to call.**

A pallet of shipping boxes arrives crushed. You have exactly one phone number:
the supplier who sent the broken one. They are out of stock, and they mention a
distributor. The distributor quotes too much, and mentions their own depot. The
depot can do it. Three companies, and you only knew about one when you started.

Every step of that is a human being kept on hold to be handed the next number.
An AI that can make a phone call does not fix it. An AI that can decide **which
call to make next** does.

That framing is also what steered us away from the obvious build. Before writing
any code we read every entry in `awesome-phone-call-agents`, and checked it again
on 11 September, by which point it held **66 skills, 126 apps and 5 plugins**. The
space is crowded and the neighbours are good: `callsweep` compares quotes across
vendors against a budget, `priority-call-waterfall` calls a ranked list until
someone accepts, `procurecall-supplier-sourcing` qualifies suppliers and returns a
comparison for approval.

Every one of them starts from a list. `partline-part-sourcing` makes the
assumption explicit — it calls *"approved suppliers"*, and instructs the agent to
*"never include another supplier's name, quote or inventory in a call"*, which for
procurement compliance is exactly right.

What nothing does is **grow its own call list mid-run**, because their candidates
come from a database, an approved-vendor table, or a map query. Ours cannot: "who
can replace order BK-7741" is not a query you can run. You have to ask someone,
and then ask the person they name.

## What it does

You create an **outcome**, not a call:

> Get a replacement pallet of 500 insulated shipping boxes for the crushed
> delivery on order BK-7741.
> **Must:** at or under USD 500 · delivered on or before 11 September

You give it one phone number. It does the rest:

| # | Who | What happened |
|---|---|---|
| 1 | Halden Packaging | Nobody answers |
| 2 | Halden Packaging | Out of stock until the 30th — *"try Northgate"* |
| 3 | Northgate Distribution | $612 with courier — **$112 over your limit, rejected** — *"our depot can do it locally"* |
| 4 | Brightwater Depot | $438, Thursday van — **meets every requirement** |
| — | **you** | *Accept $438 from Brightwater Depot?* → **Approve** |
| 5 | Brightwater Depot | Confirmed. Reference BWD-48291 |

**Two of the three companies were never given to the agent.** It found them by
asking the people it was already talking to.

Four ideas do the work:

**Evidence, not transcripts.** Every call returns a structured verdict —
`no_answer`, `refused`, `blocked`, `partial`, `offer`, `confirmed` — plus the
facts stated, blockers named, any referral given, and any concrete offer. The
planner reads that log and never reads a transcript, which is why the same
planner drives a scripted rehearsal and a live run identically.

**Constraints are code, not prompt text.** "Under $500" is a comparison operator,
not a sentence in a system prompt. Call 3 completed, the person was helpful, and
the outcome was still a **failure** — so the agent kept working. Routing on call
status instead of constraint verdict would have reported a $612 solution to
somebody who said $500.

**The frontier grows.** A referral with a dialable number becomes a party worth
calling. That single behaviour is the difference between an agent and a dialler,
and it is why the run cannot be written down in advance.

**Asking is free; agreeing is not.** Information-gathering calls run unattended
and are told, in the script itself, that they have no authority to agree to
anything. Exactly one call per run may say yes, it is gated on your approval, and
its script names the exact price and date it may accept — if the terms have
moved by the time it connects, it is told to walk away and come back to you.

## How we built it

Python 3.11+, standard library only. No framework, no dependencies to install
before a judge can run it.

```
goal + constraints
        ↓
    PLANNER ←──────────────┐
        ↓ one action       │
  APPROVAL GATE ── commits you? ──→ you decide
        ↓ no               │
      CALL-E               │
        ↓                  │
    EVIDENCE  facts, blockers, referrals, offer
        ↓                  │
   CONSTRAINTS  acceptable? ┘
        ↓
 resolved / abandoned
```

- **`planner.py`** — deterministic frontier search. The loop that spends your
  money and your CALL-E credits is readable code, not a model's judgement. An
  LLM interprets the goal sentence; it does not choose who to dial.
- **`calle.py`** — the CALL-E adapter, and the only module that can reach the
  network. `POST /v1/calls` with `recipient_result_schema`, poll `GET
  /v1/calls/{id}`, payload-derived `Idempotency-Key` so a resubmitted action
  cannot ring a second phone, and an https host allowlist for the bearer token.
- **`constraints.py`** — deterministic accept/reject with four judgements, not
  two. `unknown` (no price was quoted) deliberately does not block, or every run
  would strand behind a detail nobody asked about on the call.
- **`store.py`** — SQLite, and a **write-ahead call ledger**. It is written
  *before* the dial, because the window that matters is the one where the phone
  is ringing and nothing has been recorded yet. A process that forgets what it
  dialled dials again, and the person answering has no way to know the second
  call is a bug.
- Three transports behind one protocol — live, dry-run, and a scenario replay —
  so the engine cannot tell which it is talking to. The run you rehearse offline
  is the run that happens on the phone.

**144 tests**, no network, no credentials.

**Why not CALL-E Goals?** A Goal is a published, version-pinned workflow you run
per recipient with variables, and the run "cannot select, replace, or relax
schemas or the materialization contract" — which is exactly right for a governed,
repeatable call. It is a contract for *one* interaction. OUTCOME is the layer
above: what to do once that interaction comes back, whether the answer clears the
user's limits, and who to ring next given what was just said. The two stack
rather than compete — the natural next version publishes each call shape as a
Goal and keeps the planner deciding which Goal to run against whom. What we would
not move into a Goal is the decision of who to call next, because that is the
part that spends the user's money and it belongs in code a person can read.

## Safety

Phone calls are real-world side effects, so four guards sit between the planner
and somebody's ringing phone:

- **A number allowlist**, enforced inside the dialler rather than beside it. The
  frontier grows from numbers given on calls, so a referral reaches the network
  without passing through any form the operator filled in — the check has to be
  on the last line before the wire.
- **A calling window** in the *recipients'* timezone. Calling a depot at 03:00 is
  legal and awful, and it is the failure an autonomous agent falls into most
  easily, because nothing in the loop knows what time it is where the phone is.
  A closed window **parks** the run and resumes at the same call, approval intact.
- **A call budget**, checked immediately before every dial rather than at
  planning time, so an approval that sat overnight cannot spend a credit the
  budget no longer has.
- **The approval gate**, with a negation-aware backstop. Every gathering script
  ends with "you are NOT authorised to agree to anything, accept any price, or
  cancel anything" — three committing verbs. A naive keyword net flags all five
  calls, the user approves five times, and by the fifth they have stopped
  reading. **A safety net that fires constantly trains the behaviour it exists to
  prevent.**

Every phone number is masked everywhere it is shown or logged. The credential is
read from the environment, never written to disk, and only ever sent to CALL-E's
own hosts.

## Challenges we ran into

**The result schema CALL-E rejects.** Our first live attempt came back:

```
HTTP 400 recipient_result_schema_invalid
"unsupported JSON Schema type at $.properties.offer: ['object','null']"
```

A nullable union is the natural way to say "this field is optional" and is legal
JSON Schema. Reading CALL-E's guide properly turned up two more we would have hit
next: `summary` is a reserved recipient field name, and — the one that matters —
**a result that fails validation comes back `null` in its entirety**. Our
original `required: ["reached", "verdict", "facts"]` would have silently thrown
away every call where the caller had a verdict but nothing quotable. We now ship
a validator for the documented subset and run it in `preflight`, so the next
schema mistake costs nothing.

**A failure we could not see.** That same run printed two lines and exited. The
engine had done everything right — caught the error, parked the run, written an
explanatory event — and the CLI had no handler for that event kind, so the only
explanation went on the floor. A silent failure is worse than a crash. There is
now a test that walks the engine for every event it can emit and asserts both the
terminal and the browser render all of them.

**Regional availability.** CALL-E does not currently place calls to Bahrain,
where we are:

```
HTTP 422 call_not_ready
"The recipient number appears to be in Bahrain (BH), with Arabic requested, but
calls for that region/language combination are not currently supported."
```

We tested both English and Arabic; the gate is the region, not the language.

**And then we wrote up the wrong lesson.** Our first version of this said the
supported set was not published anywhere. It is — a 44-country table with
languages and line types, in the `call-e-integrations` README, which is the first
link on the hackathon resources page. We had searched the API surface, because
that is where an error from `POST /v1/calls` sends you, and never thought to read
the setup guide. Bahrain is genuinely not on the list, so the 422 was right and
the workaround was still needed — but the reason we spent a day on it was that we
never found the answer, not that there wasn't one.

What survives is much smaller and we think still fair: the 422 asks you to pick a
supported combination without saying where the menu is, and `calls.mdx` and the
OpenAPI schema document `region` without linking the table. One cross-reference
would have saved the detour. (UAE, Saudi Arabia and Oman are all supported, so the
better workaround was a neighbouring number, not a US one.)

**Then we misdiagnosed the workaround.** The obvious fix is to rent a number in a
supported region and point it somewhere we can answer, so we did: a US number on
a SIP connection, terminating at a softphone. One call cleared CALL-E's
validation and actually dialled. The attempt record:

```
"failure_code": "408",
"started_at":   "2026-09-10T18:53:04Z",
"completed_at": "2026-09-10T18:53:04Z"
```

SIP 408 with both timestamps identical — refused in zero seconds, not rung out.
We matched that against the telephony provider's documented restriction on unpaid
accounts, where inbound is limited to calls from your own verified number, and
wrote it up as a second independent blocker.

**It wasn't.** The account is on the paid tier, where that restriction does not
apply. We had diagnosed a live system from its vendor's documentation instead of
from the account itself — which is the precise failure mode this project's
evidence model exists to prevent, committed by the people who built it.

Isolating the real cause then ran into the concurrency bug above: the unanswered
call held CALL-E's single slot for two and a half hours, so every attempt cost an
afternoon rather than a credit.

The real cause was the dullest one available. The softphone was not reachable at
the moment CALL-E dialled — which is what SIP 408 *Request Timeout* means, and
what it had been saying all along. A policy refusal returns 403 or 603. We read a
timeout as a rejection because we had a rejection in mind.

**With the softphone confirmed live, it worked on the first attempt.** Two real
calls, a real conversation, and a resolved outcome — the transcripts and the
structured result CALL-E returned for each are in
[`docs/live-call-evidence.md`](live-call-evidence.md).

**And then it reported the call as unanswered.** A last bug, and ours: CALL-E
returns `status: failed` both when nobody picks up and when somebody does but the
objective is not met. We had collapsed the two into `no_answer` — which threw away
a conversation that happened, and worse, `no_answer` is retryable, so the planner
would have rung a person back two minutes after they finished explaining
themselves. A transcript now outranks a failed status. That is the same guarantee
`store.py` was written for, arriving through a door we had not thought to watch.

One refusal in all of this actually dialled; every other one happened **before**
the dial and cost no CALL-E credit. That behaviour is genuinely good API design,
and it is the reason this section exists instead of a bill.

## Accomplishments we're proud of

The bits where we chose the harder correct answer over the easy one:

- **Declining does not loop.** A rejected offer is recorded as declined, so the
  planner cannot immediately re-propose it. Without that, "no" is infinite.
- **An unreadable price is `unknown`, never `0`.** Guessing zero sails a quote
  straight past a budget ceiling.
- **A crash cannot cause a second call.** And when a call's outcome is genuinely
  unknown, the agent refuses to redial and asks a human which of two things
  happened, rather than guessing.
- **`--resolve` records an interrupted call as `blocked`, not `no_answer`,**
  because `no_answer` is retryable and re-ringing somebody who may have just
  spent five minutes with the agent is the wrong move.

## What we learned

That the interesting problem in agentic phone work is **not the conversation**.
CALL-E handles the conversation well. The interesting problem is what you do with
what you were told: how you read it, how you decide it is not good enough, and
how you work out where to go next.

Also that a mock which returns a different shape from the real provider is a mock
that lies. When the live 400 forced our schema to change, we rewrote the scripted
scenarios into the same wire format the same day — otherwise every rehearsal
would have been rehearsing something that cannot happen.

## What's next

- Per-organisation calling windows, for runs that cross a border.
- Persisting browser runs, which today only the CLI does.
- More outcome shapes. The second scenario — a disputed mobile bill, resolved by
  climbing an escalation chain inside one company against a *minimum* rather than
  a budget — needed one new constraint kind and no changes to the engine, which
  is the result we wanted.

## Built with

`python` · `sqlite` · `call-e` · `json-schema` · `html` · `javascript`  

## Links

- **Repository:** https://github.com/kadhim-alawi/outcome
- **Required PR:** https://github.com/CALLE-AI/awesome-phone-call-agents/pull/369
  — `outcome-completion-agent`, a reusable skill packaging the pattern rather
  than this demo, including the three CALL-E schema rules that cost us a live call.
- **Demo video:** **[TBD]**
- **CALL-E account email:** **[TBD — the address on your CALL-E account]**
- **API notes:** [`docs/calle-api-notes.md`](calle-api-notes.md) — the schema and
  region constraints we hit, with the exact requests and errors.
- **Live call evidence:** [`docs/live-call-evidence.md`](live-call-evidence.md) —
  transcripts and the structured result CALL-E returned for the two real calls
  that resolved a goal on 11 September.

---

# The "Additional info" step

Step 4 of 5 on Devpost. Judges and organisers see this; the public project page
does not.

| Field | Answer |
|---|---|
| Submitter Type | **Individual** |
| Country of residence/incorporation | **Bahrain** |
| Organization name | *blank* |
| App status | **Newly created** |
| Optional demo URL | *blank* — see below |
| Project submission pull request URL | `https://github.com/CALLE-AI/awesome-phone-call-agents/pull/369` |
| Email associated with your CALL-E account | **[TBD — same address as the link above]** |
| Primary use case | **Order / exception follow-up** |
| The three eligibility checkboxes | all three ticked |

**App status is "Newly created".** First commit is `01d5880`, dated 5 September
2026 — inside the submission period, and the repository was empty before it.

**Primary use case.** The demo is a damaged delivery on order BK-7741 chased to
a replacement, which is that category exactly. *Service coordination & dispatch*
is the near miss, but the agent is not coordinating a known provider — it is
working out who can help at all. The form says this field does not affect
judging, so the honest answer is the right one.

**Leave the optional demo URL blank.** The demo is a local server with no auth
and no persistence. Publishing it means standing up something neither hardened
nor multi-tenant, and the testing instructions below get a judge to the same
screen in about two minutes. An empty optional field costs nothing; a public URL
that is down when a judge clicks it costs a lot.

## "If pre-existing, explain what you updated during the submission period."

Required even though it does not apply, so it needs a line rather than a blank:

> Not applicable — newly created. The repository was empty before this
> hackathon; its first commit is dated 5 September 2026, inside the submission
> period, and the full history is public at
> https://github.com/kadhim-alawi/outcome/commits/main

## Testing instructions for application

```
No dependencies, no credential, and nothing dials a phone unless you pass --live.

    git clone https://github.com/kadhim-alawi/outcome
    cd outcome
    python3 -m unittest discover -s tests     # 144 tests, no network, no key
    python3 -m outcome.server                 # then open http://127.0.0.1:8765

Windows only: run `pip install tzdata` first. Windows ships no IANA timezone
database, and the calling window has nothing to resolve against without it. It is
the only thing this project needs beyond the standard library.

IN THE BROWSER — about two minutes:

 1. The supplier scenario is already loaded. Click "Read the requirements out of
    this". The goal sentence is parsed into rules: at or under USD 500, resolved
    on or before 11 September. Both are marked "must".

 2. Look at "Who to call first". It is one phone number. That is the entire
    input.

 3. Click Start. Five calls run. Watch for two rows labelled "New lead" —
    Northgate Distribution, then Brightwater Depot. Neither was given to the
    agent. Both came out of a conversation with somebody it was already talking
    to. This is the behaviour the project exists to demonstrate.

 4. Call 3 completes successfully and is still rejected: USD 612 is USD 112 over
    the limit. Call status and constraint verdict are deliberately separate — a
    helpful person who quotes too much is a failed outcome, and the agent keeps
    working.

 5. The run stops at an approval card. Nothing before this point could commit
    you; those calls were only allowed to ask. Click Approve and the final call
    accepts the exact terms shown on the card.

Add ?pace=5000 to slow the timeline down for reading:
http://127.0.0.1:8765/?pace=5000

THE SAME ENGINE FROM A TERMINAL:

    python3 -m outcome.cli run scenarios/supplier-replacement.json
    python3 -m outcome.cli run scenarios/bill-dispute.json

The second is a different outcome shape — a disputed mobile bill, resolved by
climbing an escalation chain inside one company against a minimum rather than a
budget. It needed one new constraint kind and no changes to the engine.

GOING LIVE:

    export CALLE_API_KEY=...
    export CALLE_ALLOWED_NUMBERS=+1...     # every number the agent may dial
    python3 -m outcome.cli preflight       # credential, schema, window, allowlist, budget
    python3 -m outcome.cli run scenarios/<file>.json --live --store runs.sqlite3

Three transports sit behind one protocol — live CALL-E, dry-run, and scenario
replay — and the engine cannot tell which it is talking to. The run you watch
offline is the run that happens on the phone.

IT HAS RUN LIVE:

On 11 September 2026 this resolved a goal over two real phone calls through the
CALL-E Developer API. Transcripts and the structured result CALL-E returned for
each call are in docs/live-call-evidence.md.

    call_fRjlbGjjzn8zQGPqomoRlQ   gathering  — offer USD 380.00, 2026-09-16
    call_qo8JGJf0NnhDEEqFcCnZ1Q   commit     — confirmed, with a reference

The demo above runs on the scripted transport because it is deterministic and
costs no credits to rehearse, not because the live path is untested.

Getting there was not straightforward, and the detail is in Challenges: CALL-E
does not currently place calls to my region, so the recipient is a US number on
a SIP connection that I own and answered myself. Nothing in this project has
ever dialled a real business.

```

## In one sentence, what real-world task does your CALL-E application handle?

> Resolving a stuck order or service problem end to end over the phone — chasing
> a damaged delivery to a replacement that meets a hard budget and deadline —
> when you start out knowing only one number to call and have to discover the
> rest by asking the people you reach.

Shorter, if the field feels cramped:

> Chasing a stuck order to a resolution that meets a hard budget and deadline,
> starting from one phone number and finding the rest of the companies to call
> by asking the people it reaches.

---

## Notes before submitting — delete this section

1. **Video.** Record the mock run: it is deterministic and does not burn credits
   on retakes. Say plainly in the video description that it is the scripted
   transport and that `--live` runs the identical engine. Shot list is in
   [`demo-script.md`](demo-script.md).
2. ~~The regional paragraph in *Challenges* needs updating if a live call
   succeeds.~~ Done — it ran live on 11 September, and *Challenges* and the
   testing instructions both say so.
3. Fill both **[TBD]** links above.
