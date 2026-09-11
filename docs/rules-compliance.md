# Rules compliance

Checked against the [Official Rules](https://call-e.devpost.com/rules) on
11 September 2026. Anything that needs action is marked **ACTION**.

---

## Dates

| | |
|---|---|
| Submission Period ends | **14 September 2026, 11:45pm SGT** — 18:45 in Bahrain |
| Feedback Period ends | 18 September 2026, 11:45pm SGT — *four days later* |
| Judging Period | 30 September – 13 October 2026 |

The judging window matters: **the repository must stay public and working until
13 October**, because judges test during that period, not at submission time.

## Eligibility

Bahrain is not on the exclusion list (Brazil, Quebec, Russia, Crimea, Cuba, Iran,
North Korea, and comprehensively OFAC-sanctioned countries), and is not
comprehensively sanctioned. Entering as an individual, which is the simplest
case — no Representative to appoint, prize payable directly.

## Project requirements

| Rule | Status |
|---|---|
| Uses CALL-E's API or SDK | **Yes** — `calle.py` calls `POST /v1/calls`, `GET /v1/calls/{id}`, `GET /v1/calls/{id}/events`, `GET /v1/goals` |
| Functional, installs and runs consistently | **Yes** — stdlib only, 144 tests, no credential needed to run the demo |
| Newly created during the Submission Period | **Yes** — first commit `01d5880`, 5 September 2026; the repository was empty before it |
| Third-party integrations properly licensed | **Yes** — no third-party code at all. Every import is standard library: `argparse dataclasses datetime enum hashlib http json os pathlib re sqlite3 sys threading time typing urllib uuid zoneinfo`. `tzdata` on Windows is data, not code |
| Original work, solely owned, MIT licensed | **Yes** |
| No financial or preferential support from the Sponsor | **Yes** — the only thing received is the standard free call allocation, which the rules explicitly provide for |

## Submission requirements

| Rule | Status |
|---|---|
| PR to `CALLE-AI/awesome-phone-call-agents` | **Done — and merged.** [#369](https://github.com/CALLE-AI/awesome-phone-call-agents/pull/369) |
| PR URL on the Devpost form | to enter |
| Text description of features and functionality | drafted in [`devpost-submission.md`](devpost-submission.md) |
| Demonstration video, under 3 minutes | **ACTION — not recorded** |
| Video public on YouTube or Vimeo | **ACTION** |
| CALL-E account email | **ACTION** — still `[TBD]` |
| Everything in English | Yes |

---

## ACTION 1 — the video should show a real CALL-E call

This is the one that changed when the live run succeeded, and it is the most
important item on this page.

Three separate rules point the same way:

> **Stage One)** ... pass/fail whether ... the Project **reasonably applies
> CALL-E APIs**, SDKs, MCP, or Skill integrations

> **Technical Implementation.** ... Does the code reflect genuine effort and a
> working, non-trivial implementation — **CALL-E imported and actually called at
> runtime, not just referenced?**

> **Functionality.** The Project ... must **function as depicted in the video**
> and/or expressed in the text description.

The original plan was a video of the scripted transport alone, because it is
deterministic and costs no credits to rehearse. That was the right call when a
live run was impossible. It is the wrong call now.

A judge watching only a mock run has to take the CALL-E integration on trust,
and the criterion asks them specifically not to. Meanwhile we have two real
calls, full transcripts, and a resolved outcome sitting in
[`live-call-evidence.md`](live-call-evidence.md).

**What to do:** keep the mock run as the spine of the video — it is the only way
to show the referral chain across three companies, which is the whole idea — and
add a short segment that shows the live call is real. Even fifteen seconds of the
terminal showing `call_fRjlbGjjzn8zQGPqomoRlQ` and a `RESOLVED` result, narrated
as *"and here it is on a real phone call"*, converts an assertion into a
demonstration.

Say plainly in the video which parts are which. Being straightforward about the
scripted transport is a strength; letting a judge assume the mock is live and
then discover otherwise is not.

## ACTION 2 — testing access is required, not optional

> Access must be provided to an Entrant's working Project for judging and
> testing by providing a link to a website, functioning demo, or a **test
> build**. The Entrant must make the Project available **free of charge and
> without any restriction**, for testing, evaluation and use ... **until the
> Judging Period ends**.

The Devpost form presents the demo URL as optional, and we are leaving it blank.
The public MIT-licensed repository plus the step-by-step testing instructions
satisfies "test build" — a judge can clone it and have the browser demo running
in about two minutes with no account, no key, and no payment.

**But the obligation runs to 13 October.** Do not archive, privatise or delete
the repository before then, and do not break `main`.

## ACTION 3 — the feedback survey cannot be resubmitted

> **One Feedback Submission per Entrant.**

The submitted feedback described the concurrency slot as never released. It does
release, after 2 h 36 m — [`calle-api-notes.md`](calle-api-notes.md) carries the
correction, and the repository history shows it.

Since a second submission is not permitted, the correction should go to the
CALL-E Discord `#support` channel instead, which the survey itself encouraged.
Correcting your own bug report unprompted is worth more than the original
overstatement cost.

---

## One piece of good news worth knowing

> Eligible individuals who **only** submit Most Valuable Feedback Surveys will
> NOT be eligible for any additional prizes.

The word doing the work is *only*. Submitting feedback **and** a project keeps
you eligible for both tracks — the feedback submission costs nothing in main-prize
eligibility. A single project can win one prize; the Feedback Prize is awarded to
the individual and counted separately.

## Video constraints to respect on the day

- **Under three minutes.** Judges are not required to watch past it.
- **No copyrighted music.** Silence or narration only, unless you own the rights.
- **No third-party trademarks** without permission — keep the telephony
  provider's dashboard and the softphone's branding out of frame if you record
  any live segment. CALL-E's own name is fine; it is the sponsor.
- Every phone number on screen must render masked, `+*******9558`.

## Publicity consent, so it is not a surprise

Entering consents to the Sponsor and Devpost using your name, likeness, voice,
comments and country of residence for promotion, worldwide, for three years.
If you narrate the video, that includes your voice.
