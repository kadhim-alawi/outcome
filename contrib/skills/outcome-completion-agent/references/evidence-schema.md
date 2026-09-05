# The evidence schema

Every call in an outcome run fills in the same structure. That is what makes calls
composable: the planner reads a uniform record rather than a transcript, so a call to a
supplier and a call to a depot are the same kind of input.

Pass it as `recipient_result_schema` on `POST /v1/calls`.

```json
{
  "type": "object",
  "required": ["reached", "verdict", "facts"],
  "properties": {
    "reached": {
      "type": "boolean",
      "description": "True only if a person actually spoke with you."
    },
    "verdict": {
      "type": "string",
      "enum": ["no_answer", "refused", "blocked", "partial", "offer", "confirmed"],
      "description": "no_answer if nobody picked up. refused if they declined to help. blocked if they cannot do it and named an obstacle. partial if you learned something but the objective is unmet. offer if they proposed something concrete. confirmed if the objective is now met and they committed to it."
    },
    "facts": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Short statements of what the person actually said. Do not infer, summarise or add anything they did not say."
    },
    "blockers": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Reasons given for why the objective cannot be met here."
    },
    "referrals": {
      "type": "array",
      "description": "Other organisations or departments they told you to contact, with the number they gave. Leave empty if none were offered. Never invent a number.",
      "items": {
        "type": "object",
        "required": ["org_name"],
        "properties": {
          "org_name": {"type": "string"},
          "phone": {"type": "string", "description": "E.164 if they gave one, else empty."},
          "role": {"type": "string"},
          "reason": {"type": "string"}
        }
      }
    },
    "offer": {
      "type": ["object", "null"],
      "description": "A concrete proposal, if one was made. Null otherwise.",
      "properties": {
        "summary": {"type": "string"},
        "price": {"type": ["number", "null"], "description": "Total, in the stated currency."},
        "currency": {"type": "string"},
        "eta": {"type": ["string", "null"], "description": "YYYY-MM-DD if a date was given."},
        "reference": {"type": ["string", "null"], "description": "Any reference or order number."}
      }
    }
  },
  "additionalProperties": false
}
```

## The six verdicts

The enum is small on purpose. Each value maps to a different next move, and a verdict that
does not change what the planner does next does not deserve to exist.

| Verdict | What it means | What the planner does |
|---|---|---|
| `no_answer` | Nobody picked up | Retry once, under the per-party cap, then move on |
| `refused` | They declined to engage | Do not call back. Take any referral and move on |
| `blocked` | They would help but cannot, and said why | Record the blocker, take the referral, move on |
| `partial` | Something learned, objective unmet | Record it; usually move on |
| `offer` | A concrete proposal | Evaluate against constraints |
| `confirmed` | Objective met and committed to | Resolved, if this was an approved commit call |

## Parse it defensively

This is the least trustworthy input in the system: a model's reading of a phone
conversation, filled in under time pressure by a caller who may have been talked over. The
loop must not crash on it, and — more importantly — must not quietly invent the missing
half.

- **A price you cannot read is unknown, never zero.** Accept `438`, `"438"`, `"$438.00"`,
  `"USD 1,438"`. Anything else is `null`, and `null` reads as "not quoted". Guessing `0`
  sails a quote straight past a budget ceiling.
- **A referral without a valid E.164 number is dropped.** See the Following A Referral
  section of `SKILL.md`.
- **A call the provider did not complete is never testimony.** If the CALL-E call status is
  `failed` or `canceled`, treat it as `no_answer` whatever the structured block says. A
  half-connected call can return a confidently filled-in result.
- **An empty `offer: {}` is not an offer.** Require at least a summary, a price, or a date.
- **`reached: false` overrides the verdict.** If no person spoke, nothing was established.

## Why not just read the transcript

A transcript is not a decision input. It is long, it is unstructured, and every planner
that reads one ends up re-deriving the same six facts with a second model call. Worse, it
cannot be replayed: a scripted transcript and a real one differ enough that a run you
rehearse offline is not the run that happens on the phone.

Filling a fixed schema on the call, while the person is still there to be asked, is both
cheaper and more accurate — and it means the planner is testable without a phone.
