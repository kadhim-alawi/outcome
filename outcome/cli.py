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

from .calle import CalleClient, DryRunCalleClient, MockCalleClient
from .engine import Engine
from .loader import load_scenario
from .models import Outcome, OutcomeStatus

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


def _colour(enabled: bool, text: str) -> str:
    if enabled:
        return text
    out = text
    for code in (RESET, DIM, BOLD, GREEN, YELLOW, RED, BLUE, CYAN):
        out = out.replace(code, "")
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

    def _on_error(self, e):
        return f"  {RED}error:{RESET} {e['detail']}"


def _transport(args, scenario):
    if args.live:
        key = os.environ.get("CALLE_API_KEY", "")
        if not key:
            raise SystemExit(
                "--live needs CALLE_API_KEY in the environment. Refusing to start a run "
                "that would place real calls without a credential."
            )
        base = os.environ.get("CALLE_BASE_URL", "https://api.heycall-e.com")
        return CalleClient(api_key=key, base_url=base)
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


def cmd_run(args: argparse.Namespace) -> int:
    scenario, outcome = load_scenario(args.scenario)
    events: list[dict[str, Any]] = []

    def sink(event: dict[str, Any]) -> None:
        events.append(event)
        if not args.json:
            printer(event)

    printer = Printer(colour=sys.stdout.isatty() and not args.no_colour)
    engine = Engine(_transport(args, scenario), on_event=sink)
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
    run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
