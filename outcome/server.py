"""A small HTTP server so the run can be watched in a browser.

    python -m outcome.server            # http://127.0.0.1:8765

Standard library only, and mock-backed by default: this is the demo surface,
not a deployment target. The engine runs to completion (or to the approval
gate) inside one request, and the page animates the event list it gets back.
Streaming the run over a socket would look identical on screen and would mean
holding a connection open for the length of a real phone call.

`--live` places real calls and needs CALLE_API_KEY. It is off by default and
the banner in the UI says which mode is running, because the difference between
these two modes is somebody's phone actually ringing.
"""

from __future__ import annotations

import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .calle import CalleClient, MockCalleClient
from .engine import Engine
from .loader import load_scenario, outcome_from_request
from .models import Outcome, OutcomeStatus

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
SCENARIO_ROOT = Path(__file__).resolve().parent.parent / "scenarios"

FAVICON = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    b'<rect width="32" height="32" rx="7" fill="#1f6f5c"/>'
    b'<circle cx="16" cy="16" r="7" fill="none" stroke="#fff" stroke-width="3"/></svg>'
)

_lock = threading.Lock()
_runs: dict[str, dict[str, Any]] = {}


class Runner:
    """Holds the engine and the event log for one outcome."""

    def __init__(self, outcome: Outcome, transport, live: bool) -> None:
        self.outcome = outcome
        self.events: list[dict[str, Any]] = []
        self.live = live
        self.engine = Engine(transport, on_event=self.events.append)

    def snapshot(self, since: int = 0) -> dict[str, Any]:
        return {
            "outcome": self.outcome.to_dict(),
            "events": self.events[since:],
            "event_count": len(self.events),
            "live": self.live,
        }


def _scenario_path(name: str) -> Path:
    """Resolve a scenario name to a file inside `scenarios/` only.

    The name arrives from an HTTP request, so it is resolved and then checked
    to still be under the scenario directory. Without that check, a name like
    `../../etc/passwd` reads whatever the process can read.
    """
    candidate = (SCENARIO_ROOT / f"{name}.json").resolve()
    if not str(candidate).startswith(str(SCENARIO_ROOT.resolve()) + os.sep):
        raise ValueError("Unknown scenario.")
    if not candidate.is_file():
        raise ValueError("Unknown scenario.")
    return candidate


def _make_runner(body: dict[str, Any], live: bool) -> Runner:
    name = str(body.get("scenario") or "supplier-replacement")
    scenario, outcome = load_scenario(str(_scenario_path(name)))

    text = str(body.get("text") or "").strip()
    if text:
        # The typed request wins over the scenario's canned goal, but the
        # scenario still supplies the phone book — a mock run can only replay
        # numbers it has scripted answers for.
        typed = outcome_from_request(
            text,
            organizations=[o.to_dict() for o in outcome.organizations],
            budget=outcome.budget.to_dict(),
        )
        if typed.constraints:
            outcome.goal = typed.goal
            outcome.constraints = typed.constraints

    if live:
        transport = CalleClient(
            api_key=os.environ["CALLE_API_KEY"],
            base_url=os.environ.get("CALLE_BASE_URL", "https://api.heycall-e.com"),
        )
    else:
        transport = MockCalleClient(scenario)
    return Runner(outcome, transport, live)


class Handler(BaseHTTPRequestHandler):
    live = False
    server_version = "outcome/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter console
        return

    # -- plumbing --------------------------------------------------------

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json; charset=utf-8")

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode())
        except (ValueError, UnicodeDecodeError):
            return {}

    # -- routes ----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            page = WEB_ROOT / "index.html"
            if not page.is_file():
                return self._json(500, {"error": "web/index.html is missing."})
            return self._send(200, page.read_bytes(), "text/html; charset=utf-8")
        if self.path == "/favicon.ico":
            return self._send(200, FAVICON, "image/svg+xml")
        if self.path == "/api/mode":
            return self._json(200, {"live": self.live})
        if self.path == "/api/scenarios":
            return self._json(200, {"scenarios": self._scenarios()})
        if self.path.startswith("/api/runs/"):
            run_id = self.path.rsplit("/", 1)[-1].split("?")[0]
            with _lock:
                runner = _runs.get(run_id)
            if runner is None:
                return self._json(404, {"error": "No such run."})
            return self._json(200, runner.snapshot())
        return self._json(404, {"error": "Not found."})

    def do_POST(self) -> None:  # noqa: N802
        body = self._read_json()
        if self.path == "/api/runs":
            return self._start(body)
        if self.path == "/api/decide":
            return self._decide(body)
        return self._json(404, {"error": "Not found."})

    # -- handlers --------------------------------------------------------

    def _scenarios(self) -> list[dict[str, Any]]:
        out = []
        for path in sorted(SCENARIO_ROOT.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            out.append(
                {
                    "name": path.stem,
                    "title": data.get("title", path.stem),
                    "description": data.get("description", ""),
                    "goal": (data.get("outcome") or {}).get("goal", ""),
                }
            )
        return out

    def _start(self, body: dict[str, Any]) -> None:
        try:
            runner = _make_runner(body, self.live)
        except ValueError as exc:
            return self._json(400, {"error": str(exc)})
        except KeyError:
            return self._json(400, {"error": "Live mode needs CALLE_API_KEY."})
        runner.engine.run(runner.outcome)
        with _lock:
            _runs[runner.outcome.id] = runner
        self._json(200, runner.snapshot())

    def _decide(self, body: dict[str, Any]) -> None:
        run_id = str(body.get("run_id") or "")
        with _lock:
            runner = _runs.get(run_id)
        if runner is None:
            return self._json(404, {"error": "No such run."})
        outcome = runner.outcome
        if outcome.status is not OutcomeStatus.AWAITING_APPROVAL:
            return self._json(409, {"error": "This run is not waiting for a decision."})

        since = len(runner.events)
        action_id = outcome.pending_approval_action_id or ""
        if bool(body.get("approve")):
            runner.engine.approve(outcome, action_id)
        else:
            runner.engine.reject(
                outcome, action_id, str(body.get("reason") or "Declined by the user.")
            )
        self._json(200, runner.snapshot(since=since))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="outcome.server", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Place real calls through CALL-E. Requires CALLE_API_KEY.",
    )
    args = parser.parse_args(argv)

    if args.live and not os.environ.get("CALLE_API_KEY"):
        raise SystemExit("--live needs CALLE_API_KEY in the environment.")

    Handler.live = args.live
    mode = "LIVE — real calls will be placed" if args.live else "mock — no calls are placed"
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"OUTCOME on http://{args.host}:{args.port}  ({mode})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
