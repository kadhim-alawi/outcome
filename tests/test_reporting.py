"""Nothing the engine says may be swallowed on the way to the user.

This file exists because of a live run that produced two lines of output and
then exited 1. The engine had done the right thing — caught the failure, parked
the run, written an explanatory event — and the CLI printer had no handler for
that event kind, so `getattr(self, "_on_" + kind, None)` returned None and the
message was dropped on the floor. The only way to find out what had gone wrong
was to open the SQLite ledger by hand.

A silent failure is worse than a crash. Testing each handler individually would
not have caught it, because the bug was an absence; the test has to be against
the set of kinds the engine can actually emit.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from outcome import cli, engine

ENGINE_SOURCE = Path(engine.__file__)


def emitted_kinds() -> set[str]:
    """Every literal kind passed to `self._emit(...)` in the engine.

    Read out of the AST rather than maintained by hand, so a new event added
    next month is covered by this test the moment it is written.
    """
    tree = ast.parse(ENGINE_SOURCE.read_text(encoding="utf-8"))
    kinds: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "_emit"):
            continue
        # _emit(outcome, "kind", {...}) — the kind is the second argument.
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            value = node.args[1].value
            if isinstance(value, str):
                kinds.add(value)
    return kinds


class EveryEventReachesTheUser(unittest.TestCase):
    def test_the_engine_emits_the_kinds_we_think_it_does(self):
        kinds = emitted_kinds()
        self.assertGreaterEqual(len(kinds), 10, "AST scan found suspiciously few events")
        for expected in ("started", "calling", "evidence", "resolved", "abandoned"):
            self.assertIn(expected, kinds)

    def test_the_cli_printer_handles_every_one(self):
        printer = cli.Printer(colour=False)
        missing = sorted(k for k in emitted_kinds() if not hasattr(printer, f"_on_{k}"))
        self.assertEqual(
            missing,
            [],
            "The CLI drops these events silently; a user would see nothing at all: "
            f"{missing}",
        )

    def test_the_browser_renders_every_one(self):
        """The page has the same failure mode: an unhandled kind falls through
        the switch and the row never appears."""
        page = (Path(cli.__file__).parent.parent / "web" / "index.html").read_text(
            encoding="utf-8"
        )
        # These are terminal or structural and are handled outside renderEvent.
        handled_elsewhere = {"started", "approval_required", "resolved", "abandoned"}
        missing = sorted(
            kind
            for kind in emitted_kinds() - handled_elsewhere
            if f'case "{kind}"' not in page
        )
        self.assertEqual(missing, [], f"web/index.html has no case for: {missing}")


class FailuresArePrintable(unittest.TestCase):
    """The handlers have to survive the payloads the engine actually sends,
    including the optional fields it sometimes omits."""

    def setUp(self):
        self.printer = cli.Printer(colour=False)

    def test_an_error_without_a_phone_renders(self):
        rendered = self.printer._on_error({"action_id": "a", "detail": "CALL-E refused."})
        self.assertIn("CALL-E refused.", rendered)

    def test_an_unresolved_call_renders_with_and_without_a_call_id(self):
        base = {"action_id": "a", "phone": "+*******0001", "detail": "unknown outcome"}
        self.assertIn("unknown outcome", self.printer._on_unresolved_call(base))
        with_id = self.printer._on_unresolved_call({**base, "call_id": "cal_123"})
        self.assertIn("cal_123", with_id)

    def test_the_failure_handlers_shout_rather_than_whisper(self):
        """A failed run must not look like a quiet aside. These are the two
        messages that mean 'a human has to do something'."""
        for rendered in (
            self.printer._on_error({"detail": "x"}),
            self.printer._on_unresolved_call({"phone": "p", "detail": "x"}),
        ):
            self.assertRegex(rendered, r"FAILED|UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
