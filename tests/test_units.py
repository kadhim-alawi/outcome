"""Unit tests for the parts that decide, parse, or refuse."""

from __future__ import annotations

import unittest
from datetime import date

from outcome.approval import classify
from outcome.calle import ALLOWED_HOSTS, CallRequest, CalleError, assert_trusted_base_url
from outcome.constraints import Judgement, best_acceptable, evaluate
from outcome.evidence import extract, parse_money
from outcome.interpret import RuleInterpreter, parse_budget, parse_deadline
from outcome.models import (
    Action,
    ActionType,
    CallVerdict,
    Constraint,
    ConstraintKind,
    Offer,
    mask_phone,
)
from outcome.planner import build_commit_task, build_gathering_task
from outcome.calle import CallOutcome


BUDGET = Constraint(kind=ConstraintKind.BUDGET, description="under 500", value=500, hard=True)
DEADLINE = Constraint(
    kind=ConstraintKind.DEADLINE, description="by the 11th", value="2026-09-11", hard=True
)
REF = Constraint(
    kind=ConstraintKind.REQUIRED_FACT, description="a reference", value="reference", hard=False
)


class Constraints(unittest.TestCase):
    def test_over_budget_is_a_blocking_violation(self):
        result = evaluate(Offer(summary="x", org_id="o", price=612.0), [BUDGET])
        self.assertFalse(result.acceptable)
        self.assertTrue(result.results[0].blocking)

    def test_a_missing_price_is_unknown_not_free(self):
        result = evaluate(Offer(summary="x", org_id="o", price=None), [BUDGET])
        self.assertIs(result.results[0].judgement, Judgement.UNKNOWN)
        self.assertTrue(result.acceptable, "unknown must not block on its own")

    def test_a_soft_violation_does_not_block(self):
        result = evaluate(Offer(summary="x", org_id="o", price=10.0), [BUDGET, REF])
        self.assertTrue(result.acceptable)
        self.assertEqual(len(result.violations), 1)

    def test_deadline_compares_dates_not_strings(self):
        late = evaluate(Offer(summary="x", org_id="o", eta="2026-09-12"), [DEADLINE])
        onTime = evaluate(Offer(summary="x", org_id="o", eta="2026-09-11"), [DEADLINE])
        self.assertFalse(late.acceptable)
        self.assertTrue(onTime.acceptable)

    def test_cheapest_acceptable_offer_wins(self):
        offers = [
            Offer(summary="a", org_id="o1", price=480.0, eta="2026-09-11"),
            Offer(summary="b", org_id="o2", price=438.0, eta="2026-09-10"),
            Offer(summary="c", org_id="o3", price=612.0, eta="2026-09-09"),
        ]
        best, every = best_acceptable(offers, [BUDGET, DEADLINE])
        self.assertEqual(best.offer.price, 438.0)
        self.assertEqual(len(every), 3)

    def test_no_acceptable_offer_returns_none_with_the_reasons(self):
        best, every = best_acceptable(
            [Offer(summary="a", org_id="o", price=900.0)], [BUDGET]
        )
        self.assertIsNone(best)
        self.assertEqual(len(every), 1)


MINIMUM = Constraint(
    kind=ConstraintKind.MINIMUM, description="at least 62.50", value=62.5, hard=True
)


