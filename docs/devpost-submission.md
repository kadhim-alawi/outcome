# Devpost submission — OUTCOME

Copy each section into the matching Devpost field. Placeholders marked **[TBD]**.

---

## Project name

**OUTCOME**

## Tagline

Don't tell it who to call. Tell it what needs to happen.

## Elevator pitch (Devpost's short field)

An autonomous phone-work agent that owns a goal to resolution. You give it an
outcome and the limits an answer has to satisfy. It works out who to call, calls
them, and — when the answer is "we can't help, try these people" — calls those
people instead. The list of who to ring is discovered on the phone, not supplied
up front.

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
any code we read every entry in `awesome-phone-call-agents` — at the time 40
skills and 75 apps — and found the space genuinely crowded. `callsweep` already
compares quotes across vendors against a budget. `priority-call-waterfall`
already calls a ranked list until someone accepts. What nothing did was **grow
its own call list mid-run**, because their candidates come from a database or a
map query. Ours cannot: "who can replace order BK-7741" is not a query you can
run. You have to ask someone.

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

**124 tests**, no network, no credentials.

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

We tested both English and Arabic; the gate is the region, not the language. The
supported set is not published anywhere in the docs, the OpenAPI schema, or the
error body — so this is only discoverable *after* signing up, integrating, and
making a request that fails.

**Then the workaround hit a second wall.** The obvious fix is to rent a number in
a supported region and forward it, so we did: a US number from a VoIP provider,
pointed at a SIP softphone. Calls to it never arrived — and never appeared in the
provider's own logs either, which is the tell that they were rejected at the edge
rather than misrouted. The cause was in the provider's account-level
documentation rather than any error message:

> **Voice → Inbound: limited to receiving from the verified phone number.**

That restriction applies at both of their unpaid account tiers. CALL-E dials from
its own numbers, which will never be a developer's single verified number, so
inbound from CALL-E can never be accepted on an unpaid account — not as a bug, by
design. Reaching the tier that lifts it requires a card payment.

So the two blockers are independent and neither is a defect in this project:
CALL-E does not serve our region, and the cheap way around that needs a paid
telephony account. **[TBD: update if a live call is made before submission.]**

Every refusal along the way happened **before the dial**, so none of them cost a
CALL-E credit. That behaviour is genuinely good API design, and it is the reason
this section exists instead of a bill.

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

---

## Notes before submitting — delete this section

1. **Video.** Record the mock run: it is deterministic and does not burn credits
   on retakes. Say plainly in the video description that it is the scripted
   transport and that `--live` runs the identical engine. Shot list is in
   [`demo-script.md`](demo-script.md).
2. **The regional paragraph** in *Challenges* needs updating if a live call
   succeeds before the deadline.
3. Fill both **[TBD]** links above.
