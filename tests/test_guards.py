"""Guards that stand between the planner and somebody's ringing phone.

Two of them, and they live in different places on purpose. The calling window
is a scheduling decision and sits in the engine; the number allowlist is the
last line before the network and sits in the transport, where no planning bug,
bad referral or hand-edited phone book can get past it.
"""

from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from outcome.calle import CalleClient, CalleError, MockCalleClient, parse_allowed_numbers
from outcome.engine import Engine
from outcome.loader import DefinitionError, load_scenario, outcome_from_definition
from outcome.models import ActionStatus, OutcomeStatus
from outcome.window import CallWindow, WindowError

SCENARIO = str(Path(__file__).resolve().parent.parent / "scenarios" / "supplier-replacement.json")
LONDON = ZoneInfo("Europe/London")

ALWAYS = CallWindow(timezone="UTC", start="00:00", end="23:59", weekdays=[0, 1, 2, 3, 4, 5, 6])
NEVER = CallWindow(timezone="UTC", start="09:00", end="09:01", weekdays=[6])


class DiallingMock(MockCalleClient):
    """A mock that claims to ring phones, so the real-world guards engage.

    The plain `MockCalleClient` deliberately does not: enforcing a Mon-Fri
    window on a replay would make the demo unrunnable at weekends and the test
    suite dependent on the day it runs, while protecting nobody.
    """

    places_real_calls = True


def build(transport_cls=DiallingMock, window=ALWAYS):
    scenario, outcome = load_scenario(SCENARIO)
    outcome.call_window = window
    events: list[dict] = []
    return Engine(transport_cls(scenario), on_event=events.append), outcome, events


class Window(unittest.TestCase):
    def test_open_only_inside_the_hours_and_days(self):
        window = CallWindow(timezone="Europe/London", start="09:00", end="17:30")
        self.assertTrue(window.is_open(datetime(2026, 9, 7, 10, 0, tzinfo=LONDON)))
        self.assertFalse(window.is_open(datetime(2026, 9, 7, 3, 0, tzinfo=LONDON)))
        self.assertFalse(window.is_open(datetime(2026, 9, 7, 17, 30, tzinfo=LONDON)))
        self.assertFalse(window.is_open(datetime(2026, 9, 5, 10, 0, tzinfo=LONDON)))

    def test_it_is_the_recipients_clock_that_counts(self):
        singapore = CallWindow(timezone="Asia/Singapore", start="09:00", end="17:30")
        # 02:00 UTC on a Monday is 10:00 in Singapore: fine there, the middle of
        # the night for whoever is running the agent.
        moment = datetime(2026, 9, 7, 2, 0, tzinfo=ZoneInfo("UTC"))
        self.assertTrue(singapore.is_open(moment))

    def test_next_open_lands_on_the_next_working_morning(self):
        window = CallWindow(timezone="Europe/London", start="09:00", end="17:30")
        saturday = datetime(2026, 9, 5, 10, 0, tzinfo=LONDON)
        opens = window.next_open(saturday)
        self.assertEqual((opens.weekday(), opens.hour, opens.minute), (0, 9, 0))
        self.assertEqual(opens.date().isoformat(), "2026-09-07")

    def test_next_open_survives_a_dst_change(self):
        # The UK leaves BST on 25 October 2026. Walking day by day keeps 09:00
        # local; arithmetic on a fixed offset would land an hour out.
        window = CallWindow(timezone="Europe/London", start="09:00", end="17:30")
        before = datetime(2026, 10, 23, 18, 0, tzinfo=LONDON)
        opens = window.next_open(before)
        self.assertEqual(opens.date().isoformat(), "2026-10-26")
        self.assertEqual((opens.hour, opens.minute), (9, 0))
        self.assertEqual(opens.utcoffset().total_seconds(), 0)  # GMT by then

    def test_nonsense_is_rejected_rather_than_guessed_at(self):
        for kwargs in (
            {"timezone": "Mars/Olympus"},
            {"start": "25:00"},
            {"start": "half nine"},
            {"start": "18:00", "end": "09:00"},
            {"weekdays": []},
            {"weekdays": [9]},
        ):
            with self.subTest(**kwargs):
                with self.assertRaises(WindowError):
                    CallWindow(**kwargs)

    def test_a_bad_window_in_a_definition_is_a_definition_error(self):
        with self.assertRaises(DefinitionError):
            outcome_from_definition({"goal": "g", "call_window": {"timezone": "Mars/Olympus"}})

    def test_both_shipped_scenarios_carry_a_window(self):
        for path in sorted(Path(SCENARIO).parent.glob("*.json")):
            with self.subTest(scenario=path.stem):
                _s, outcome = load_scenario(str(path))
                self.assertIsNotNone(outcome.call_window, path.stem)


