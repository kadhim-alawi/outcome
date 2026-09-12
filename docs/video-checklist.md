# Video checklist

Everything you need is on this page. Work down it in order.

---

# Step 1 — Install three things (20 min)

- [ ] **OBS Studio** — obsproject.com. This records the screen.
- [ ] **VB-CABLE** — vb-audio.com/Cable. This lets you play audio into a phone
      call. Restart the PC after installing.
- [ ] **A video editor.** Clipchamp is already on Windows 11 and does everything
      you need. Search for it in the Start menu.

---

# Step 2 — Make the narrator's voice (30 min)

Open ElevenLabs. Pick one calm, normal-sounding voice. Not excited — the demo is
already interesting and an excited voice makes it sound like an advert.

Settings to start with: Stability 50, Similarity 75, Style 0, Speaker boost on.

Generate each of these as its own file. Save them with these names.

### `01.mp3`
```
A pallet of shipping boxes arrived crushed. I need a replacement before Friday,
for under five hundred dollars. And I have exactly one phone number: the supplier
who sent the broken one.
```

### `02.mp3`
```
So I don't create a call. I create an outcome — the goal, and the rules any
answer has to satisfy. Must, not prefer. An answer that breaks one of these isn't
an answer.
```

### `03.mp3`
```
And that's everything I've given it. One number.
```

### `04.mp3`
```
Nobody picks up.
```

### `05.mp3`
```
Second try. They're out of stock, so they can't help.
```

### `06.mp3`
```
But they told it who could. That number came out of the phone call.
```

### `07.mp3`
```
Northgate has stock. Six hundred and twelve dollars — over my limit. So it turns
it down.
```

### `08.mp3`
```
And Northgate points at their own depot. No courier surcharge.
```

### `09.mp3`
```
Four hundred and thirty-eight. Thursday. Inside both rules.
```

### `10.mp3`
```
It found something that works — and it stops. Nothing so far committed me to
anything; those calls were only allowed to ask. This one is allowed to say yes,
so it's mine to authorise.
```

### `11.mp3`
```
One call is authorised, and only for these exact terms. If the price or the date
had moved by the time it got through, it was told to walk away and come back to
me.
```

### `12.mp3`
```
Three companies. I gave it one. It found the other two by asking the people it
was already talking to.
```

### `13.mp3`
```
That was a scripted rehearsal. Here's the same engine, on a real phone.
```

### `14.mp3`
```
CALL-E can make a phone call. This decides which phone call to make next.
```

## Now listen to all fourteen

- [ ] Do the numbers sound right? Five hundred. Six hundred and twelve. Four
      hundred and thirty-eight.
- [ ] Does `14.mp3` say **call-ee**? If it says "cally" or spells out the
      letters, change the text to `Call-ee can make a phone call.` and generate
      it again.
- [ ] Do `06.mp3` and `12.mp3` end on a downward tone? Those are your two best
      lines. If either sounds like a question, generate it again.

---

# Step 3 — Make the depot's voice (15 min)

Now pick a **different** voice. If the narrator and the depot sound like the same
person, the whole thing looks staged.

These are what gets played down the phone to the agent.

### `A.mp3` — the main answer
```
Yes, we can do that. Fifty insulated shipping boxes, three hundred and eighty
dollars. We can deliver on the sixteenth of September.
```

### `B.mp3` — confirming
```
Yes, that's correct.
```

### `C.mp3` — the reference number
```
Your reference is seven seven four one.
```

### `D.mp3` — for the second call
```
That's right. Three hundred and eighty dollars, delivered on the sixteenth. Your
order reference is seven seven four one.
```

### `E.mp3` — answering the phone
```
Hello, depot speaking.
```

- [ ] Put all five somewhere you can click them fast. A folder on the desktop is
      fine.

---

# Step 4 — Wire up the audio (20 min)

You're going to play those clips down the phone line instead of speaking.

- [ ] Put your headset on. Not speakers.
- [ ] Open Linphone → Settings → Audio
- [ ] Set the **microphone** to `CABLE Output (VB-Audio Virtual Cable)`
- [ ] Set the **speaker** to your headset
- [ ] Open Windows Settings → System → Sound → Volume mixer
- [ ] Find whatever app plays your mp3 files, and set its **output** to
      `CABLE Input (VB-Audio Virtual Cable)`

What this does: the agent's voice comes into your headset, and your clips go out
down the phone line. Your actual microphone is not used at all.

---

# Step 5 — Test it without spending anything (10 min)

- [ ] Ring your US number from your own mobile
- [ ] Answer it in Linphone
- [ ] Play `A.mp3`
- [ ] **Can you hear it on your mobile?**
- [ ] Hang up