class ValueFloor(unittest.TestCase):
    """A `minimum` reverses the comparison a `budget` makes: recovering a refund
    and buying a replacement are the same shape pointed the other way."""

    def test_an_offer_below_the_floor_is_a_blocking_violation(self):
        result = evaluate(Offer(summary="goodwill", org_id="o", price=40.0), [MINIMUM])
        self.assertFalse(result.acceptable)
        self.assertIn("short of", result.results[0].detail)

    def test_meeting_the_floor_exactly_satisfies_it(self):
        result = evaluate(Offer(summary="full", org_id="o", price=62.5), [MINIMUM])
        self.assertTrue(result.acceptable)

    def test_a_missing_amount_is_unknown_not_generous(self):
        result = evaluate(Offer(summary="x", org_id="o", price=None), [MINIMUM])
        self.assertIs(result.results[0].judgement, Judgement.UNKNOWN)

    def test_larger_wins_when_only_a_floor_is_set(self):
        offers = [
            Offer(summary="a", org_id="o1", price=62.5),
            Offer(summary="b", org_id="o2", price=80.0),
        ]
        best, _ = best_acceptable(offers, [MINIMUM])
        self.assertEqual(best.offer.price, 80.0)

    def test_cheaper_wins_when_a_ceiling_is_also_set(self):
        band = [MINIMUM, Constraint(kind=ConstraintKind.BUDGET, description="cap", value=100)]
        offers = [
            Offer(summary="a", org_id="o1", price=70.0),
            Offer(summary="b", org_id="o2", price=95.0),
        ]
        best, _ = best_acceptable(offers, band)
        self.assertEqual(best.offer.price, 70.0)

    def test_an_unquoted_amount_sorts_last_in_either_direction(self):
        offers = [
            Offer(summary="unquoted", org_id="o1", price=None),
            Offer(summary="quoted", org_id="o2", price=62.5),
        ]
        for constraints in ([MINIMUM], [Constraint(
            kind=ConstraintKind.BUDGET, description="cap", value=100
        )]):
            best, _ = best_acceptable(offers, constraints)
            self.assertEqual(best.offer.price, 62.5)


class EvidenceParsing(unittest.TestCase):
    def test_money_is_read_from_the_shapes_a_caller_produces(self):
        self.assertEqual(
            [parse_money(v) for v in (438, "438", "$438.00", "USD 1,438", "  612 ")],
            [438.0, 438.0, 438.0, 1438.0, 612.0],
        )

    def test_unreadable_money_is_none_rather_than_zero(self):
        for value in ("about four hundred", "", None, True, {}):
            self.assertIsNone(parse_money(value), value)

    def test_a_referral_without_a_dialable_number_is_dropped(self):
        action = Action(type=ActionType.CALL, purpose="p", target_org_id="org_1")
        call = CallOutcome(
            call_id="c",
            status="completed",
            structured={
                "reached": True,
                "verdict": "blocked",
                "referrals": [
                    {"org_name": "Good", "phone": "+15550100009"},
                    {"org_name": "No number", "phone": ""},
                    {"org_name": "Not E.164", "phone": "555-0100"},
                    {"phone": "+15550100010"},
                ],
            },
        )
        evidence = extract(action, call)
        self.assertEqual([r.org_name for r in evidence.referrals], ["Good"])

    def test_a_failed_call_is_never_read_as_testimony(self):
        action = Action(type=ActionType.CALL, purpose="p")
        call = CallOutcome(
            call_id="c",
            status="failed",
            structured={"reached": True, "verdict": "confirmed", "facts": ["all sorted"]},
        )
        self.assertIs(extract(action, call).verdict, CallVerdict.NO_ANSWER)

    def test_an_empty_offer_object_is_not_an_offer(self):
        action = Action(type=ActionType.CALL, purpose="p")
        call = CallOutcome(
            call_id="c",
            status="completed",
            structured={"reached": True, "verdict": "offer", "offer": {}},
        )
        self.assertIsNone(extract(action, call).offer)

    def test_missing_fields_do_not_raise(self):
        action = Action(type=ActionType.CALL, purpose="p")
        self.assertIsNotNone(
            extract(action, CallOutcome(call_id="c", status="completed", structured={}))
        )


