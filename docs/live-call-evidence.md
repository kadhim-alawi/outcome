# Evidence: the live run

OUTCOME resolved a goal over two real phone calls on **11 September 2026**,
through the CALL-E Developer API. This is the raw record, pulled from the call
ledger — transcripts as CALL-E transcribed them, and the structured result it
returned for each call. Only the phone number is redacted.

The recipient is a number the operator owns and authorised, answering as the
fictional "Test depot". Nothing here contacted a real business.

Reproduce the shape of it without a phone:

```bash
python3 -m outcome.cli run scenarios/supplier-replacement.json
```


---

## Call 1 — gathering. It may ask, it may not agree to anything.

`call_fRjlbGjjzn8zQGPqomoRlQ`

Connected `2026-09-11T14:45:21.966176Z` → `2026-09-11T14:46:33.552339Z`

```
BOT   Hi,
BOT   I'm calling on behalf of a customer.
USER  Hi. I'm calling on behalf of a customer. Hello, Deepu.
BOT   Hi Deepu,
BOT   thanks for taking my call. Could you help me check whether you can supply fifty insulated shipping boxes and deliver them by September seventeenth,
BOT   twenty twenty-six, for a total cost at or under five hundred US dollars?
USER  Hi, Deepu. Thanks for taking my call. Could you help me check whether you can 50 insulated shipping boxes and deliver them by 09/17/2026 for a total cost at or under 500 US dollars. Yes. We can do that. 50 inflated shipping boxes, $380. We can deliver on the September 16.
BOT   Thank you.
BOT   Just to confirm, that's fifty insulated shipping boxes for $380 US dollars,
BOT   delivered on September sixteenth, twenty twenty-six.
USER  Thank you. Just to confirm, that's 50 insulated shipping boxes for $380 US dollars delivered on 09/16/2026.
BOT   Yes, that's correct.
BOT   Do you have a reference number or order number for this arrangement?
USER  Yes. Yes. That's correct. Do you have a reference number or order number for this arrangement? Yes. It's b w d 4 4 7 1.
BOT   Thank you,
BOT   the reference number is BWD4471. I'll let the customer know and they will confirm shortly.
BOT   Thank you for your help, bye.
USER  BWDD471. I'll let the customer know, and they will confirm shortly.
USER  Thank you for
```

What CALL-E extracted:

```json
{
  "verdict": "confirmed",
  "reached": "yes",
  "facts": [
    "They said: \"Yes. We can do that.\"",
    "They said: \"50 inflated shipping boxes, $380.\"",
    "They said: \"We can deliver on the September 16.\"",
    "They confirmed that 50 insulated shipping boxes for $380 US dollars delivered on 09/16/2026 was correct.",
    "They gave the reference number as \"b w d 4 4 7 1.\""
  ],
  "offer": {
    "what_is_offered": "50 insulated shipping boxes",
    "price": "380",
    "currency": "USD",
    "eta": "2026-09-16",
    "reference": "BWD4471"
  },
  "blockers": [],
  "referrals": []
}
```


---

## Call 2 — the commit call. The only call in the run allowed to say yes.

`call_qo8JGJf0NnhDEEqFcCnZ1Q`

Connected `2026-09-11T14:47:55.579244Z` → `2026-09-11T14:48:41.502057Z`

```
BOT   Hi,
BOT   I’m an AI assistant placing this call on behalf of a customer.
USER  Hi. I'm an AI assistant placing this call on behalf Hello, Deepa.
BOT   Hi,
BOT   I’m an AI assistant placing this call on behalf of a
USER  Hi. I'm an AI assistant placing this call on behalf of a
BOT   customer.
USER  Yes. Hello. Depot. Customer.
BOT   Hi,
BOT   can you confirm whether you can supply fifty insulated shipping boxes for three hundred eighty U.S.
BOT   dollars total and deliver them on September sixteenth, twenty twenty-six?
USER  Hi. Can you confirm whether you can supply 50 insulated shipping boxes for 380 US dollars total and deliver them on 09/16/2026. Yes.
USER  Hi. Can you confirm whether you can supply 50 insulated shipping boxes for 380 US dollars total and deliver them on 09/16/2026. Yes. That's right. $380 delivered the 16th. Your order reference is d w d 4 4 7 1.
BOT   Thank you.
BOT   I have the reference number. Thank you, bye.
USER  number.
```

What CALL-E extracted:

```json
{
  "verdict": "confirmed",
  "reached": "yes",
  "facts": [
    "They said yes when asked to confirm they can supply 50 insulated shipping boxes for 380 US dollars total and deliver them on 09/16/2026.",
    "They said, \"That's right. $380 delivered the 16th.\"",
    "They said, \"Your order reference is d w d 4 4 7 1.\""
  ],
  "offer": {
    "what_is_offered": "50 insulated shipping boxes",
    "price": "380.00",
    "currency": "USD",
    "eta": "2026-09-16",
    "reference": "DWD4471"
  },
  "blockers": [],
  "referrals": []
}
```


---

## What the operator saw

```
▸ Call Test depot (you) — can they fix this, and if not, who can?
  ☎  Test depot (you) +*******9558
  ✓ confirmed
     offer 50 insulated shipping boxes — USD 380.00 — meets your requirements
▸ Call Test depot (you) back to accept: 50 insulated shipping boxes at USD 380.00.

  APPROVAL NEEDED
  Accept 50 insulated shipping boxes from Test depot (you) for USD 380.00 on 2026-09-16?
    ✓ USD 380.00 is within the USD 500.00 limit.
    ✓ 2026-09-16 is on or before the 2026-09-17 deadline.
    ✓ reference=BWD4471
  ✓ approved
  ☎  Test depot (you) +*******9558 (attempt 2) [commits you]
  ✓ confirmed

  RESOLVED
  50 insulated shipping boxes with Test depot (you) for USD 380.00, 2026-09-16.
  Reference: DWD4471
  2 of 2 calls used across 1 organisations.
```

## Two honest artifacts in the record

**The reference number drifted.** The depot said "b w d 4 4 7 1" on call 1 and
CALL-E heard `BWD4471`. On call 2 the same speaker said it again and CALL-E heard
`DWD4471`, which is what the resolved outcome carries. B and D are hard to tell
apart over a phone line, and the agent recorded what it heard rather than what it
had on file — which is the behaviour we want, even when it produces a worse
answer. A production version would read the reference back for confirmation.

**The recipient's audio echoed.** The operator answered on a softphone using
speakers rather than a headset, so the microphone picked up the agent's own
voice. That is why several `USER` turns begin by repeating what the agent just
said before the human's actual words. It did not affect extraction — every field
in the structured result is correct — but it makes the transcript harder to read
than it should be.
