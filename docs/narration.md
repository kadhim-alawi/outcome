# Narration script — for text-to-speech

Fifteen clips, generated separately and laid over silent screen footage. Each has
a target duration; the word counts are written to land near it at a normal
narration pace of roughly 150 words per minute.

**Generate each clip as its own file.** One long take gives you no way to nudge a
line that lands early, and re-generating a single clip is free.

**Numbers are spelled out deliberately.** Every text-to-speech engine mangles
`$612` and `BK-7741` sooner or later, and a garbled figure loses the argument the
shot exists to make.

---

## 01 · The problem — 13 s

> A pallet of shipping boxes arrived crushed. I need a replacement before Friday,
> for under five hundred dollars. And I have exactly one phone number: the
> supplier who sent the broken one.

*32 words. Lands over the order line or the crushed pallet.*

## 02 · Creating the outcome — 14 s

> So I don't create a call. I create an outcome — the goal, and the rules any
> answer has to satisfy. Must, not prefer. An answer that breaks one of these
> isn't an answer.

*34 words. Over the requirement rows filling themselves in.*

## 03 · The hold — 4 s

> And that's everything I've given it. One number.

*9 words. Over the three-second hold on "Who to call first". Do not rush this.*

---

## 04 · No answer — 2 s

> Nobody picks up.

## 05 · Blocked — 4 s

> Second try. They're out of stock, so they can't help.

## 06 · **The lead beat** — 6 s

> But they told it who could. That number came out of the phone call.

*This is the line the whole video exists for. It lands at 0:50, on the first
`New lead` row. If anything in the edit has to move, move something else.*

## 07 · The rejected offer — 7 s

> Northgate has stock. Six hundred and twelve dollars — over my limit. So it
> turns it down.

## 08 · The second lead — 5 s

> And Northgate points at their own depot. No courier surcharge.

## 09 · The good offer — 4 s

> Four hundred and thirty-eight. Thursday. Inside both rules.

---

## 10 · The approval card — 15 s

> It found something that works — and it stops. Nothing so far committed me to
> anything; those calls were only allowed to ask. This one is allowed to say yes,
> so it's mine to authorise.

*35 words. Let the card sit on screen after the line ends.*

## 11 · The commit call — 14 s

> One call is authorised, and only for these exact terms. If the price or the
> date had moved by the time it got through, it was told to walk away and come
> back to me.

*35 words, over a 21-second beat. The silence at the end is intentional.*

## 12 · The point — 9 s

> Three companies. I gave it one. It found the other two by asking the people it
> was already talking to.

*21 words over 13 seconds. Let it breathe.*

## 13 · The handoff — 5 s

> That was a scripted rehearsal. Here's the same engine, on a real phone.

---

## 14 · The real call — 28 s, NO NARRATION

Real audio only: the line ringing, the agent's own voice, the answer, and
`RESOLVED` landing. **Do not put a generated voice over this.** The whole point
of the segment is that it is not produced.

---

## 15 · Close — 6 s

> CALL-E can make a phone call. This decides which phone call to make next.

*Over the final title card holding the tagline.*

---

# Generating it

## Voice

Pick a **measured, neutral voice** from the stock library. Demo narration fails
far more often from over-enthusiasm than from being too flat — the material is
already interesting, and an excited read makes it sound like an advert.

**Use a library voice, not a clone of a real person.** The rules require that the
submission not violate anyone's rights of publicity, and a cloned voice is
exactly the sort of thing that becomes a problem after you have won something.
Check your plan permits commercial use, and keep whatever attribution it requires.

## Settings worth starting from

| | |
|---|---|
| Stability | around 50 — steady without going robotic |
| Similarity | 70–80 |
| Style exaggeration | low or zero |
| Speaker boost | on |

## Listen for these before you commit

- **"CALL-E"** — it should be *call-ee*, two syllables. If it says "cally" or
  spells out the letters, write it as `Call-ee` in the input and check again.
- **"Northgate", "Brightwater", "Halden"** — should be fine, but confirm clip 07
  and 08 do not stress them oddly.
- **Every figure.** Five hundred, six hundred and twelve, four hundred and
  thirty-eight. These carry the technical argument.
- **Sentence-final falls.** Clips 06 and 12 are the two lines that have to land.
  If either ends on a rising tone, regenerate.

---

# What this changes in the recording

Text-to-speech removes most of the audio preparation and one whole class of
retake. It also reverses the order of work.

**Record the screen silent.** Segment A becomes a pure screen capture — no
microphone, no room noise, no plosives, no neighbour. Take it as many times as
you like.

**Then fit the voice to the picture, not the other way round.** This is the real
advantage: if clip 07 lands two seconds early, regenerate it slightly longer, or
move it. You are no longer trying to perform to a stopwatch.

**Keep about half a second of silence** at the head of each clip so lines do not
collide with the row appearing on screen.

## Both sides of the live call are generated too

Segment B has no human voice either. The depot's replies are pre-generated clips
played into the line through a virtual audio cable, so the recording carries the
agent's real voice and a synthetic depot, and nothing of yours.

The routing, the clips and the rehearsal step are in
[`live-call-rehearsal.md`](live-call-rehearsal.md). Two things from it that
matter here:

- **Use a different voice for the depot.** Narrator and depot sounding like the
  same person is the one detail that would make the whole thing read as staged.
- **Rehearse the routing on a free call first**, ringing the number from your own
  mobile. A take that fails on audio still costs the credits.
