# The three-minute demo

Hard limit is 2:59. Everything below is timed against the real UI at
`python3 -m outcome.server`, with `STEP_DELAY = 900` in `web/index.html` —
that is the knob that controls pacing, and it is the only thing to tune if the
cut runs long.

The single job of this video: make the viewer notice that **two of the three
companies on screen were never typed in by the user.**

---

## 0:00 — 0:18 · The problem

Screen: the crushed pallet, or the order line `BK-7741 — DAMAGED ON ARRIVAL`.

> "A pallet of shipping boxes arrived crushed. I need a replacement before
> Friday, and I can't spend more than $500.
>
> I have one phone number: the supplier who sent me the broken one."

Say *one phone number* clearly. It is the setup for the whole video.

---

## 0:18 — 0:32 · Create the outcome

Type into the box, do not paste. Typing reads as real; pasting reads as a
rehearsal.

> Get a replacement pallet of 500 insulated shipping boxes for the crushed
> delivery on order BK-7741.

Click **Read the requirements out of this**. The requirement rows fill
themselves in — `budget · Total cost at or under USD 500 · must`, and
`deadline · Resolved on or before 2026-09-11 · must`.

> "I'm not creating a call. I'm creating an outcome: the goal, and the rules any
> answer has to satisfy. **Must**, not *prefer* — an answer that breaks one of
> these is not an answer."

Now scroll one line to **Who to call first** and **hold there for three
seconds**. One row: Halden Packaging.

> "And that's everything I've given it. One phone number."

That hold is the setup for the last shot of the video. Do not rush it.

Click **Start**.

---

## 0:32 — 1:35 · It works

Do not narrate every row. Say one line per beat and let the timeline run.

| Time | On screen | Say |
|---|---|---|
| 0:32 | `☎ Call Halden Packaging` → `no answer` | "Nobody picks up." |
| 0:38 | `Trying again` → `blocked` | "Second try. They're out of stock until the 30th — they can't help." |
| 0:46 | **`New lead: Northgate Distribution`** | **"But they told it who could. That number came out of the phone call."** |
| 0:56 | `☎ Call Northgate` → offer **$612** `REJECTED`, `✗ $112 over the USD 500.00 limit` | "Northgate has stock. Six twelve. That's over my limit — so the agent turns it down." |
| 1:10 | **`New lead: Brightwater Depot`** | "And Northgate points at their own depot: same stock, no courier surcharge." |
| 1:20 | `☎ Call Brightwater` → offer **$438** `MEETS YOUR REQUIREMENTS` | "Four thirty-eight. Thursday. Inside both rules." |

The 0:46 beat is the one that matters. Pause on it. If the edit needs to lose
ten seconds, take them from 0:56, not here.

---

## 1:35 — 2:05 · Approval

The approval card is on screen with all three checks and the turned-down offer.

> "It found something that works — and it stops.
>
> Nothing so far committed me to anything. Those calls were only allowed to
> ask. This one is allowed to say yes, so it's mine to authorise.
>
> It shows me what it's accepting, that both my rules are met, and what it
> turned down to get here."

Click **Approve**.

---

## 2:05 — 2:35 · The commit call

`☎ Call Brightwater Depot back to accept` with the **commits you** badge, then
`confirmed`.

> "One call is authorised, and only for these exact terms. If the price or the
> date had moved by the time it got through, it was told to walk away and come
> back to me."

Result card: **RESOLVED**, `Reference BWD-48291`, three green checks,
`5 of 6 calls used.`

---

## 2:35 — 2:50 · The point

Hold on the party list at the bottom of the result card:

```
Halden Packaging       · 2 calls · blocked
Northgate Distribution · 1 call  · offer      · found by the agent
Brightwater Depot      · 2 calls · confirmed  · found by the agent
```

> "Three companies. I gave it one.
>
> It found the other two by asking the people it was already talking to."

---

## 2:50 — 2:59 · Close

> "CALL-E can make a phone call.
>
> This decides which phone call to make next."

Last frame: the tagline. *Don't tell it who to call. Tell it what needs to happen.*

---

## Production notes

- **Screen-record the mock run.** Deterministic, repeatable, and 20 free credits
  do not survive rehearsals. Say plainly in the Devpost text that the video is
  the mock transport and that `--live` runs the identical engine — the repo's
  own conventions expect a dry-run/no-call default, so this is a strength.
- **Record the live proof separately.** One real call, screen plus audio, as a
  second linked video or a GIF in the README. Do not try to fit it in the three
  minutes.
- **Do not show the constraint JSON, the code, or the architecture diagram.**
  A reviewer who wants those opens the repo. Spend all 179 seconds on the agent
  doing the thing.
- **Use the Reset button between takes.** It repopulates the form from the
  selected scenario, so every take starts identical. The scenario dropdown
  already opens on the supplier run.
- **Leave the `mock · no calls placed` badge in frame.** It is the first thing a
  sceptical reviewer looks for, and answering the question before it is asked is
  worth more than the pixels it costs.
- **Captions.** Judges watch muted. The 0:46 and 1:10 lead beats especially.
- **Check the masking.** Every number on screen must render `+*******0002`.
  Nothing in this scenario is real, but the frame is what a viewer copies.
