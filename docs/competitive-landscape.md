# What is already in `awesome-phone-call-agents`

Read against `CALLE-AI/awesome-phone-call-agents` at commit `100eb25`
(2026-09-05): **40 skills, 75 apps, 5 workflow plugins.**

This is a teardown of the field, not a pitch. The useful output of it is the
part where our differentiator turned out to be narrower than assumed.

---

## The shape of the field

Almost every entry is **one workflow, one call**: place a call, fill a
structured result, route on the answer.

- `structured-outcome-followup-call` — one call, score the answers against a
  rubric you supply, conditionally trigger a follow-up.
- `exception-resolver` — one call to get the information a system is missing,
  return it for human approval.
- `freshchain-resolver` — one cold-chain delivery exception, one call, four
  routes (`proceed` / `rebook` / `hold` / `escalate`).
- `appointment-confirm`, `service-dispatch-call`, `incident-escalation-call`,
  `verify-by-phone`, `pharmacy-stock-check`, and most of the other 36 skills.

A smaller group does **many calls against a known list**:

- `priority-call-waterfall` — one opening, a priority-ordered candidate list,
  call each in turn until someone accepts. The list is fixed at the start.
- `hungrycall-cascade`, `callback-coordinator`, `multi-party-scheduler` —
  fan-out or cascade over supplied contacts.
- `cortex-call-brain` — persistent two-tier memory across calls, so each call
  makes the next one smarter. Memory, not planning.

Nobody in this field is short of polish. The safety conventions are strong
throughout — E.164 enforcement, masked numbers, dry-run defaults, explicit
disclosure — and the repository's own `AGENTS.md` requires them.

---

## The one that matters: `callsweep`

`apps/typescript/callsweep` is far closer to OUTCOME than anything else, and it
is worth being precise about, because it invalidates the easy version of our
pitch.

> "Call many local businesses, haggle each one down toward your budget, rank
> their offers by the best overall deal, and book the one you pick."

It does, genuinely:

- discovers candidate businesses for a category and location (OpenStreetMap,
  no key required);
- places one quote-and-haggle call per shop, with a `recipientResultSchema`;
- **negotiates against a real budget**, with a per-shop floor;
- ranks the offers and shows a live board;
- requires the human to pick before any booking call is placed;
- enforces an `ALLOWED_PHONES` allowlist and a `yes` prompt before dialling.

So these claims are **not** available to us, and we should not make them:

- ❌ "Nothing here does more than one call."
- ❌ "Nothing here compares offers."
- ❌ "Nothing here evaluates a price against a budget."
- ❌ "Nothing here gates the committing call on a human."

---

## Where OUTCOME is actually different

One thing, and it is structural rather than a feature list.

**In `callsweep`, the candidate set is enumerable before the first call.**
"Barbers within 4km" is a map query. Every candidate offers the same service,
and the problem is choosing among them — comparison shopping, done well.

**In OUTCOME, the candidate set does not exist until people tell you about it.**
"Who can replace the crushed pallet from order BK-7741" is not a map query. The
user knows one number: the supplier who let them down. The route to a resolution
runs through a chain of heterogeneous parties, each holding one piece —

```
supplier  ──"out of stock, try Northgate"──▶  distributor
                                                  │
                              "our depot can do it locally, no surcharge"
                                                  │
                                                  ▼
                                              depot ──▶ resolved
```

— and each hop exists only because somebody on a call said so. The agent parses
a referral out of a conversation, validates the number, and adds it to the
frontier mid-run (`engine._absorb_referrals`). Two of the three organisations in
our demo were never given to the agent.

That produces behaviours the enumerable-list shape does not need:

| | `callsweep` | OUTCOME |
|---|---|---|
| Candidate source | Map query, fixed at start | Referrals extracted from calls, grows mid-run |
| Parties | Homogeneous (same service) | Heterogeneous (supplier / distributor / depot) |
| `blocked` outcome | A shop that cannot help drops out | A shop that cannot help is asked *who can*, and answers |
| Retry | — | Per-party cap on no-answer, then move on |
| Commit call | Human picks the shop | Human approves an **envelope**: this item, this price, this date; the caller is told to walk away if any term moved |
| Budget | Negotiation target | Hard constraint that rejects an otherwise successful call, plus a hard **call** budget checked before every dial |

The commit envelope is the second real difference. In `callsweep` the booking
call confirms the shop the human chose. In OUTCOME the approved terms are
written into the script as an exhaustive authorisation, and the caller is
instructed that a changed price, date, fee or item means *do not accept, record
the new terms, hang up, the customer decides again*. The user approved an offer,
not a renegotiation.

---

## What this means for the submission

1. **Do not pitch "multi-call agent".** That is taken, by a good entry.
   Pitch **"the agent finds out who to call by calling"**.
2. **The demo must show a referral being followed.** The moment that carries the
   whole idea is `New lead: Northgate Distribution` appearing on a timeline the
   user never typed it into. If a reviewer only remembers one frame, it is that.
3. **Lead with the chain, not the comparison.** Northgate's $612 being rejected
   is good, but it is comparison shopping. Northgate *pointing at its own depot*
   is the thing nothing else in the repository does.
4. **The contribution should be the pattern, not the story.** 40 skills and 75
   apps are already one-workflow entries. A skill packaging evidence →
   constraints → frontier → gate is a contribution *to* the repository rather
   than another entry *in* it. See `SPEC.md` §15.
5. **Judge honestly against `callsweep` before submitting.** It is polished, it
   is safe, and it is in the same neighbourhood. Our margin is the discovered
   call graph. If a version of our demo would work with a phone book known
   upfront, we have not demonstrated our own idea.
