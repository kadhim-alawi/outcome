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

SCENARIOS = Path(__file__).resolve().parent.parent / "scenarios"
SCENARIO = str(SCENARIOS / "supplier-replacement.json")
BILL_DISPUTE = str(SCENARIOS / "bill-dispute.json")


def build(path: str = SCENARIO, **overrides):
    scenario, outcome = load_scenario(path)
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


class SecondScenario(unittest.TestCase):
    """The bill dispute has a different shape from the supplier run: escalation
    inside one company rather than across a supply chain, and a value floor
    instead of a cost ceiling. It runs on the same engine with no special
    casing, which is the only claim worth testing here."""

    def test_climbs_an_escalation_chain_to_a_full_reversal(self):
        engine, outcome, _ = build(BILL_DISPUTE)
        engine.run(outcome)
        engine.approve(outcome, outcome.pending_approval_action_id)

        self.assertIs(outcome.status, OutcomeStatus.RESOLVED)
        self.assertEqual(outcome.resolution["reference"], "CR-77310")
        self.assertEqual(outcome.resolution["offer"]["price"], 62.5)
        self.assertEqual(outcome.calls_placed(), 4)

    def test_the_goodwill_offer_is_rejected_for_being_too_small(self):
        engine, outcome, events = build(BILL_DISPUTE)
        engine.run(outcome)
        low = next(
            e for e in events
            if e["kind"] == "evidence" and (e.get("offer") or {}).get("price") == 40.0
        )
        self.assertFalse(low["acceptable"])
        self.assertIn("short of the USD 62.50", str(low["constraint_report"]))

    def test_both_further_departments_were_discovered_on_calls(self):
        engine, outcome, _ = build(BILL_DISPUTE)
        engine.run(outcome)
        self.assertEqual(sum(1 for o in outcome.organizations if o.discovered_by), 2)

    def test_the_floor_is_stated_in_the_call_script(self):
        _engine, outcome, _ = build(BILL_DISPUTE)
        from outcome.planner import FrontierPlanner

        action = FrontierPlanner().next_action(outcome)
        self.assertIn("at least 62.5", action.task_prompt)


class EveryScenario(unittest.TestCase):
    def test_each_scenario_runs_to_a_terminal_state(self):
        for path in sorted(SCENARIOS.glob("*.json")):
            with self.subTest(scenario=path.stem):
                engine, outcome, _ = build(str(path))
                engine.run(outcome)
                if outcome.status is OutcomeStatus.AWAITING_APPROVAL:
                    engine.approve(outcome, outcome.pending_approval_action_id)
                self.assertTrue(outcome.is_terminal(), outcome.status)
                self.assertIsNotNone(outcome.resolution)
                self.assertLessEqual(outcome.calls_placed(), outcome.budget.max_calls)

    def test_no_scenario_uses_a_number_outside_the_fiction_range(self):
        import json
        import re

        for path in sorted(SCENARIOS.glob("*.json")):
            numbers = set(re.findall(r'"\+\d{6,15}"', path.read_text(encoding="utf-8")))
            for number in numbers:
                with self.subTest(scenario=path.stem, number=number):
                    self.assertRegex(number, r'^"\+1555010\d{4}"$')
            self.assertTrue(numbers, f"{path.stem} has no phone numbers")
            json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
