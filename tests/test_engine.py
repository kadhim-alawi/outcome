"""End-to-end behaviour of the agent loop, driven by the mock transport.

These run the real engine, planner, constraint checker and evidence extractor.
Only the phone line is fake.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from outcome.calle import DryRunCalleClient, MockCalleClient
from outcome.engine import Engine
from outcome.loader import load_scenario
from outcome.models import OutcomeStatus

SCENARIO = str(Path(__file__).resolve().parent.parent / "scenarios" / "supplier-replacement.json")


def build(**overrides):
    scenario, outcome = load_scenario(SCENARIO)
    for key, value in overrides.items():
        setattr(outcome.budget, key, value)
    events: list[dict] = []
    engine = Engine(MockCalleClient(scenario), on_event=events.append)
    return engine, outcome, events


def kinds(events):
    return [e["kind"] for e in events]


class ResolutionPath(unittest.TestCase):
    def test_reaches_resolution_through_approval(self):
        engine, outcome, events = build()
        engine.run(outcome)

        self.assertIs(outcome.status, OutcomeStatus.AWAITING_APPROVAL)
        self.assertIn("approval_required", kinds(events))

        engine.approve(outcome, outcome.pending_approval_action_id)

        self.assertIs(outcome.status, OutcomeStatus.RESOLVED)
        self.assertEqual(outcome.resolution["reference"], "BWD-48291")
        self.assertEqual(outcome.resolution["offer"]["price"], 438.0)
        self.assertEqual(outcome.calls_placed(), 5)

    def test_retries_a_number_that_did_not_answer(self):
        engine, outcome, _ = build()
        engine.run(outcome)
        halden = next(o for o in outcome.organizations if o.name == "Halden Packaging")
        self.assertEqual(outcome.calls_to_org(halden.id), 2)

    def test_follows_referrals_the_user_never_supplied(self):
        engine, outcome, events = build()
        engine.run(outcome)

        discovered = [o for o in outcome.organizations if o.discovered_by]
        self.assertEqual(
            sorted(o.name for o in discovered),
            ["Brightwater Depot", "Northgate Distribution"],
        )
        self.assertEqual(kinds(events).count("lead_discovered"), 2)

    def test_a_lead_is_reported_after_the_call_that_produced_it(self):
        engine, outcome, events = build()
        engine.run(outcome)
        sequence = kinds(events)
        first_lead = sequence.index("lead_discovered")
        self.assertEqual(sequence[first_lead - 1], "evidence")

    def test_rejects_the_over_budget_offer_and_keeps_going(self):
        engine, outcome, events = build()
        engine.run(outcome)

        offers = {o.price: o for o in outcome.offers()}
        self.assertIn(612.0, offers)
        rejected = next(
            e for e in events
            if e["kind"] == "evidence" and (e.get("offer") or {}).get("price") == 612.0
        )
        self.assertFalse(rejected["acceptable"])
        self.assertIn("over the USD 500.00 limit", str(rejected["constraint_report"]))

    def test_final_report_lists_what_was_turned_down_once(self):
        engine, outcome, _ = build()
        engine.run(outcome)
        engine.approve(outcome, outcome.pending_approval_action_id)
        considered = outcome.resolution["considered"]
        self.assertEqual([c["offer"]["price"] for c in considered], [612.0])


class ApprovalGate(unittest.TestCase):
    def test_no_call_is_placed_while_waiting_for_approval(self):
        engine, outcome, _ = build()
        engine.run(outcome)
        before = outcome.calls_placed()
        engine.run(outcome)  # calling run again must not sneak the call through
        self.assertEqual(outcome.calls_placed(), before)
        self.assertIs(outcome.status, OutcomeStatus.AWAITING_APPROVAL)

    def test_only_the_committing_call_is_gated(self):
        engine, outcome, events = build()
        engine.run(outcome)
        gated = [e for e in events if e["kind"] == "approval_required"]
        self.assertEqual(len(gated), 1)
        placed = [e for e in events if e["kind"] == "calling"]
        self.assertEqual(sum(1 for e in placed if e["commits_user"]), 0)

    def test_declining_does_not_re_propose_the_same_offer(self):
        engine, outcome, _ = build()
        engine.run(outcome)
        engine.reject(outcome, outcome.pending_approval_action_id, "Too slow.")

        self.assertIs(outcome.status, OutcomeStatus.ABANDONED)
        self.assertEqual(len(outcome.declined_offer_ids), 1)
        self.assertEqual(outcome.calls_placed(), 4)

    def test_approving_an_unknown_action_is_an_error(self):
        engine, outcome, _ = build()
        engine.run(outcome)
        with self.assertRaises(ValueError):
            engine.approve(outcome, "act_does_not_exist")


class Budget(unittest.TestCase):
    def test_stops_dialling_at_the_call_budget(self):
        engine, outcome, events = build(max_calls=2)
        engine.run(outcome)

        self.assertIs(outcome.status, OutcomeStatus.ABANDONED)
        self.assertEqual(outcome.calls_placed(), 2)
        self.assertIn("budget", outcome.resolution["why"].lower())

    def test_abandoned_report_still_carries_what_was_learned(self):
        engine, outcome, _ = build(max_calls=3)
        engine.run(outcome)
        self.assertIs(outcome.status, OutcomeStatus.ABANDONED)
        self.assertTrue(outcome.resolution["blockers"])
        self.assertTrue(any(p["facts"] for p in outcome.resolution["parties"]))

    def test_per_org_cap_stops_endless_redialling(self):
        scenario, outcome = load_scenario(SCENARIO)
        # Nobody ever answers anywhere.
        scenario = dict(scenario, responses=[])
        outcome.budget.max_calls = 10
        outcome.budget.max_calls_per_org = 2
        engine = Engine(MockCalleClient(scenario))
        engine.run(outcome)

        self.assertIs(outcome.status, OutcomeStatus.ABANDONED)
        self.assertEqual(outcome.calls_placed(), 2)


class DryRun(unittest.TestCase):
    def test_dry_run_places_nothing_and_renders_the_request(self):
        _scenario, outcome = load_scenario(SCENARIO)
        transport = DryRunCalleClient()
        engine = Engine(transport)
        engine.run(outcome)

        self.assertIs(outcome.status, OutcomeStatus.ABANDONED)
        self.assertTrue(transport.requests)
        first = transport.requests[0]
        self.assertIn("AI assistant", first.task)
        self.assertEqual(first.payload()["recipients"], [{"phones": ["+15550100001"]}])


class Persistence(unittest.TestCase):
    def test_a_finished_outcome_round_trips_through_json(self):
        from outcome.models import Outcome

        engine, outcome, _ = build()
        engine.run(outcome)
        engine.approve(outcome, outcome.pending_approval_action_id)

        restored = Outcome.from_dict(outcome.to_dict())
        self.assertEqual(restored.to_dict(), outcome.to_dict())
        self.assertEqual(restored.calls_placed(), 5)
        self.assertIs(restored.status, OutcomeStatus.RESOLVED)


if __name__ == "__main__":
    unittest.main()
