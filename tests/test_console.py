"""Rendering to a console that cannot take what we want to print.

A Windows console defaults to a legacy codepage, and printing a telephone glyph
to cp1252 raises rather than degrading — so the whole CLI dies on its first
call, having produced two lines of output. That is a worse failure than plain
text, and it only ever shows up on somebody else's machine.

These tests run everywhere. They do not need a legacy console; they stub the
encoding, which is the only part that differs.
"""

from __future__ import annotations

import io
import unittest
from pathlib import Path
from unittest import mock

from outcome import cli

SCENARIOS = Path(__file__).resolve().parent.parent / "scenarios"


class FakeStdout(io.StringIO):
    """A stdout whose encoding we control, and which refuses like a real one."""

    def __init__(self, encoding: str) -> None:
        super().__init__()
        self._encoding = encoding

    @property
    def encoding(self) -> str:
        return self._encoding


class ConsoleCapability(unittest.TestCase):
    def test_a_utf8_console_is_left_alone(self):
        with mock.patch.object(cli.sys, "stdout", FakeStdout("utf-8")):
            self.assertTrue(cli._console_takes_unicode())
            self.assertEqual(cli._colour(True, "✓ ☎"), "✓ ☎")

    def test_a_legacy_console_gets_ascii(self):
        with mock.patch.object(cli.sys, "stdout", FakeStdout("cp1252")):
            self.assertFalse(cli._console_takes_unicode())
            self.assertEqual(cli._colour(True, "▸ ☎ ✓ ✗ ○ ─"), "> * + x o -")

    def test_an_ascii_console_gets_ascii(self):
        with mock.patch.object(cli.sys, "stdout", FakeStdout("ascii")):
            self.assertEqual(cli._colour(True, "a — b … c"), "a - b . c")

    def test_an_unknown_encoding_name_does_not_raise(self):
        with mock.patch.object(cli.sys, "stdout", FakeStdout("not-a-codec")):
            self.assertFalse(cli._console_takes_unicode())
            self.assertEqual(cli._colour(True, "✓"), "+")

    def test_colour_stripping_still_happens_on_a_legacy_console(self):
        with mock.patch.object(cli.sys, "stdout", FakeStdout("cp1252")):
            rendered = cli._colour(False, f"{cli.GREEN}✓{cli.RESET} done")
            self.assertEqual(rendered, "+ done")


class EveryGlyphIsCovered(unittest.TestCase):
    """The map has to cover what the CLI can actually emit, not what it emitted
    when the map was written."""

    def _unencodable(self, text: str, encoding: str) -> set[str]:
        out = set()
        for char in set(text):
            try:
                char.encode(encoding)
            except (UnicodeEncodeError, LookupError):
                out.add(char)
        return out

    def test_no_source_glyph_escapes_the_fallback(self):
        source = (Path(cli.__file__)).read_text(encoding="utf-8")
        for encoding in ("cp1252", "ascii"):
            with self.subTest(encoding=encoding):
                uncovered = self._unencodable(source, encoding) - set(cli.ASCII_FALLBACK)
                self.assertEqual(uncovered, set())

    def test_the_fallback_values_are_themselves_ascii(self):
        for fancy, plain in cli.ASCII_FALLBACK.items():
            with self.subTest(glyph=fancy):
                plain.encode("ascii")

    def test_shipped_scenarios_survive_an_ascii_console(self):
        """Scenario text reaches the screen verbatim, so it is part of the
        surface an ASCII console has to cope with."""
        for path in sorted(SCENARIOS.glob("*.json")):
            with self.subTest(scenario=path.stem):
                text = path.read_text(encoding="utf-8")
                uncovered = self._unencodable(text, "ascii") - set(cli.ASCII_FALLBACK)
                self.assertEqual(uncovered, set(), f"{path.name} has glyphs with no fallback")


class RenderingARealRun(unittest.TestCase):
    def test_a_whole_run_prints_to_a_legacy_console_without_raising(self):
        """The regression this file exists for: the CLI used to die partway
        through its first call with a UnicodeEncodeError."""
        from outcome.calle import MockCalleClient
        from outcome.engine import Engine
        from outcome.loader import load_scenario

        for path in sorted(SCENARIOS.glob("*.json")):
            with self.subTest(scenario=path.stem):
                scenario, outcome = load_scenario(str(path))
                sink = FakeStdout("cp1252")
                with mock.patch.object(cli.sys, "stdout", sink):
                    printer = cli.Printer(colour=False)
                    engine = Engine(MockCalleClient(scenario), on_event=printer)
                    engine.run(outcome)
                    engine.approve(outcome, outcome.pending_approval_action_id)
                # Everything written must survive the round trip to the console.
                sink.getvalue().encode("cp1252")
                self.assertIn("RESOLVED", sink.getvalue())


if __name__ == "__main__":
    unittest.main()