class ApprovalNet(unittest.TestCase):
    def _org(self):
        from outcome.models import Organization, Outcome

        outcome = Outcome(goal="Get the pallet replaced", constraints=[BUDGET, DEADLINE])
        org = outcome.add_organization(
            Organization(name="Halden", phone="+15550100001", role="supplier")
        )
        return outcome, org

    def test_a_gathering_script_is_not_flagged_by_its_own_prohibitions(self):
        outcome, org = self._org()
        action = Action(
            type=ActionType.CALL,
            purpose=f"Call {org.name} — can they fix this?",
            task_prompt=build_gathering_task(outcome, org, "Find out if they can help"),
        )
        decision = classify(action)
        self.assertFalse(decision.required, decision.reason)

    def test_a_flagged_action_is_always_gated(self):
        action = Action(type=ActionType.CALL, purpose="Call back", commits_user=True)
        self.assertTrue(classify(action).required)

    def test_an_unflagged_committing_script_is_caught_anyway(self):
        action = Action(
            type=ActionType.CALL,
            purpose="Ring the depot",
            task_prompt="Please place the order for 500 boxes and confirm the total.",
        )
        decision = classify(action)
        self.assertTrue(decision.required)
        self.assertIn("place the order", decision.reason)

    def test_the_commit_script_names_the_exact_authorised_terms(self):
        outcome, org = self._org()
        offer = Offer(summary="500 boxes", org_id=org.id, price=438.0, eta="2026-09-10")
        task = build_commit_task(outcome, org, offer)
        self.assertIn("USD 438.00", task)
        self.assertIn("2026-09-10", task)
        self.assertIn("do NOT accept", task)


class Transport(unittest.TestCase):
    def test_the_credential_only_goes_to_call_e(self):
        for bad in ("https://api.heycall-e.com.evil.example", "http://api.heycall-e.com"):
            with self.assertRaises(CalleError):
                assert_trusted_base_url(bad)
        for good in ALLOWED_HOSTS:
            self.assertEqual(
                assert_trusted_base_url(f"https://{good}/"), f"https://{good}"
            )

    def test_the_idempotency_key_is_stable_for_an_unchanged_request(self):
        one = CallRequest(phone="+15550100001", task="hello")
        two = CallRequest(phone="+15550100001", task="hello")
        three = CallRequest(phone="+15550100001", task="hello there")
        self.assertEqual(one.idempotency_key(), two.idempotency_key())
        self.assertNotEqual(one.idempotency_key(), three.idempotency_key())

    def test_the_payload_matches_the_call_e_contract(self):
        payload = CallRequest(phone="+15550100001", task="hello").payload()
        self.assertEqual(
            sorted(payload), ["metadata", "recipient_result_schema", "recipients", "task"]
        )
        self.assertEqual(payload["recipients"], [{"phones": ["+15550100001"]}])


class Interpretation(unittest.TestCase):
    SATURDAY = date(2026, 9, 5)

    def test_reads_a_limit_and_a_weekday(self):
        parsed = RuleInterpreter().interpret(
            "Get a replacement pallet before Friday, under $500", self.SATURDAY
        )
        kinds = {c.kind: c.value for c in parsed["constraints"]}
        self.assertEqual(kinds[ConstraintKind.BUDGET], 500.0)
        self.assertEqual(kinds[ConstraintKind.DEADLINE], "2026-09-11")

    def test_an_amount_that_is_not_a_limit_is_not_a_budget(self):
        self.assertIsNone(parse_budget("$500 of stock was damaged, get it replaced"))

    def test_relative_dates_resolve_against_today(self):
        self.assertEqual(parse_deadline("within 2 weeks", self.SATURDAY), date(2026, 9, 19))
        self.assertEqual(parse_deadline("by tomorrow", self.SATURDAY), date(2026, 9, 6))
        self.assertIsNone(parse_deadline("as soon as you can", self.SATURDAY))

    def test_nothing_is_invented_when_nothing_was_said(self):
        parsed = RuleInterpreter().interpret("Sort out my broken delivery", self.SATURDAY)
        self.assertEqual(parsed["constraints"], [])


class Masking(unittest.TestCase):
    def test_only_the_last_four_digits_survive(self):
        self.assertEqual(mask_phone("+15550100001"), "+*******0001")
        self.assertEqual(mask_phone("555-0100"), "***0100")
        self.assertEqual(mask_phone("12"), "**")


if __name__ == "__main__":
    unittest.main()
