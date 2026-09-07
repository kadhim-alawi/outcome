#!/usr/bin/env python3
"""Write the one-call scenario for a first live run, using your own number.

    python3 scripts/make_live_smoke_test.py --timezone Europe/London

Reads the number from CALLE_ALLOWED_NUMBERS (the first entry) so the same
value that authorises the dial is the one that gets dialled, and writes
`scenarios/local/live-smoke-test.json`, which is gitignored. This repository is
public and every number committed to it is fictional; a live run needs a real
one, and it must not end up in a commit.

What the scenario is for
------------------------

One call, one credit, ending at the approval gate. That exercises the entire
read path — auth, POST /v1/calls, polling, structured_result, evidence
extraction, constraint evaluation, the approval gate — and stops before the
call that would commit you to anything. It is the cheapest way to find out
whether the pipeline works end to end on a real phone line.

You play the depot. When it rings, answer as though you can help, quote a
price and a date, and give a reference number. Then look at what came back.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "scenarios" / "local" / "live-smoke-test.json"

sys.path.insert(0, str(ROOT))

from outcome.calle import CalleError, parse_allowed_numbers  # noqa: E402
from outcome.models import mask_phone  # noqa: E402
from outcome.window import CallWindow, WindowError  # noqa: E402


def build(phone: str, timezone: str, today: date, locale: str | None, region: str | None) -> dict:
    deadline = today + timedelta(days=7)
    return {
        "name": "live-smoke-test",
        "title": "Live smoke test — one call, one credit",
        "description": (
            "A single live call to a number you own, to prove the CALL-E pipeline works "
            "end to end. It stops at the approval gate, so it costs one credit and "
            "commits you to nothing. Answer as the depot: say you can do it, quote a "
            "price under the limit, give a date before the deadline, and offer a "
            "reference number."
        ),
        "outcome": {
            "goal": (
                "Find out whether the depot can supply 50 insulated shipping boxes and "
                "deliver them this week."
            ),
            "budget": {"max_calls": 1, "max_calls_per_org": 1, "max_actions": 6},
            # Deliberately wide. The window is not what this test is checking, and a
            # shut one would park the run instead of dialling. The narrow windows in
            # the shipped scenarios are the real pattern.
            "call_window": {
                "timezone": timezone,
                "start": "00:00",
                "end": "23:59",
                "weekdays": [0, 1, 2, 3, 4, 5, 6],
            },
            "constraints": [
                {
                    "kind": "budget",
                    "description": "Total cost at or under USD 500",
                    "value": 500,
                    "hard": True,
                },
                {
                    "kind": "deadline",
                    "description": f"Delivered on or before {deadline.isoformat()}",
                    "value": deadline.isoformat(),
                    "hard": True,
                },
                {
                    "kind": "required_fact",
                    "description": "A reference number",
                    "value": "reference",
                    "hard": False,
                },
            ],
            "organizations": [
                {
                    "name": "Test depot (you)",
                    "phone": phone,
                    "role": "The number you authorised for this test",
                    # CALL-E refuses region/language pairs it does not serve, so
                    # these are worth stating rather than leaving it to infer.
                    **({"locale": locale} if locale else {}),
                    **({"region": region} if region else {}),
                }
            ],
        },
        "responses": [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timezone",
        default="UTC",
        help="IANA name for the calling window, e.g. Europe/London. Default: UTC.",
    )
    parser.add_argument(
        "--phone",
        help="Override the number. Normally taken from CALLE_ALLOWED_NUMBERS.",
    )
    parser.add_argument(
        "--locale",
        help="BCP 47 conversation locale, e.g. en-US or ar-BH. CALL-E refuses "
        "region/language pairs it does not serve, so state it rather than let it infer.",
    )
    parser.add_argument("--region", help="Recipient country code, e.g. US, GB, BH.")
    args = parser.parse_args(argv)

    phone = args.phone
    if not phone:
        try:
            allowed = parse_allowed_numbers(os.environ.get("CALLE_ALLOWED_NUMBERS"))
        except CalleError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if not allowed:
            print(
                "ERROR: CALLE_ALLOWED_NUMBERS is not set, so there is no number to "
                "call.\n\n"
                '    export CALLE_ALLOWED_NUMBERS="+447700900123"\n\n'
                "Use a number you own. This is the allowlist the dialler enforces, and "
                "taking the smoke-test number from it means the number authorised and "
                "the number dialled cannot drift apart.",
                file=sys.stderr,
            )
            return 1
        if len(allowed) > 1:
            print(
                f"ERROR: CALLE_ALLOWED_NUMBERS has {len(allowed)} numbers in it. For a "
                "first live run, allow exactly one — your own — or pass --phone to "
                "choose.",
                file=sys.stderr,
            )
            return 1
        phone = next(iter(allowed))

    try:
        CallWindow(timezone=args.timezone)
    except WindowError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            build(phone, args.timezone, date.today(), args.locale, args.region), indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUT.relative_to(ROOT)}")
    print(f"  number   {mask_phone(phone)}")
    print(f"  window   {args.timezone}, always open (this is a test, not the pattern)")
    print(f"  locale   {args.locale or '(unset — CALL-E infers)'}" f"   region {args.region or '(unset)'}")
    print("  budget   1 call\n")
    print("Next, and it costs nothing:")
    print("  python3 -m outcome.cli preflight scenarios/local/live-smoke-test.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
