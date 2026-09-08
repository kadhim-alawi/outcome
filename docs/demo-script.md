# The three-minute demo

Hard limit is 2:59.

**Record at `http://127.0.0.1:8765/?pace=5000`.** The default 900ms feels right
when you are driving the UI yourself and is far too fast to narrate over — the
whole run lands in 14.7 seconds, so you would be talking over a finished screen.
`?pace=5000` stretches it to 76 seconds, which is the speed somebody can talk
through. Adjust between takes without touching the code; the clamp is 100–15000.

Every timing below is **measured**, not estimated — from an instrumented run at
`?pace=5000` that stamps each row as it lands. Times are given as clock
positions assuming you click **Start** at 0:32.

| Checkpoint | Measured |
|---|---|
| Start → approval card | 55.5 s |
| Approve → result card | 20.9 s |
| Whole run | 76.4 s |

Everything after the approval card is under your control, since the run waits
for the click.

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

## 0:32 — 1:28 · It works

Do not narrate every row — there are ten and you have about five seconds each.
Say one line per beat and let the rest run silent. Silence over a moving
timeline reads as confidence; filler over it reads as a tour.

| Lands at | On screen | Say |
|---|---|---|
| 0:32 | `☎ Call Halden Packaging — can they fix this, and if not, who can?` | *(let it go)* |
| 0:37 | `Halden Packaging — no answer` | "Nobody picks up." |
| 0:42 | `☎ Nobody answered at Halden Packaging. Trying again.` | — |
| 0:47 | `Halden Packaging — blocked` · out of stock until the 30th | "Second try. They're out of stock — they can't help." |
| **0:52** | **`New lead: Northgate Distribution`** | **"But they told it who could. That number came out of the phone call."** |
| 0:57 | `☎ Call Northgate Distribution` | — |
| 1:02 | offer **USD 612.00** · `REJECTED` · `✗ $112 over the USD 500.00 limit` | "Northgate has stock. Six twelve — over my limit, so it turns it down." |
| 1:07 | **`New lead: Brightwater Depot`** | "And Northgate points at their own depot. No courier surcharge." |
| 1:12 | `☎ Call Brightwater Depot` | — |
| 1:17 | offer **USD 438.00** · `MEETS YOUR REQUIREMENTS` | "Four thirty-eight. Thursday. Inside both rules." |
| 1:28 | approval card appears | *(stop talking)* |

**0:52 is the beat the whole video exists for.** If the edit has to lose ten
seconds, take them from 0:57–1:12, never from here.

---

## 1:28 — 1:53 · Approval

The approval card is on screen with all three checks and the turned-down offer.
**The run is waiting for you here**, so this section is the one place the clock
is entirely yours — take the time to let a viewer read the card.

> "It found something that works — and it stops.
>
> Nothing so far committed me to anything. Those calls were only allowed to
> ask. This one is allowed to say yes, so it's mine to authorise.
>
> It shows me what it's accepting, that both my rules are met, and what it
> turned down to get here."

Click **Approve**.

---

## 1:53 — 2:14 · The commit call

Measured from the click, so these land on their own:

| After the click | On screen |
|---|---|
| +0s | `You approved it` |
| +5s | `☎ Call Brightwater Depot back to accept…` with the **commits you** badge |
| +10s | `Brightwater Depot — confirmed` |
| +21s | Result card |

> "One call is authorised, and only for these exact terms. If the price or the
> date had moved by the time it got through, it was told to walk away and come
> back to me."

Result card: **RESOLVED**, `Reference BWD-48291`, three green checks,
`5 of 6 calls used.`

---

## 2:14 — 2:40 · The point

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

## 2:40 — 2:55 · Close

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
- **Captions.** Judges watch muted. The 0:52 and 1:07 lead beats especially.
- **Re-measure if you change the pace.** `scripts/time_demo.mjs` stamps every
  row as the page appends it, which is where the numbers above came from:

  ```bash
  python3 -m outcome.server &
  npm install playwright && npx playwright install chromium
  node scripts/time_demo.mjs 5000
  ```
- **Check the masking.** Every number on screen must render `+*******0002`.
  Nothing in this scenario is real, but the frame is what a viewer copies.
