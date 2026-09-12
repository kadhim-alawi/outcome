# Video production plan

Everything around the camera. The words to say are in
[`demo-script.md`](demo-script.md); this is setup, recording, editing and
publishing.

**Hard limit 2:59.** Judges are not required to watch past three minutes.

---

## Who you are making this for

Four named judges, from the overview page: AI Rudder's **CEO**, **Chief
Marketing & Revenue Officer**, **Head of GTM**, and **CALL-E's Product Manager**.
Three of four are commercial. None is an engineer.

They will not open the repository. This video *is* the project to them. Lead with
the problem and the cost; let the code speak through what it does on screen.

---

## 1 · Pre-production — about 30 minutes

### The machine

- **Do Not Disturb on.** Windows: `Win+N` → Focus. Kill Slack, Teams, mail,
  everything with a badge.
- **Close every other window.** Nothing in the taskbar you would not show a
  stranger.
- **Hide personal detail.** Desktop icons, browser bookmarks bar (`Ctrl+Shift+B`),
  any tab title with your name or an unrelated project.
- **Display at 1920×1080.** If your screen is larger, record a 1080p region
  rather than downscaling — text stays sharp.

### The browser

- **A fresh profile or a guest window.** No extensions, no autofill, no history
  dropdown when you click the address bar.
- **Zoom to 110–125%** (`Ctrl +`). What is comfortable on your monitor is
  unreadable on a laptop, and at least one judge will watch on a laptop.
- **Open the recording URL and leave it there:**
  ```
  http://127.0.0.1:8765/?pace=5000
  ```

### The terminal, for the live-proof shot

- **Font at 16–18pt minimum.** Same reason.
- **Dark theme, clean prompt.** A prompt showing a long path or a git branch is
  noise; `cd` somewhere short first.
- **Clear the scrollback** before each take.

### Audio

- **Wear a headset.** Not laptop speakers. This is not aesthetic advice — the
  live call transcript shows the agent's own voice echoing back into the mic,
  because the softphone was on speakers. The same will happen to your narration.
- **Quiet room, hard surfaces covered.** Phone on silent, face down, in another
  room.
- **Record a 10-second test and listen back on headphones** before the real take.
  Levels, plosives, room hum. This is the single most common thing that ruins an
  otherwise good hackathon video.

### The recorder

**OBS Studio** (free, obsproject.com) is the right tool. Windows Game Bar
(`Win+G`) cannot record the desktop or File Explorer and will bite you mid-take.

OBS settings:

| | |
|---|---|
| Base & output resolution | 1920×1080 |
| FPS | 30 |
| Encoder | x264 or hardware, quality "High" |
| Audio | **mic AND desktop audio, on separate tracks** — you need both sides of the call |
| Format | mp4 |

Add a **Display Capture** source, and an **Audio Input Capture** for the mic.
Check the audio meter moves when you speak and does *not* move when you don't.

### The app

```bash
python -m outcome.server        # leave running in a window you won't show
```

Verify before recording:

- The page loads at `?pace=5000`
- The badge reads **`mock · no calls placed`** — leave it in frame all the way
  through, it answers the sceptical question before it is asked
- **Reset** repopulates the form
- Every phone number renders masked, `+*******0002`

---

## 2 · Recording — two takes, not one

Do not attempt a single continuous take. Record two segments and join them. The
join is invisible and each segment becomes retakeable on its own.

### Segment A — the browser run (about 2:25)

Narrate live while you drive. Follow the beat table in
[`demo-script.md`](demo-script.md); every timing there is measured from an
instrumented run, not estimated.

The measured facts you are working against:

| Checkpoint | Measured at `?pace=5000` |
|---|---|
| Start → approval card | 55.5 s |
| Approve → result card | 20.9 s |
| Whole run | 76.4 s |

Everything after the approval card waits for your click, so that is where your
clock is your own.

**Type the goal, do not paste.** Typing reads as real.

**Hold three seconds on "Who to call first"** before clicking Start. One phone
number. That hold is what makes the two `New lead` rows land later.

