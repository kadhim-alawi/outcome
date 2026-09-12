# Live call rehearsal — you are the depot

Your lines for the live run. Two calls to your handset, with an approval in
between, about four minutes end to end. This is what
[`video-plan.md`](video-plan.md) Segment B records.

You are **"Test depot"**, a supplier of insulated shipping boxes. The caller is
an AI assistant ringing on behalf of a customer. It will say so itself, first
thing.

---

## Call 1 — it asks, you quote

### What it wants

> Can you supply **50 insulated shipping boxes**, delivered this week?

Behind that, it is checking three things:

| | Must be |
|---|---|
| Price | at or under **USD 500** |
| Delivery | on or before **17 September** |
| Reference number | nice to have, not required |

It is explicitly told it **may not agree to anything** on this call. If you try
to close the deal, it should say it will confirm shortly. That is correct
behaviour, not a failure.

### What you say

Wait for it to introduce itself and ask. Then:

> "Yes, we can do that. Fifty insulated shipping boxes, three hundred and eighty
> dollars. We can deliver on the sixteenth of September."

If it asks for a reference number:

> "Your reference is BWD-4471."

Then let it wrap up and **let it hang up first**.

### Why these numbers

- **380** is under the 500 limit → the budget constraint passes
- **16 September** is before the 17th → the deadline constraint passes
- Both passing is what produces an approval card instead of a rejection

**Say the date as a date** — "the sixteenth of September", not "Tuesday". The
constraint check compares actual dates, and a weekday name may not resolve.

---

## Between the calls — your bit

The run stops and shows an approval card: the offer, the three checks, and what
it would commit you to. With `--approve auto` it continues by itself, and the
second call goes out within a few seconds.

**Stay on the line mentally — the phone rings again quickly.**

---

## Call 2 — it accepts

### What it wants

This is the one call in the whole run allowed to say yes, and its authority is
written as an exact envelope:

```
YOU ARE AUTHORISED TO ACCEPT EXACTLY THIS AND NOTHING ELSE:
  50 insulated shipping boxes
  Price: USD 380.00
  Delivery: 2026-09-16
```

It is told that if **anything** has moved — a different price, a later date, an
added fee — it must NOT accept, and must come back to you instead.

### What you say

> "Yes, that's right. Three hundred and eighty dollars, delivered the sixteenth.
> Your order reference is BWD-4471."

It should confirm, thank you, and end. The run then reports **RESOLVED**.

---

## Optional: prove the envelope holds

If you want to demonstrate the safety property rather than the happy path, on
**call 2** change the terms:

> "Actually the price has gone up to six hundred dollars."

The agent should **refuse to accept**, record the new terms as a fresh offer,
and end the call politely — because 600 is over your 500 limit and it was only
authorised for 380.

That is arguably the more impressive recording. But do the clean run first, so
you have the RESOLVED result banked.

---

## Practical

- **Answer promptly.** An unanswered call is a wasted credit and locks the
  account for about 2h36m.
- **Speak normally.** Don't over-enunciate; it handles ordinary speech.
- **Short sentences beat complete ones.** It is extracting fields, not enjoying
  prose.
- **Don't hang up first** on call 1 — it needs a moment to fill in the result
  schema before the line drops.
- If it asks something you have no answer for, say so plainly. "I don't know" is
  a legitimate answer and the schema has a place for it.

---

## What success looks like on my side

```
▸ Call Test depot (you) — can they fix this, and if not, who can?
  ☎  Test depot (you) +*******9558
  ✓  offer  50 insulated shipping boxes — USD 380.00 — meets your requirements
     ✓ at or under USD 500.00
     ✓ on or before 2026-09-17
▸ APPROVAL — accept USD 380.00 from Test depot (you)?
  ✓ approved
▸ Call Test depot (you) back to accept: 50 insulated shipping boxes at USD 380.00
  ☎  Test depot (you) +*******9558
  ✓  confirmed — reference BWD-4471

  RESOLVED
  2 of 2 calls used.
```
