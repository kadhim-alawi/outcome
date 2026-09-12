# The live call — playing generated audio as the depot

Your side of the call is pre-generated and played into the line, so no human
voice appears in the video at all. This is what
[`video-plan.md`](video-plan.md) Segment B records.

It works, but the audio routing is fiddly and the rehearsal step below is not
optional. **Test it without CALL-E first** — that costs nothing, and discovering
the cable is wired backwards while a paid agent waits on the line is a bad way to
find out.

---

## 1 · Route generated audio into the call

Install **VB-CABLE** (free, vb-audio.com/Cable). It creates a virtual device
pair: anything played to `CABLE Input` is heard by anything listening on
`CABLE Output`.

| | Set to |
|---|---|
| Linphone → Audio → **Capture / microphone** | `CABLE Output (VB-Audio Virtual Cable)` |
| Linphone → Audio → **Playback** | your headset |
| Your media player's **output device** | `CABLE Input (VB-Audio Virtual Cable)` |

On Windows, set the player's output per-app: **Settings → System → Sound →
Volume mixer →** pick the app **→ Output device**.

The agent's voice now arrives in your headset. Your clips go down the line and
you never speak.

### What OBS needs to capture

Two separate outputs, or the recording will have only half the conversation:

| OBS source | Device | Captures |
|---|---|---|
| Audio Output Capture 1 | your headset | the agent |
| Audio Output Capture 2 | `CABLE Input` | the depot clips |

Watch both meters move during the rehearsal call. **No microphone source at
all** — if one is enabled you will record the room.

## 2 · Rehearse with a free call

Before spending a single credit:

1. Ring the US number **from your own mobile**
2. Answer in Linphone
3. Play clip **A** from your media player
4. Confirm you hear it **on your mobile**, and that both OBS meters moved

If your mobile hears silence, the capture device is wrong. If it hears your
room, Linphone is still on the real microphone.

---

## 3 · The clips

**The five clips and their exact words are in
[`video-checklist.md`](video-checklist.md), step 3**, so there is one copy and it
is the one you work from. Use a different voice from the narrator.

Keep them short and separate. The agent's phrasing varies between calls, so you
are answering what it actually asks rather than playing a script in order.

---

## Why the reference is numeric now

The first live run used `BWD-4471`. The agent heard `BWD4471` on call one and
`DWD4471` on call two — B and D are nearly identical over a phone line, and the
resolved outcome carried the wrong one.

That was an honest artifact and it is written up in
[`live-call-evidence.md`](live-call-evidence.md), but it is not what you want
on screen in a three-minute video. **A numeric reference cannot drift**, so the
recording gets a clean result and the transcript in the repository keeps the
interesting failure.

---

## 4 · How the call actually goes

From the two live runs we have, the flow is stable:

| The agent | You play |
|---|---|
| *"Hi, I'm an AI assistant placing this call on behalf of a customer."* | **E** — or nothing, it continues on its own |
| *"Could you help me check whether you can supply fifty insulated shipping boxes and deliver them by September seventeenth, for a total cost at or under five hundred US dollars?"* | **A** |
| *"Just to confirm, that's fifty insulated shipping boxes for three hundred and eighty dollars, delivered September sixteenth."* | **B** |
| *"Do you have a reference number for this arrangement?"* | **C** |
| *"Thank you, I'll let the customer know and they'll confirm shortly."* | nothing — let it hang up |

Then the approval passes automatically and it rings back:

| The agent | You play |
|---|---|
| *"Can you confirm you can supply fifty insulated shipping boxes for three hundred and eighty dollars total, delivered on September sixteenth?"* | **D** |
| *"Thank you, I have the reference number."* | nothing |

**Wait for it to finish speaking before you play a clip.** It listens for a pause
to know its turn has ended, and talking over it produces the smeared transcript
we already have one example of.

**Do not hang up first.** It needs a moment after the conversation to fill in the
result schema.

---

## 5 · The command

```bash
python -m outcome.cli run scenarios/local/live-smoke-test.json \
    --live --approve auto --store runs.sqlite3
```

Two calls, budget two, ends **RESOLVED**. Costs 2 credits per take out of 200,
so take it as many times as you need — but rehearse the routing first, because
a take that fails on audio still costs the credits.

## If it goes wrong on the day

The agent handles an unanswered question fine; it records what it was told and
moves on. A run that ends `blocked` or `partial` is still a real call and still
proves the integration — but it is not the frame you want at 2:20.

If the routing fights you, stop. Fall back to
[`video-plan.md`](video-plan.md)'s no-credit ledger shot:

```bash
python -m outcome.cli calls --store runs.sqlite3 --all
```

The video ships either way. The routing is worth thirty minutes, not three hours.