If your mobile hears the clip, you're ready.

If it hears nothing, Linphone's microphone isn't set to `CABLE Output`.
If it hears your room, same problem.

**Don't move on until this works.** A recording with no sound still costs
credits.

---

# Step 6 — Set up OBS (15 min)

- [ ] Open OBS. In the Sources box, click **+**
- [ ] Add **Display Capture** → pick your main screen
- [ ] Add **Audio Output Capture** → pick your headset. Rename it "agent"
- [ ] Add another **Audio Output Capture** → pick `CABLE Input`. Rename it
      "depot"
- [ ] If there's a **Mic/Aux** source in the list, delete it. You don't want one.
- [ ] Settings → Video → set both resolutions to 1920x1080, FPS 30
- [ ] Settings → Output → Recording format **mp4**
- [ ] Do the test call from Step 5 again, and watch both audio meters move

---

# Step 7 — Record the real phone call (30 min)

- [ ] Press `Win+N` and turn on Do Not Disturb
- [ ] Close every window you wouldn't show a stranger
- [ ] Open a terminal. Make the font big — 16pt or more
- [ ] Clear the screen so it starts empty
- [ ] Have `A.mp3` to `E.mp3` open and ready to click
- [ ] Press **Start Recording** in OBS
- [ ] Run this:

```
python -m outcome.cli run scenarios/local/live-smoke-test.json --live --approve auto --store runs.sqlite3
```

Your phone rings. Answer it in Linphone.

Then play clips as it asks for things:

| It says something like | You play |
|---|---|
| "Hi, I'm an AI assistant placing this call on behalf of a customer" | `E.mp3`, or nothing |
| "Can you supply fifty insulated shipping boxes, delivered by September seventeenth, under five hundred dollars?" | `A.mp3` |
| "Just to confirm, that's fifty boxes for three hundred and eighty dollars, delivered September sixteenth" | `B.mp3` |
| "Do you have a reference number?" | `C.mp3` |
| "Thank you, I'll let the customer know" | nothing — let it hang up |

- [ ] **Wait for it to finish talking before you play a clip.** If you talk over
      it, the transcript comes out garbled.
- [ ] Don't hang up yourself. Let it end the call.

It rings back a second time after a few seconds:

| It says something like | You play |
|---|---|
| "Can you confirm fifty boxes for three hundred and eighty dollars, delivered the sixteenth?" | `D.mp3` |
| "Thank you, I have the reference number" | nothing |

- [ ] Wait until the terminal shows **RESOLVED**
- [ ] Press **Stop Recording**

That cost 2 credits. You have about 200. If it came out messy, do it again.

---

# Step 8 — Record the browser demo (30 min)

This one has **no sound**. Just the picture. You'll add the voice later.

- [ ] Open a terminal and run:

```
python -m outcome.server
```

- [ ] Open this in your browser:

```
http://127.0.0.1:8765/?pace=5000
```

- [ ] Press `Ctrl +` three times to zoom to about 120%
- [ ] Press `Ctrl+Shift+B` to hide the bookmarks bar
- [ ] Press **Start Recording** in OBS

Now do this, slowly:

- [ ] Click in the goal box and **type** this (don't paste it — typing looks
      real):

```
Get a replacement pallet of 500 insulated shipping boxes for the crushed delivery on order BK-7741.
```

- [ ] Click **Read the requirements out of this**. The requirement rows fill
      themselves in.
- [ ] Scroll down one line to **Who to call first**
- [ ] **Stop. Count to three.** There's one company in that list. This pause is
      what makes the rest of the video work.
- [ ] Click **Start**
- [ ] Let it run. Don't touch anything. Rows appear one at a time.
- [ ] When the **approval card** appears, wait about five seconds so a viewer can
      read it
- [ ] Click **Approve**
- [ ] Wait for the result card at the end
- [ ] Press **Stop Recording**

- [ ] Watch it back. If you rushed anything, do it again — this one is free.

---

# Step 9 — Edit it together (60 min)

