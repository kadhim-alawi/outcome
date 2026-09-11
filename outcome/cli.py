"""Watch an outcome run in a terminal.

    python -m outcome.cli run scenarios/supplier-replacement.json
    python -m outcome.cli run scenarios/supplier-replacement.json --approve auto
    python -m outcome.cli run scenarios/supplier-replacement.json --json

`--live` is the only mode that spends credits, and it refuses to start without
CALLE_API_KEY. Everything else replays the scenario.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from .calle import (
    EVIDENCE_SCHEMA,
    CalleClient,
    CalleError,
    DryRunCalleClient,
    MockCalleClient,
    parse_allowed_numbers,
    validate_result_schema,
)
from .engine import Engine
from .loader import load_scenario
from .models import ActionType, Outcome, OutcomeStatus, mask_phone
from .planner import FrontierPlanner

RESET, DIM, BOLD = "\033[0m", "\033[2m", "\033[1m"
GREEN, YELLOW, RED, BLUE, CYAN = (
    "\033[32m", "\033[33m", "\033[31m", "\033[34m", "\033[36m",
)

VERDICT_MARK = {
    "confirmed": f"{GREEN}✓{RESET}",
    "offer": f"{CYAN}○{RESET}",
    "partial": f"{DIM}·{RESET}",
    "blocked": f"{RED}✗{RESET}",
    "refused": f"{RED}✗{RESET}",
    "no_answer": f"{DIM}…{RESET}",
}


def _mark(result: dict[str, Any]) -> str:
    """A violated soft constraint is a note, not a failure.

    Rendering "no reference number was given" with the same red cross as "$112
    over your limit" teaches the user that the crosses do not mean anything,
    which is exactly the wrong lesson on an approval screen.
    """
    judgement = result["judgement"]
    if judgement == "satisfied":
        return f"{GREEN}✓{RESET}"
    if judgement == "violated":
        return f"{RED}✗{RESET}" if result.get("hard") else f"{YELLOW}~{RESET}"
    return f"{DIM}?{RESET}"


# A Windows console defaults to a legacy codepage, and printing "☎" to cp1252
# raises rather than degrading — so the whole CLI dies on its first call. Ask
# for UTF-8, and keep an ASCII set for the consoles that refuse.
ASCII_FALLBACK = {
    "▸": ">", "☎": "*", "✓": "+", "✗": "x", "○": "o",
    "·": ".", "…": ".", "─": "-", "×": "x", "—": "-",
}


def _enable_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            pass


def _console_takes_unicode() -> bool:
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        "".join(ASCII_FALLBACK).encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def _colour(enabled: bool, text: str) -> str:
    """The single choke point every line of CLI output passes through.

    Does two downgrades: strips ANSI when colour is off, and swaps the symbols
    for ASCII when the console cannot encode them. Both belong here rather than
    at each call site, because a renderer that is only mostly applied is a
    crash waiting for the one message nobody tested.
    """
    out = text
    if not enabled:
        for code in (RESET, DIM, BOLD, GREEN, YELLOW, RED, BLUE, CYAN):
            out = out.replace(code, "")
    if not _console_takes_unicode():
        for fancy, plain in ASCII_FALLBACK.items():
            out = out.replace(fancy, plain)
    return out


class Printer:
    def __init__(self, colour: bool = True) -> None:
        self.colour = colour

    def __call__(self, event: dict[str, Any]) -> None:
        kind = event["kind"]
        handler = getattr(self, f"_on_{kind}", None)
        if handler:
            print(_colour(self.colour, handler(event)))

    def _on_started(self, e):
        return f"\n{BOLD}OUTCOME{RESET}  {e['goal']}\n"

    def _on_planned(self, e):
        if e["type"] in ("complete", "abandon"):
            return f"{DIM}   … {e['purpose']}{RESET}"
        return f"{BLUE}▸{RESET} {e['purpose']}"

    def _on_calling(self, e):
        tag = f" {YELLOW}[commits you]{RESET}" if e.get("commits_user") else ""
        attempt = f" {DIM}(attempt {e['attempt']}){RESET}" if e["attempt"] > 1 else ""
        return f"  ☎  {BOLD}{e['org']}{RESET} {DIM}{e['phone']}{RESET}{attempt}{tag}"

    def _on_evidence(self, e):
        mark = VERDICT_MARK.get(e["verdict"], "·")
        lines = [f"  {mark} {e['verdict']}"]
        for fact in e.get("facts", []):
            lines.append(f"     {DIM}·{RESET} {fact}")
        for blocker in e.get("blockers", []):
            lines.append(f"     {RED}!{RESET} {blocker}")
        if e.get("offer"):
            offer = e["offer"]
            price = f"{offer['currency']} {offer['price']:.2f}" if offer["price"] is not None else "no price"
            verdict = (
                f"{GREEN}meets your requirements{RESET}"
                if e.get("acceptable")
                else f"{RED}rejected{RESET}"
            )
            lines.append(f"     {CYAN}offer{RESET} {offer['summary']} — {price} — {verdict}")
            for result in e.get("constraint_report", []):
                if result["judgement"] == "violated":
                    lines.append(f"       {_mark(result)} {result['detail']}")
        return "\n".join(lines)

    def _on_lead_discovered(self, e):
        return f"     {YELLOW}+{RESET} new lead: {BOLD}{e['org']}{RESET} {DIM}{e['phone']} — {e['reason']}{RESET}"

    def _on_approval_required(self, e):
        lines = ["", f"{YELLOW}{BOLD}  APPROVAL NEEDED{RESET}", f"  {e['prompt']}"]
        if e.get("evaluation"):
            for result in e["evaluation"]["results"]:
                lines.append(f"    {_mark(result)} {result['detail']}")
        for rejected in e.get("rejected", []):
            offer = rejected["offer"]
            lines.append(f"    {DIM}turned down: {offer['summary']} — {offer['currency']} {offer['price']}{RESET}")
        return "\n".join(lines)

    def _on_approved(self, e):
        return f"  {GREEN}✓ approved{RESET}"

    def _on_rejected(self, e):
        return f"  {RED}✗ declined:{RESET} {e['reason']}"

    def _on_resolved(self, e):
        lines = ["", f"{GREEN}{BOLD}  RESOLVED{RESET}", f"  {e['headline']}"]
        if e.get("reference"):
            lines.append(f"  Reference: {BOLD}{e['reference']}{RESET}")
        lines.append(
            f"  {DIM}{e['calls_placed']} of {e['call_budget']} calls used across "
            f"{len(e['parties'])} organisations.{RESET}"
        )
        return "\n".join(lines)

    def _on_abandoned(self, e):
        lines = ["", f"{RED}{BOLD}  NOT RESOLVED{RESET}", f"  {e['why']}"]
        for blocker in e.get("blockers", []):
            lines.append(f"    {RED}!{RESET} {blocker}")
        lines.append(f"  {DIM}{e['calls_placed']} of {e['call_budget']} calls used.{RESET}")
        return "\n".join(lines)

    def _on_awaiting_user(self, e):
        return f"  {YELLOW}? waiting on you:{RESET} {e['purpose']}"

    def _on_awaiting_window(self, e):
        return (
            f"\n{YELLOW}  PAUSED{RESET}\n  {e['detail']}\n"
            f"  {DIM}The run is not lost. Start it again once the window is open and it "
            f"resumes at this call.{RESET}"
        )

    def _on_error(self, e):
        return f"\n{RED}{BOLD}  FAILED{RESET}\n  {e['detail']}"

    def _on_unresolved_call(self, e):
        call_id = f"\n  {DIM}CALL-E call id: {e['call_id']}{RESET}" if e.get("call_id") else ""
        return (
            f"\n{RED}{BOLD}  UNRESOLVED CALL{RESET}\n  {e['detail']}{call_id}"
        )

    def _on_replayed(self, e):
        return f"  {DIM}(already placed — replaying the stored result){RESET}"


def _live_client(allow_any_number: bool = False) -> CalleClient:
    key = os.environ.get("CALLE_API_KEY", "")
    if not key:
        raise SystemExit(
            "CALLE_API_KEY is not set. Refusing to start a run that would place real "
            "calls without a credential."
        )
    try:
        allowed = parse_allowed_numbers(os.environ.get("CALLE_ALLOWED_NUMBERS"))
    except CalleError as exc:
        raise SystemExit(str(exc)) from None
    if not allowed and not allow_any_number:
        raise SystemExit(
            "CALLE_ALLOWED_NUMBERS is not set.\n\n"
            "A live run dials whoever the agent decides to dial, including numbers it "
            "was given on a call. Set the allowlist to the numbers you are willing to "
            "have rung:\n\n"
            '    export CALLE_ALLOWED_NUMBERS="+15550100001,+15550100002"\n\n'
            "For a first live run, put only your own number in it. Pass "
            "--allow-any-number to run without an allowlist."
        )
    return CalleClient(
        api_key=key,
        base_url=os.environ.get("CALLE_BASE_URL", "https://api.heycall-e.com"),
        allowed_numbers=allowed,
    )


def _check_live_preconditions(outcome: Outcome, client: CalleClient) -> list[str]:
    """Everything that should stop a live run before the first dial, not during it."""
    problems: list[str] = []
    if outcome.call_window is None:
        problems.append(
            "This outcome has no calling window. A live run needs one, or the agent "
            'will dial at 03:00. Add "call_window": {"timezone": "Europe/London", '
            '"start": "09:00", "end": "17:30", "weekdays": [0,1,2,3,4]} to the scenario.'
        )
    for org in outcome.organizations:
        try:
            client.assert_dialable(org.phone)
        except CalleError as exc:
            problems.append(f"{org.name}: {exc}")
    return problems


def _transport(args, scenario):
    if args.live:
        return _live_client(getattr(args, "allow_any_number", False))
    if args.dry_run:
        return DryRunCalleClient()
    return MockCalleClient(scenario)


def _prompt_approval(outcome: Outcome, mode: str) -> bool:
    if mode == "auto":
        return True
    if mode == "never":
        return False
    try:
        answer = input("  Approve? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


def cmd_preflight(args: argparse.Namespace) -> int:
    """Everything checkable about a live run, without placing one.

    A first live run against real numbers should never be the moment you find
    out the key is wrong, the window is shut, or the script says something you
    would not say. All of that is knowable for free.
    """
    colour = sys.stdout.isatty() and not args.no_colour
    out = lambda text: print(_colour(colour, text))  # noqa: E731
    scenario, outcome = load_scenario(args.scenario)
    problems: list[str] = []
    warnings: list[str] = []

    out(f"\n{BOLD}OUTCOME preflight{RESET}  {DIM}nothing will be dialled{RESET}\n")
    out(f"  {BOLD}Goal{RESET}          {outcome.goal}")

    try:
        client = _live_client(args.allow_any_number)
    except SystemExit as exc:
        out(f"  {RED}Credential    {exc}{RESET}")
        return 1

    out(f"  {BOLD}Endpoint{RESET}      {client.base_url}")
    try:
        client.ping()
        out(f"  {BOLD}Credential{RESET}    {GREEN}accepted{RESET} "
            f"{DIM}(read-only GET /v1/goals; no call placed){RESET}")
    except CalleError as exc:
        out(f"  {BOLD}Credential{RESET}    {RED}rejected{RESET} — {exc}")
        problems.append("The API key was not accepted.")

    if client.allowed_numbers:
        listed = ", ".join(sorted(mask_phone(n) for n in client.allowed_numbers))
        out(f"  {BOLD}Allowlist{RESET}     {len(client.allowed_numbers)} number(s): {listed}")
    else:
        out(f"  {BOLD}Allowlist{RESET}     {YELLOW}none — any number may be dialled{RESET}")
        warnings.append(
            "No allowlist: the agent may dial any number it is given on a call."
        )

    # Checked here because CALL-E rejects a bad schema with a 400 at dial time,
    # which is a fine place to find out and a bad place to find out first.
    schema_problems = validate_result_schema(EVIDENCE_SCHEMA)
    if schema_problems:
        out(f"  {BOLD}Result schema{RESET} {RED}unsupported by CALL-E{RESET}")
        for problem in schema_problems:
            out(f"    {RED}✗{RESET} {problem}")
        problems.extend(schema_problems)
    else:
        out(f"  {BOLD}Result schema{RESET} {GREEN}within the documented subset{RESET}")

    window = outcome.call_window
    if window is None:
        out(f"  {BOLD}Window{RESET}        {RED}not set{RESET}")
    elif window.is_open():
        out(f"  {BOLD}Window{RESET}        {GREEN}open now{RESET} {DIM}({window.describe()}){RESET}")
    else:
        out(f"  {BOLD}Window{RESET}        {YELLOW}closed{RESET} — {window.explain_closed()}")
        warnings.append(
            f"The window is closed, so a run started now will park immediately and "
            f"place no calls until {window.next_open().strftime('%a %d %b %H:%M %Z')}."
        )

    out(f"  {BOLD}Budget{RESET}        {outcome.budget.max_calls} calls total, "
        f"{outcome.budget.max_calls_per_org} per organisation")

    out(f"\n  {BOLD}Requirements{RESET}")
    for c in outcome.constraints:
        marker = "must  " if c.hard else "prefer"
        out(f"    {DIM}{marker}{RESET} {c.description} {DIM}({c.kind.value}={c.value}){RESET}")

    out(f"\n  {BOLD}Phone book{RESET}")
    for org in outcome.organizations:
        try:
            client.assert_dialable(org.phone)
            mark, note = f"{GREEN}✓{RESET}", ""
        except CalleError as exc:
            mark, note = f"{RED}✗{RESET}", f"  {RED}{exc}{RESET}"
            problems.append(f"{org.name}: {exc}")
        out(f"    {mark} {org.name} {DIM}{mask_phone(org.phone)}{RESET}{note}")

    problems.extend(
        p for p in _check_live_preconditions(outcome, client) if p not in problems
    )

    action = FrontierPlanner().next_action(outcome)
    if action.type is ActionType.CALL:
        out(f"\n  {BOLD}First call{RESET}  {DIM}the exact words the caller is given{RESET}")
        out(f"  {DIM}{'─' * 66}{RESET}")
        for line in action.task_prompt.splitlines():
            out(f"  {line}")
        out(f"  {DIM}{'─' * 66}{RESET}")

    if problems:
        out(f"\n{RED}{BOLD}  NOT READY{RESET}")
        for problem in problems:
            out(f"    {RED}✗{RESET} {problem}")
        out("")
        return 1
    if warnings:
        out(f"\n{YELLOW}{BOLD}  READY, WITH CAVEATS{RESET}")
        for warning in warnings:
            out(f"    {YELLOW}~{RESET} {warning}")
        out(f"  {DIM}Nothing here blocks a live run. Read them anyway.{RESET}\n")
        return 0
    out(f"\n{GREEN}{BOLD}  READY{RESET}  {DIM}run again with --live to place calls.{RESET}\n")
    return 0


def cmd_calls(args: argparse.Namespace) -> int:
    """The operator surface for the call ledger.

    Only ever needed after a crash. An unfinished entry means a call was started
    and never recorded a result, so the engine refuses to dial that number again
    until somebody says which of the two things happened.
    """
    from .store import Store

    colour = sys.stdout.isatty() and not args.no_colour
    out = lambda text: print(_colour(colour, text))  # noqa: E731
    store = Store(args.store)

    if args.resolve:
        if store.resolve_call(args.resolve):
            out(f"{GREEN}Recorded as placed.{RESET} That number will not be dialled again "
                "for this action, and the run can continue.")
            return 0
        out(f"{RED}No unfinished call with that key.{RESET}")
        return 1

    if args.forget:
        if store.forget_call(args.forget):
            out(f"{YELLOW}Claim removed.{RESET} That number can now be dialled again. "
                "Only correct if you established the call never happened.")
            return 0
        out(f"{RED}No unfinished call with that key.{RESET}")
        return 1

    unfinished = store.unfinished_calls()
    if not unfinished:
        out(f"{GREEN}No unfinished calls.{RESET} Nothing was left mid-flight.")
        return 0

    out(f"\n{YELLOW}{BOLD}  {len(unfinished)} unfinished call(s){RESET}")
    out(f"  {DIM}Each was started and never recorded a result, so it may have "
        f"connected.{RESET}\n")
    for entry in unfinished:
        out(f"  {BOLD}{mask_phone(entry.phone)}{RESET}  {DIM}claimed {entry.claimed_at}{RESET}")
        out(f"    outcome {entry.outcome_id}  action {entry.action_id}")
        out(f"    {DIM}it happened   :{RESET} outcome calls --store {args.store} "
            f"--resolve {entry.idempotency_key}")
        out(f"    {DIM}it did not    :{RESET} outcome calls --store {args.store} "
            f"--forget {entry.idempotency_key}\n")
    return 1


def cmd_run(args: argparse.Namespace) -> int:
    scenario, outcome = load_scenario(args.scenario)
    events: list[dict[str, Any]] = []

    def sink(event: dict[str, Any]) -> None:
        events.append(event)
        if not args.json:
            printer(event)

    printer = Printer(colour=sys.stdout.isatty() and not args.no_colour)
    transport = _transport(args, scenario)
    if args.live:
        problems = _check_live_preconditions(outcome, transport)
        if not args.store:
            # Without a ledger a live run can place a call and then lose its id,
            # and CALL-E has no endpoint that lists calls — so there is no way to
            # ask what you just dialled. We learned this the expensive way: a
            # real conversation whose transcript and result we could not read
            # back afterwards. The whole point of the write-ahead ledger is that
            # a call is never unrecorded, which makes it a poor thing to opt in
            # to.
            problems.append(
                "A live run needs --store, or a call can be placed and its id lost. "
                "CALL-E has no endpoint that lists calls, so an unrecorded call "
                "cannot be looked up afterwards. Try --store runs.sqlite3"
            )
        if problems:
            raise SystemExit(
                "Refusing to start a live run:\n\n  - " + "\n  - ".join(problems)
            )
    store = None
    if args.store:
        from .store import Store

        store = Store(args.store)
    engine = Engine(transport, on_event=sink, store=store)
    engine.run(outcome)

    while outcome.status is OutcomeStatus.AWAITING_APPROVAL:
        action_id = outcome.pending_approval_action_id
        if _prompt_approval(outcome, args.approve):
            engine.approve(outcome, action_id)
        else:
            engine.reject(outcome, action_id, "Declined at the approval step.")

    if args.json:
        print(json.dumps({"outcome": outcome.to_dict(), "events": events}, indent=2))
    elif args.live or args.dry_run:
        print()

    return 0 if outcome.status is OutcomeStatus.RESOLVED else 1


def main(argv: list[str] | None = None) -> int:
    _enable_utf8()
    parser = argparse.ArgumentParser(prog="outcome", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run an outcome from a scenario file.")
    run.add_argument("scenario")
    run.add_argument(
        "--approve",
        choices=["ask", "auto", "never"],
        default="ask",
        help="How to answer approval requests. Default: ask.",
    )
    run.add_argument("--json", action="store_true", help="Emit the full run as JSON.")
    run.add_argument("--no-colour", action="store_true")
    mode = run.add_mutually_exclusive_group()
    mode.add_argument(
        "--live", action="store_true", help="Place real calls. Requires CALLE_API_KEY."
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the CALL-E request for the first call and stop.",
    )
    run.add_argument(
        "--allow-any-number",
        action="store_true",
        help="Run live without CALLE_ALLOWED_NUMBERS. Think before using this.",
    )
    run.add_argument(
        "--store",
        metavar="PATH",
        help="Persist the run to a SQLite file, and record every call in a ledger so "
        "a restart cannot dial the same number twice. Recommended for --live.",
    )
    run.set_defaults(func=cmd_run)

    calls = sub.add_parser(
        "calls", help="Inspect the call ledger and clear calls left unfinished by a crash."
    )
    calls.add_argument("--store", required=True, metavar="PATH")
    calls.add_argument("--resolve", metavar="KEY", help="The call did happen.")
    calls.add_argument("--forget", metavar="KEY", help="The call never happened.")
    calls.add_argument("--no-colour", action="store_true")
    calls.set_defaults(func=cmd_calls)

    pre = sub.add_parser(
        "preflight",
        help="Check a live run without placing one: credential, allowlist, window, "
        "numbers, budget, and the exact first call script.",
    )
    pre.add_argument("scenario")
    pre.add_argument("--no-colour", action="store_true")
    pre.add_argument(
        "--allow-any-number",
        action="store_true",
        help="Check without requiring CALLE_ALLOWED_NUMBERS.",
    )
    pre.set_defaults(func=cmd_preflight)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
