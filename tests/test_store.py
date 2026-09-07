"""Surviving a crash without dialling anybody twice.

The ledger's whole reason to exist is the window between "we told CALL-E to
ring this number" and "we wrote down what happened". A process that dies in
that window and forgets restarts by ringing the same person again, and they
have no way to know the second call is a bug.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from outcome.calle import MockCalleClient
from outcome.engine import Engine
from outcome.loader import load_scenario
from outcome.models import ActionStatus, Outcome, OutcomeStatus
from outcome.store import Store

SCENARIO = str(Path(__file__).resolve().parent.parent / "scenarios" / "supplier-replacement.json")


class CrashingMock(MockCalleClient):
    """Dies mid-call, after CALL-E would already have been told to dial."""

    def __init__(self, scenario, crash_on: int) -> None:
        super().__init__(scenario)
        self.crash_on = crash_on

    def place(self, request):
        if len(self.placed) + 1 == self.crash_on:
            self.placed.append(request)
            raise RuntimeError("process died mid-call")
        return super().place(request)


class StoreTestCase(unittest.TestCase):
    """Gives each test a temporary database that is actually released.

    Every store has to be closed before the directory goes, because Windows
    refuses to delete a file that is still open — on Linux the unlink succeeds
    and the leak is invisible. `addCleanup` runs last-registered-first, so
    stores opened during the test close ahead of the directory that holds them.
    """

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = str(Path(self.dir.name) / "runs.sqlite3")
        self.addCleanup(self.dir.cleanup)

    def open_store(self, path: str | None = None) -> Store:
        store = Store(path or self.path)
        self.addCleanup(store.close)
        return store


class StoreBasics(StoreTestCase):
    def test_a_run_is_reloadable_in_full(self):
        scenario, outcome = load_scenario(SCENARIO)
        store = self.open_store()
        engine = Engine(MockCalleClient(scenario), store=store)
        engine.run(outcome)
        engine.approve(outcome, outcome.pending_approval_action_id)

        reopened = self.open_store()
        restored = reopened.load(outcome.id)
        self.assertEqual(restored.to_dict(), outcome.to_dict())
        self.assertIs(restored.status, OutcomeStatus.RESOLVED)
        self.assertEqual(len(reopened.calls_for(outcome.id)), 5)
        self.assertTrue(reopened.events_for(outcome.id))

    def test_every_dial_is_recorded_before_it_happens(self):
        scenario, outcome = load_scenario(SCENARIO)
        store = self.open_store()
        Engine(MockCalleClient(scenario), store=store).run(outcome)
        ledger = store.calls_for(outcome.id)
        self.assertEqual(len(ledger), outcome.calls_placed())
        self.assertTrue(all(entry.finished for entry in ledger))

    def test_events_are_durable_and_ordered(self):
        scenario, outcome = load_scenario(SCENARIO)
        store = self.open_store()
        seen: list[dict] = []
        Engine(MockCalleClient(scenario), on_event=seen.append, store=store).run(outcome)
        stored = store.events_for(outcome.id)
        self.assertEqual([e["kind"] for e in stored], [e["kind"] for e in seen])

    def test_a_run_with_no_store_still_works(self):
        scenario, outcome = load_scenario(SCENARIO)
        engine = Engine(MockCalleClient(scenario))
        engine.run(outcome)
        engine.approve(outcome, outcome.pending_approval_action_id)
        self.assertIs(outcome.status, OutcomeStatus.RESOLVED)


class CrashRecovery(StoreTestCase):
    def setUp(self):
        super().setUp()
        self.scenario, self.outcome = load_scenario(SCENARIO)
        self.store = self.open_store()

    def crash_on_third_call(self) -> Outcome:
        engine = Engine(CrashingMock(self.scenario, crash_on=3), store=self.store)
        with self.assertRaises(RuntimeError):
            engine.run(self.outcome)
        return self.store.load(self.outcome.id)

    def test_the_interrupted_call_is_left_claimed_and_unfinished(self):
        self.crash_on_third_call()
        unfinished = self.store.unfinished_calls()
        self.assertEqual(len(unfinished), 1)
        self.assertFalse(unfinished[0].finished)
        self.assertEqual(unfinished[0].phone, "+15550100002")

    def test_restarting_refuses_to_redial_the_interrupted_number(self):
        restored = self.crash_on_third_call()
        transport = MockCalleClient(self.scenario)
        Engine(transport, store=self.store).run(restored)

        self.assertIs(restored.status, OutcomeStatus.AWAITING_USER)
        self.assertEqual(
            transport.placed, [], "a restart must not dial anything it cannot account for"
        )

    def test_the_park_names_the_command_that_clears_it(self):
        restored = self.crash_on_third_call()
        events: list[dict] = []
        Engine(MockCalleClient(self.scenario), on_event=events.append, store=self.store).run(
            restored
        )
        parked = next(e for e in events if e["kind"] == "unresolved_call")
        self.assertIn("--resolve", parked["detail"])
        self.assertNotIn("+15550100002", parked["phone"], "the number must be masked")

    def test_resolving_it_as_placed_moves_on_without_redialling(self):
        """Recorded as blocked, not no_answer.

        `no_answer` is retryable, and retrying is the wrong move towards
        somebody who may have just spent five minutes on the phone with the
        agent. The credit is spent; the frontier advances instead.
        """
        restored = self.crash_on_third_call()
        key = self.store.unfinished_calls()[0].idempotency_key
        self.assertTrue(self.store.resolve_call(key))

        transport = MockCalleClient(self.scenario)
        Engine(transport, store=self.store).run(restored)

        self.assertNotIn("+15550100002", [r.phone for r in transport.placed])
        self.assertIsNot(restored.status, OutcomeStatus.AWAITING_USER)
        northgate = next(o for o in restored.organizations if o.phone == "+15550100002")
        self.assertEqual(restored.calls_to_org(northgate.id), 1)

        # The paid-for call has to actually land as evidence. Without this the
        # run silently loses it: the number is not dialled again *and* nothing
        # is recorded, which looks identical from the outside and is not.
        recorded = [e for e in restored.evidence if e.org_id == northgate.id]
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0].verdict.value, "blocked")
        self.assertIn("interrupted", recorded[0].blockers[0])

    def test_an_unresolved_call_leaves_its_action_resumable(self):
        """Parking is not failing. A FAILED action is never picked up again, so
        marking it failed would make `--resolve` a no-op."""
        restored = self.crash_on_third_call()
        Engine(MockCalleClient(self.scenario), store=self.store).run(restored)
        self.assertIs(restored.status, OutcomeStatus.AWAITING_USER)
        stuck = [a for a in restored.actions if a.status is ActionStatus.RUNNING]
        self.assertEqual(len(stuck), 1)

    def test_forgetting_it_allows_exactly_one_redial(self):
        restored = self.crash_on_third_call()
        key = self.store.unfinished_calls()[0].idempotency_key
        self.assertTrue(self.store.forget_call(key))
        self.assertEqual(self.store.unfinished_calls(), [])

        transport = MockCalleClient(self.scenario)
        Engine(transport, store=self.store).run(restored)
        self.assertIn("+15550100002", [r.phone for r in transport.placed])

    def test_forget_refuses_to_touch_a_finished_call(self):
        scenario, outcome = load_scenario(SCENARIO)
        Engine(MockCalleClient(scenario), store=self.store).run(outcome)
        finished = self.store.calls_for(outcome.id)[0]
        self.assertFalse(self.store.forget_call(finished.idempotency_key))
        self.assertFalse(self.store.resolve_call(finished.idempotency_key))


class ReplayingACompletedCall(StoreTestCase):
    """The other half of the crash window: the call finished, and the process
    died before the result was written into the outcome."""

    def test_a_completed_call_is_replayed_not_repeated(self):
        scenario, outcome = load_scenario(SCENARIO)
        store = self.open_store()
        Engine(MockCalleClient(scenario), store=store).run(outcome)
        placed_first_time = outcome.calls_placed()

        # Roll the outcome back to the instant before the last result landed:
        # the call completed and the ledger knows it, but the evidence never
        # reached the outcome, so the action is still RUNNING.
        rolled_back = store.load(outcome.id)
        rolled_back.actions = [a for a in rolled_back.actions if not a.commits_user]
        rolled_back.evidence.pop()
        last_call = [a for a in rolled_back.actions if a.status is ActionStatus.DONE][-1]
        last_call.status = ActionStatus.RUNNING
        rolled_back.status = OutcomeStatus.WORKING
        rolled_back.pending_approval_action_id = None

        transport = MockCalleClient(scenario)
        events: list[dict] = []
        Engine(transport, on_event=events.append, store=store).run(rolled_back)

        self.assertEqual(transport.placed, [], "the result was on disk; nothing to dial")
        self.assertTrue(any(e["kind"] == "replayed" for e in events))
        self.assertEqual(rolled_back.calls_placed(), placed_first_time)


if __name__ == "__main__":
    unittest.main()
