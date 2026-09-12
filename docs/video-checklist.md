# Video checklist

Work down the list. Don't skip ahead — a few steps save you from wasting credits
later.

The details behind any step are in [`video-plan.md`](video-plan.md),
[`narration.md`](narration.md) and
[`live-call-rehearsal.md`](live-call-rehearsal.md).

---

## Install (20 min)

- [ ] Install **OBS Studio** from obsproject.com
- [ ] Install **VB-CABLE** from vb-audio.com/Cable, then restart the PC
- [ ] Open your video editor. Clipchamp is already on Windows 11 and is enough

## Make the voices (40 min)

- [ ] Open ElevenLabs. Pick a calm, normal-sounding voice for the narrator
- [ ] Generate the 15 narration clips from [`narration.md`](narration.md). Save
      them as `01.mp3`, `02.mp3` and so on so they stay in order
- [ ] Listen to each one. Check it says the numbers properly — five hundred, six
      hundred and twelve, four hundred and thirty-eight
- [ ] Check it says "CALL-E" as *call-ee*. If not, type it as `Call-ee` and redo
- [ ] Now pick a **different** voice for the depot
- [ ] Generate the 5 depot clips from
      [`live-call-rehearsal.md`](live-call-rehearsal.md). Save as `A.mp3` to
      `E.mp3`

## Wire up the audio (20 min)

- [ ] In Linphone, set the **microphone** to `CABLE Output`
- [ ] In Linphone, set the **speaker** to your headset
- [ ] In Windows: Settings → System → Sound → Volume mixer. Find your media
      player and set its **output** to `CABLE Input`
- [ ] Put your headset on

## Test it without spending credits (10 min)

- [ ] Call your US number from your own mobile
- [ ] Answer it in Linphone
- [ ] Play `A.mp3`
- [ ] **Can your mobile hear it?** If yes, you're good. If it's silent, Linphone's
      microphone is set wrong. If it picks up your room, same problem
- [ ] Hang up

Don't go further until this works.

## Set up OBS (15 min)

- [ ] Add a **Display Capture** source
- [ ] Add an **Audio Output Capture** → your headset
- [ ] Add a second **Audio Output Capture** → `CABLE Input`
- [ ] Delete any microphone source. You don't want one
- [ ] Settings → Output → 1920x1080, 30fps, mp4
- [ ] Do the test call again and watch both audio meters move

## Record the real call (30 min)

- [ ] Turn on Do Not Disturb (`Win+N`)
- [ ] Close everything you wouldn't show a stranger
- [ ] Open a terminal, make the font big, clear the screen
- [ ] Have `A.mp3` to `E.mp3` ready to click
- [ ] Start recording in OBS
- [ ] Run this:
      ```
      python -m outcome.cli run scenarios/local/live-smoke-test.json --live --approve auto --store runs.sqlite3
      ```
- [ ] Answer in Linphone when it rings
- [ ] Play the clips as it asks for things. Order is in
      [`live-call-rehearsal.md`](live-call-rehearsal.md)
- [ ] **Wait for it to stop talking before you play a clip**
- [ ] Don't hang up. Let it finish
- [ ] It rings back a second time. Play `D.mp3`
- [ ] Wait for **RESOLVED** on screen, then stop recording

That's 2 credits. You've got 200, so do it again if it's messy.

## Record the browser (30 min)

This one has **no sound at all**. Just the picture.

- [ ] Start the server: `python -m outcome.server`
- [ ] Open `http://127.0.0.1:8765/?pace=5000`
- [ ] Zoom the browser to about 120% (`Ctrl +`)
- [ ] Hide the bookmarks bar (`Ctrl+Shift+B`)
- [ ] Mute the audio sources in OBS, or just ignore them
- [ ] Start recording
- [ ] **Type** the goal (don't paste it)
- [ ] Click "Read the requirements out of this"
- [ ] Scroll to "Who to call first" and **stop for three seconds**
- [ ] Click Start and let it run
- [ ] When the approval card appears, wait a few seconds, then click Approve
- [ ] Wait for the result card, then stop recording

Do it a couple of times and keep the best one. It costs nothing.

## Edit (60 min)

- [ ] Put the browser recording on the timeline first
- [ ] Lay the narration clips over it, following the times in
      [`narration.md`](narration.md)
- [ ] Add the live call recording at the end. Cut it down to about 25 seconds:
      the phone ringing, the agent's first line, the depot answering, then
      RESOLVED
- [ ] **No narration over the call.** Let the real audio play
- [ ] Add a 3-second end card with: *Don't tell it who to call. Tell it what
      needs to happen.*
- [ ] No music
- [ ] Check the whole thing is **under 2 minutes 59 seconds**

## Captions (20 min)

- [ ] Auto-generate captions
- [ ] Read them back and fix the mistakes
- [ ] Especially the numbers, and the company names — Halden, Northgate,
      Brightwater

## Last look before you upload

- [ ] Under 2:59
- [ ] No music
- [ ] No Telnyx or Linphone logos on screen
- [ ] Every phone number shows as `+*******9558` or `+*******0002`
- [ ] No personal email, no other browser tabs, nothing private
- [ ] Watch it once with the sound off. Does it still make sense?

## Upload (20 min)

- [ ] Export as 1080p mp4
- [ ] Upload to YouTube
- [ ] Set it to **Public**. Not Unlisted
- [ ] Copy the title and description from
      [`video-plan.md`](video-plan.md)
- [ ] Open the link in a private window to check it really is public

## Submit (15 min)

- [ ] Go to your Devpost submission
- [ ] **Project details** step: paste the video link
- [ ] **Additional info** step: fill it in from
      [`devpost-submission.md`](devpost-submission.md)
- [ ] Put in your CALL-E account email
- [ ] Paste the PR link: `https://github.com/CALLE-AI/awesome-phone-call-agents/pull/369`
- [ ] Go through every step until it says 5 of 5
- [ ] **Press submit.** A draft doesn't count

---

## If something breaks

**The audio routing won't work.** Give it 30 minutes, then stop. Skip the live
call and record this instead — it needs no audio and no credits:

```
python -m outcome.cli calls --store runs.sqlite3 --all
```

It shows the real call IDs from the calls you already made. Not as good, but the
video still ships.

**The live call goes wrong.** Just run it again. It's 2 credits.

**You're running out of time.** Cut the live call section entirely. A clean
2:30 video of the browser demo is much better than a rushed 2:59 one.

---

**Deadline: Sunday 14 September, 6:45pm your time.**