class ParkingOnAClosedWindow(unittest.TestCase):
    def test_a_closed_window_parks_before_the_first_dial(self):
        engine, outcome, events = build(window=NEVER)
        engine.run(outcome)

        self.assertIs(outcome.status, OutcomeStatus.AWAITING_WINDOW)
        self.assertEqual(outcome.calls_placed(), 0)
        self.assertFalse(outcome.is_terminal(), "parked is not finished")
        parked = next(e for e in events if e["kind"] == "awaiting_window")
        self.assertIn("It opens", parked["detail"])

    def test_running_again_while_shut_does_not_pile_up_actions(self):
        engine, outcome, _ = build(window=NEVER)
        engine.run(outcome)
        for _ in range(3):
            engine.run(outcome)
        self.assertEqual(len(outcome.actions), 1)
        self.assertEqual(outcome.calls_placed(), 0)

    def test_it_resumes_at_the_same_call_when_the_window_opens(self):
        engine, outcome, _ = build(window=NEVER)
        engine.run(outcome)
        outcome.call_window = ALWAYS
        engine.run(outcome)
        engine.approve(outcome, outcome.pending_approval_action_id)

        self.assertIs(outcome.status, OutcomeStatus.RESOLVED)
        self.assertEqual(outcome.calls_placed(), 5)

    def test_an_approval_survives_the_window_closing_under_it(self):
        """The window shutting between 'Approve' and the dial must not throw the
        approval away and ask again — the user answered."""
        engine, outcome, _ = build()
        engine.run(outcome)
        self.assertIs(outcome.status, OutcomeStatus.AWAITING_APPROVAL)

        outcome.call_window = NEVER
        engine.approve(outcome, outcome.pending_approval_action_id)
        self.assertIs(outcome.status, OutcomeStatus.AWAITING_WINDOW)

        committing = [a for a in outcome.actions if a.commits_user]
        self.assertEqual(len(committing), 1)
        self.assertTrue(committing[0].approved)
        self.assertIs(committing[0].status, ActionStatus.PLANNED)

        outcome.call_window = ALWAYS
        engine.run(outcome)
        self.assertIs(outcome.status, OutcomeStatus.RESOLVED)
        self.assertEqual(len([a for a in outcome.actions if a.commits_user]), 1)

    def test_a_replay_is_not_subject_to_the_window(self):
        engine, outcome, _ = build(transport_cls=MockCalleClient, window=NEVER)
        engine.run(outcome)
        self.assertIs(outcome.status, OutcomeStatus.AWAITING_APPROVAL)

    def test_a_parked_run_round_trips_through_json(self):
        from outcome.models import Outcome

        engine, outcome, _ = build(window=NEVER)
        engine.run(outcome)
        restored = Outcome.from_dict(outcome.to_dict())
        self.assertIs(restored.status, OutcomeStatus.AWAITING_WINDOW)
        self.assertEqual(restored.call_window.describe(), NEVER.describe())


class NumberAllowlist(unittest.TestCase):
    def client(self, allowed: str | None):
        return CalleClient(api_key="test-key", allowed_numbers=parse_allowed_numbers(allowed))

    def test_it_reads_a_comma_separated_list_and_tidies_spacing(self):
        self.assertEqual(
            sorted(parse_allowed_numbers("+15550100001, +1 555-0100002")),
            ["+15550100001", "+15550100002"],
        )

    def test_an_unparseable_entry_is_an_error_not_a_silent_drop(self):
        with self.assertRaises(CalleError):
            parse_allowed_numbers("0800 nonsense")

    def test_a_number_off_the_list_is_refused(self):
        client = self.client("+15550100001")
        client.assert_dialable("+15550100001")
        with self.assertRaises(CalleError):
            client.assert_dialable("+15550100999")

    def test_a_non_e164_number_is_refused_even_with_no_list(self):
        with self.assertRaises(CalleError):
            self.client(None).assert_dialable("555-0100")

    def test_an_empty_list_means_unrestricted(self):
        self.client(None).assert_dialable("+15550100999")

    def test_the_guard_sits_under_place_not_beside_it(self):
        """A referral picked up mid-run reaches `place` without passing the form,
        so the check has to be inside it."""
        client = self.client("+15550100001")
        from outcome.calle import CallRequest

        with self.assertRaises(CalleError):
            client.place(CallRequest(phone="+15550100999", task="hello"))


class LivePreconditions(unittest.TestCase):
    def setUp(self):
        from outcome import cli

        self.cli = cli

    def test_a_live_run_needs_a_calling_window(self):
        _s, outcome = load_scenario(SCENARIO)
        outcome.call_window = None
        client = CalleClient(api_key="k", allowed_numbers=parse_allowed_numbers("+15550100001"))
        problems = self.cli._check_live_preconditions(outcome, client)
        self.assertTrue(any("calling window" in p for p in problems))

    def test_a_number_off_the_allowlist_stops_the_run_before_it_starts(self):
        _s, outcome = load_scenario(SCENARIO)
        client = CalleClient(api_key="k", allowed_numbers=parse_allowed_numbers("+15550100777"))
        problems = self.cli._check_live_preconditions(outcome, client)
        self.assertTrue(any("Halden Packaging" in p for p in problems))

    def test_a_ready_outcome_reports_no_problems(self):
        _s, outcome = load_scenario(SCENARIO)
        client = CalleClient(api_key="k", allowed_numbers=parse_allowed_numbers("+15550100001"))
        self.assertEqual(self.cli._check_live_preconditions(outcome, client), [])


class ALiveRunNeedsALedger(unittest.TestCase):
    """A live run without --store can place a call and lose its id. CALL-E has
    no endpoint that lists calls, so nothing can ask what was just dialled —
    which happened to us on the first call that connected, and cost us the
    transcript. The write-ahead ledger is a safety feature, so it is a poor
    thing to opt in to."""

    def _run(self, argv):
        import contextlib
        import io
        import os
        from unittest import mock

        from outcome import cli

        env = {"CALLE_API_KEY": "k", "CALLE_ALLOWED_NUMBERS": "+15550100001"}
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()):
            return cli.main(argv)

    def test_live_without_store_refuses_and_says_what_to_pass(self):
        with self.assertRaises(SystemExit) as caught:
            self._run(["run", SCENARIO, "--live"])
        message = str(caught.exception)
        self.assertIn("--store", message)
        self.assertIn("no endpoint that lists calls", message)

    def test_a_replay_run_still_needs_no_store(self):
        """Only a live run can lose a real call. The mock cannot."""
        self.assertEqual(self._run(["run", SCENARIO, "--approve", "auto"]), 0)


if __name__ == "__main__":
    unittest.main()
