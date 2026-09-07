"""The result schema has to be one CALL-E will actually accept.

Written after a live run was refused with:

    HTTP 400 recipient_result_schema_invalid
    unsupported JSON Schema type at $.properties.offer: ['object', 'null']

The request never reached the phone, which is the good half. The bad half is
that the rules are published — CALL-E's calls guide lists exactly which JSON
Schema features it supports — and nothing checked our schema against them until
a real dial did.
"""

from __future__ import annotations

import unittest

from outcome.calle import (
    EVIDENCE_SCHEMA,
    RESERVED_RECIPIENT_FIELDS,
    SUPPORTED_TYPES,
    validate_result_schema,
)
from outcome.evidence import extract
from outcome.calle import CallOutcome
from outcome.models import Action, ActionType, CallVerdict


class OurSchemaIsAcceptable(unittest.TestCase):
    def test_the_evidence_schema_passes(self):
        self.assertEqual(validate_result_schema(EVIDENCE_SCHEMA), [])

    def test_it_declares_no_union_types_anywhere(self):
        """The exact defect the live 400 reported."""

        def walk(node, path="$"):
            if isinstance(node, dict):
                if isinstance(node.get("type"), list):
                    self.fail(f"{path} declares a union type: {node['type']}")
                for key, value in node.items():
                    walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{path}[{index}]")

        walk(EVIDENCE_SCHEMA)

    def test_it_uses_no_reserved_recipient_field_names(self):
        top_level = set(EVIDENCE_SCHEMA["properties"])
        self.assertEqual(top_level & RESERVED_RECIPIENT_FIELDS, set())

    def test_required_is_kept_minimal(self):
        """CALL-E returns null for the whole result when it cannot satisfy the
        schema, so every extra required field trades a partial answer for no
        answer at all."""
        self.assertEqual(EVIDENCE_SCHEMA["required"], ["verdict"])

    def test_every_object_forbids_extra_properties(self):
        def walk(node, path="$"):
            if not isinstance(node, dict):
                return
            if node.get("type") == "object":
                self.assertIs(
                    node.get("additionalProperties"), False, f"{path} allows extras"
                )
            for key in ("properties", "items"):
                child = node.get(key)
                if isinstance(child, dict):
                    if key == "items":
                        walk(child, f"{path}[]")
                    else:
                        for name, value in child.items():
                            walk(value, f"{path}.{name}")

        walk(EVIDENCE_SCHEMA)


class TheValidatorCatchesWhatCalleRejects(unittest.TestCase):
    def test_a_union_type(self):
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {"offer": {"type": ["object", "null"]}},
        }
        problems = validate_result_schema(schema)
        self.assertTrue(any("union" in p for p in problems), problems)

    def test_a_reserved_top_level_name(self):
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {"summary": {"type": "string"}},
        }
        self.assertTrue(any("reserved" in p for p in validate_result_schema(schema)))

    def test_a_reserved_name_is_fine_nested(self):
        """The reserved list is about recipient response fields, which are the
        top-level ones."""
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "offer": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"status": {"type": "string"}},
                }
            },
        }
        self.assertEqual(validate_result_schema(schema), [])

    def test_the_unsupported_keywords(self):
        for keyword in ("$ref", "oneOf", "anyOf", "allOf"):
            with self.subTest(keyword=keyword):
                schema = {"type": "object", "additionalProperties": False, "properties": {
                    "x": {"type": "string", keyword: ["whatever"]}}}
                self.assertTrue(any(keyword in p for p in validate_result_schema(schema)))

    def test_additional_properties_true(self):
        schema = {"type": "object", "additionalProperties": True, "properties": {}}
        self.assertTrue(any("additionalProperties" in p for p in validate_result_schema(schema)))

    def test_an_array_without_items(self):
        schema = {"type": "object", "additionalProperties": False,
                  "properties": {"xs": {"type": "array"}}}
        self.assertTrue(any("items" in p for p in validate_result_schema(schema)))

    def test_required_naming_a_field_that_does_not_exist(self):
        schema = {"type": "object", "additionalProperties": False,
                  "required": ["ghost"], "properties": {"real": {"type": "string"}}}
        self.assertTrue(any("ghost" in p for p in validate_result_schema(schema)))

    def test_an_unsupported_type(self):
        schema = {"type": "object", "additionalProperties": False,
                  "properties": {"x": {"type": "null"}}}
        self.assertTrue(any("null" in p for p in validate_result_schema(schema)))
        self.assertNotIn("null", SUPPORTED_TYPES)


class ReadingTheWireFormatBack(unittest.TestCase):
    """The schema changed shape, so the extractor has to read the new one — and
    keep reading the old one, because a model handed a description may reach for
    either word."""

    def _extract(self, structured):
        return extract(
            Action(type=ActionType.CALL, purpose="p", target_org_id="org_1"),
            CallOutcome(call_id="c", status="completed", structured=structured),
        )

    def test_reached_as_a_string_enum(self):
        self.assertIs(
            self._extract({"reached": "no", "verdict": "partial"}).verdict,
            CallVerdict.NO_ANSWER,
        )

    def test_reached_as_a_boolean_still_works(self):
        self.assertIs(
            self._extract({"reached": False, "verdict": "partial"}).verdict,
            CallVerdict.NO_ANSWER,
        )

    def test_unknown_is_not_a_no(self):
        """A call that cannot say whether it reached anyone has not established
        that it did not."""
        self.assertIs(
            self._extract({"reached": "unknown", "verdict": "partial"}).verdict,
            CallVerdict.PARTIAL,
        )

    def test_what_is_offered_is_read(self):
        evidence = self._extract(
            {
                "reached": "yes",
                "verdict": "offer",
                "offer": {"what_is_offered": "500 boxes", "price": "438.00", "eta": "2026-09-10"},
            }
        )
        self.assertEqual(evidence.offer.summary, "500 boxes")
        self.assertEqual(evidence.offer.price, 438.0)

    def test_the_old_summary_key_is_still_read(self):
        evidence = self._extract(
            {"reached": "yes", "verdict": "offer", "offer": {"summary": "x", "price": "10"}}
        )
        self.assertEqual(evidence.offer.summary, "x")

    def test_empty_strings_mean_absent_not_zero(self):
        evidence = self._extract(
            {
                "reached": "yes",
                "verdict": "offer",
                "offer": {"what_is_offered": "boxes", "price": "", "eta": "", "reference": ""},
            }
        )
        self.assertIsNone(evidence.offer.price, "an unquoted price must not become 0")
        self.assertIsNone(evidence.offer.eta)
        self.assertIsNone(evidence.offer.reference)

    def test_an_empty_offer_object_is_no_offer(self):
        self.assertIsNone(self._extract({"reached": "yes", "verdict": "partial", "offer": {}}).offer)


class ShippedScenariosMatchTheWireFormat(unittest.TestCase):
    """A mock that returns a different shape from the live provider is a mock
    that lies, and the whole point of it is that the rehearsed run is the real
    one."""

    def test_no_scenario_uses_the_pre_400_shape(self):
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent / "scenarios"
        for path in sorted(root.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for index, response in enumerate(data.get("responses", [])):
                structured = response.get("structured", {})
                with self.subTest(scenario=path.stem, response=index):
                    self.assertNotIsInstance(
                        structured.get("reached"), bool, "reached should be a string enum"
                    )
                    offer = structured.get("offer")
                    self.assertIsInstance(offer, dict, "offer is never null on the wire")
                    self.assertNotIn("summary", offer, "'summary' is a reserved name")
                    if "price" in offer:
                        self.assertIsInstance(offer["price"], str)


if __name__ == "__main__":
    unittest.main()