Open Clipchamp (or whatever editor you're using).

- [ ] Put the **browser recording** on the timeline first
- [ ] Drag the narration clips on top, so each one plays when its moment appears
      on screen:

| Play this | When you see |
|---|---|
| `01.mp3` | the very start |
| `02.mp3` | the requirement rows filling in |
| `03.mp3` | the pause on "Who to call first" |
| `04.mp3` | "Halden Packaging — no answer" |
| `05.mp3` | "Halden Packaging — blocked", out of stock |
| `06.mp3` | **"New lead: Northgate Distribution"** |
| `07.mp3` | the USD 612 offer being rejected |
| `08.mp3` | **"New lead: Brightwater Depot"** |
| `09.mp3` | the USD 438 offer being accepted |
| `10.mp3` | the approval card |
| `11.mp3` | the call back to Brightwater |
| `12.mp3` | the result card, on the list of three companies |
| `13.mp3` | right at the end, just before you cut to the phone call |

- [ ] Now add the **phone call recording** at the end
- [ ] Cut it down to about 25 seconds. Keep only these bits:
      - the phone ringing
      - the agent saying "Hi, I'm an AI assistant placing this call..."
      - the depot answering with the price and the date
      - the terminal showing **RESOLVED**
- [ ] **Don't put any narration over the phone call.** The real audio is the
      whole point.
- [ ] Add `14.mp3` at the very end
- [ ] Add a plain text card under it for 3 seconds:

```
Don't tell it who to call. Tell it what needs to happen.
```

- [ ] **No music.** The rules don't allow it.
- [ ] Check the total length. It must be **under 2 minutes 59 seconds.**

---

# Step 10 — Add captions (20 min)

Judges watch with the sound off, so this matters.

- [ ] Use your editor's auto-caption button
- [ ] Read every caption and fix the mistakes
- [ ] Check these especially:
      - Halden, Northgate, Brightwater
      - five hundred, six hundred and twelve, four hundred and thirty-eight
      - CALL-E

---

# Step 11 — Check before you upload (10 min)

- [ ] Under 2 minutes 59 seconds
- [ ] No music
- [ ] No Telnyx or Linphone logos anywhere on screen
- [ ] Every phone number shows with stars, like `+*******9558`
- [ ] No personal email, no other browser tabs, nothing private in shot
- [ ] Watch it once with the sound **off**. Does it still make sense?

---

# Step 12 — Put it on YouTube (20 min)

- [ ] Export as 1080p mp4
- [ ] Upload to YouTube
- [ ] Set visibility to **Public**. Not Unlisted — the rules say publicly visible.
- [ ] Title:

```
OUTCOME — an AI agent that works out who to phone next (CALL-E Hackathon)
```

- [ ] Description:

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

- [ ] Copy the video link
- [ ] Open it in a private browsing window to check it really plays

---

# Step 13 — Finish the Devpost submission (20 min)

Go to your submission on Devpost. There are 5 steps and you've done 2.

## Project details step

- [ ] Paste your YouTube link in the video field
- [ ] The long written description — the Inspiration, What it does, How we built
      it sections — is a few pages long, so it lives in
      [`devpost-submission.md`](devpost-submission.md). Copy each section into
      the matching box.

## Additional info step

Type these in:

| Field | What to put |
|---|---|
| Submitter Type | Individual |
| Country of residence | Bahrain |
| Organization name | leave empty |
| App status | Newly created |
| Optional demo URL | leave empty |
| Primary use case | Order / exception follow-up |
| CALL-E account email | your CALL-E email |
| The three checkboxes | tick all three |

- [ ] Pull request URL:

```
https://github.com/CALLE-AI/awesome-phone-call-agents/pull/369
```

- [ ] "If pre-existing, explain what you updated" — it's a required box even
      though it doesn't apply to you. Paste this:

```
Not applicable — newly created. The repository was empty before this hackathon;
its first commit is dated 5 September 2026, inside the submission period, and the
full history is public at https://github.com/kadhim-alawi/outcome/commits/main
```

- [ ] "In one sentence, what real-world task does your app handle?" — paste this:

```
Chasing a stuck order to a resolution that meets a hard budget and deadline,
starting from one phone number and finding the rest of the companies to call by
asking the people it reaches.
```

- [ ] "Testing instructions" — this one is long. It's in
      [`devpost-submission.md`](devpost-submission.md) under *Testing
      instructions for application*. Copy the whole block.

## Then

- [ ] Click through every step until it says **5 of 5 steps done**
- [ ] **Press Submit.** A draft doesn't count as an entry.
- [ ] Check your email for the confirmation

---

# If something goes wrong

**The audio routing won't work.**
Give it 30 minutes, then give up on it. Skip Step 7 entirely. Instead, record
your terminal running this — it needs no audio and no credits:

```
python -m outcome.cli calls --store runs.sqlite3 --all
```

It prints the real call IDs from the calls you already made. Show that for 15
seconds instead of the phone call. Not as good, but the video still works.

**The phone call goes badly.**
Just run it again. It's 2 credits and you have about 200.

**You're running out of time.**
Drop the phone call section completely. A clean 2 minute 30 video of the browser
demo is better than a rushed 2:59.

**Nothing is working and it's Sunday afternoon.**
Record the browser demo with no narration at all, upload it, and submit. A silent
demo that exists beats a perfect one that doesn't.

---

**Deadline: Sunday 14 September, 6:45pm Bahrain time.**