**Stop talking when the approval card appears.** Let it sit.

### Segment B — a real call, with its real audio (about 28 s in the cut)

This is the segment worth the extra hour. Three of the four judges are
commercial; hearing the agent hold an actual conversation will land harder than
any terminal output.

You will record roughly four minutes and cut it to under thirty seconds.

**Audio setup — this is the part that goes wrong.** You need *both* sides clean:

| Source | Captures | OBS source |
|---|---|---|
| The agent's voice | Linphone's output | **Desktop Audio** (Audio Output Capture) |
| Your voice | you answering | **Mic** (Audio Input Capture) |

**Wear a headset.** Linphone's audio then reaches OBS digitally via Desktop
Audio, and never reaches your microphone — so there is no echo. On speakers, your
mic picks up the agent and both channels smear. Our own live transcript shows
exactly that failure: several lines repeat the agent's words back before the
human's reply.

Verify both meters move independently before you dial.

**On screen:** the terminal running the CLI. Nothing else.

**Record this:**

```bash
python -m outcome.cli run scenarios/local/live-smoke-test.json \
    --live --approve auto --store runs.sqlite3
```

Answer as the depot, exactly as in
[`live-call-rehearsal`](#) — *"Fifty insulated shipping boxes, three hundred and
eighty dollars. We can deliver on the sixteenth of September."* Reference
BWD-4471 if asked. Two calls, budget 2, ends **RESOLVED**.

Costs 2 credits. Do a full take even if you fluff a line — you are cutting it
down anyway, and a retake costs 2 more credits out of 200.

**The cut — four beats, hard cuts between them:**

| | On screen | Audio |
|---|---|---|
| ~4 s | `☎ Test depot (you) +*******9558` appears | ringing |
| ~9 s | terminal holding | *"Hi, I'm an AI assistant placing this call on behalf of a customer…"* |
| ~7 s | terminal holding | you: *"Yes, we can do that. Fifty boxes, three hundred and eighty dollars, the sixteenth of September."* |
| ~8 s | `✓ confirmed` → offer USD 380.00 → **RESOLVED** | let it land in silence |

**Do not narrate over this.** The real audio *is* the argument. One line before
the cut is enough, spoken at the end of Segment A:

> "Everything you have seen so far is a scripted rehearsal, so I can practise
> without spending credits. Here is the same engine, unchanged, on a real phone."

**Fallback if the call fails on the day.** The ledger shot still works and needs
no credits:

```bash
python -m outcome.cli calls --store runs.sqlite3 --all
```

It prints every real call id with status and timing. Leave the `failed` row in
frame — it is a true record, and hiding it would be the wrong instinct.

---

## 3 · The timeline

Total **2:56**, leaving three seconds of headroom. It is tight, and the tightness
is all in Segment A — Segment B is fixed-length footage.

| From | To | Beat | Source |
|---|---|---|---|
| 0:00 | 0:13 | The problem — a crushed pallet, one phone number | you |
| 0:13 | 0:28 | Create the outcome; requirements parse out of the sentence | Segment A |
| 0:28 | 1:24 | It works. **0:50 and 1:05 are the two `New lead` beats** | Segment A |
| 1:24 | 1:42 | The approval card. Let a viewer read it | Segment A |
| 1:42 | 2:03 | The commit call, with the `commits you` badge | Segment A |
| 2:03 | 2:16 | The point: three companies, you gave it one | Segment A |
| 2:16 | 2:20 | The one-line handoff: *"here is the same engine on a real phone"* | Segment A |
| 2:20 | 2:48 | **The real call** — ringing, the agent talking, RESOLVED | Segment B |
| 2:48 | 2:56 | Close on the tagline | either |

**If it overruns, take the seconds from 1:42–2:03** — the commit call in the mock
run, which the real call at 2:20 now demonstrates better anyway.

**Never cut 0:50, and never cut the agent's opening line at 2:24.** Those are the
two moments the whole video exists for: the frontier growing, and the thing
actually talking to a person.

---

## 4 · Editing — keep it minimal

You need almost no editing, and every effect you add is a risk.

- **Join the two segments.** A hard cut is fine. No transition.
- **Trim dead air** at the head and tail of each segment.
- **No music.** The rules bar copyrighted audio, and narration over silence is
  the norm for this format. Silence over a moving timeline reads as confidence.
- **No zooms, no callout arrows, no kinetic text.** At 110–125% browser zoom
  everything is already legible.
- **One title card at the end**, 3 seconds, holding the tagline:
  *Don't tell it who to call. Tell it what needs to happen.*

Free editors that are enough for this: **Clipchamp** (ships with Windows 11),
**DaVinci Resolve**, **Shotcut**.

### Captions — not optional

Judges watch muted. Clipchamp and YouTube Studio both auto-generate; **read them
back and fix the errors**, especially:

- Company names — Halden, Northgate, Brightwater
- The two `New lead` beats at 0:52 and 1:07
- Any figure: $612, $500, $438

A caption that says "five hundred" where you said "five hundred dollars" is
fine. One that garbles the rejected quote loses the whole technical argument.

---

## 5 · Before you export — the rules check

From [`rules-compliance.md`](rules-compliance.md):

- [ ] **Under three minutes.**
- [ ] **No copyrighted music.**
- [ ] **No third-party trademarks.** Keep the telephony provider's dashboard and
      the softphone out of frame. CALL-E's own name is fine — it is the sponsor.
- [ ] **Every phone number masked** — including in the live segment. The CLI
      masks to `+*******9558` itself, but check the frame, because that number is
      real and yours.
- [ ] **Shows the project functioning**, which is the explicit requirement.
- [ ] **English.**
- [ ] No personal data on screen — email, real numbers, other tabs.

Export **1080p, 30fps, mp4**.

---

## 6 · Publishing

**YouTube, and it must be Public.** The rules say "made publicly visible" —
Unlisted is a risk not worth taking.

**Title:**

```
OUTCOME — an AI agent that works out who to phone next (CALL-E Hackathon)
```

**Description:**

```
OUTCOME is an autonomous phone-work agent built on CALL-E.

You give it an outcome and the limits an answer has to satisfy — "a replacement
pallet of 500 insulated shipping boxes, at or under USD 500, delivered before
Friday" — and exactly one phone number. It works out who to call, calls them,
reads each result as structured evidence, checks any offer against your hard
limits, and follows referrals given on calls to companies you never supplied.

In this demo, two of the three companies it rings were never given to it. It
found them by asking the people it was already talking to.

The first run on screen uses the scripted transport, which is deterministic and
costs no credits to rehearse. From 2:20 it is a real CALL-E phone call, with the
real audio — the same engine, unchanged. Transcripts and structured results are
in the repository.

Repo: https://github.com/kadhim-alawi/outcome
Contributed skill: https://github.com/CALLE-AI/awesome-phone-call-agents/pull/369
Live call transcripts: https://github.com/kadhim-alawi/outcome/blob/main/docs/live-call-evidence.md

Built for CALL-E: Your Code Is Calling.
```

Then:

1. Copy the URL into the Devpost **Project details** step
2. Replace the `[TBD]` demo-video link in
   [`devpost-submission.md`](devpost-submission.md)
3. **Open the YouTube link in a private window** to confirm it really is public
4. Watch it once, muted, on a phone

---

## 7 · Order of work

| | |
|---|---|
| 1 | OBS installed, audio test recorded and listened back |
| 2 | One full rehearsal of Segment A, not recorded — just to feel the pacing |
| 3 | Record Segment A. Expect 2–4 takes |
| 4 | Record Segment B — the live call. Check both audio meters first |
| 5 | Join, trim, caption |
| 6 | Rules checklist |
| 7 | Export, upload **Public**, verify in a private window |
| 8 | Paste the URL into Devpost and into the submission doc |
| 9 | Submit — do not leave it as a draft |

Budget about three hours. Most of it is takes 2–4 of Segment A.

**Submission closes 14 September, 11:45pm SGT — 18:45 in Bahrain.** Devpost
drafts do not submit themselves.
