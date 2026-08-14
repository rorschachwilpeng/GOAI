from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

from golden_path import (  # noqa: E402
    ToolError,
    create_resolution_plan,
    evaluate_rebooking,
    execute_rebooking,
    get_authorized_order,
    get_order_state,
    load_fixture,
    record_customer_confirmation,
    resolve_order_reference,
    verify_rebooking,
)
from run_golden_path import run_golden_path  # noqa: E402


FIXTURE = SERVICE_DIR / "fixtures" / "golden-case.json"


class GoldenPathTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = load_fixture(FIXTURE)
        self.case_id = self.store["case_id"]
        self.customer_id = self.store["session"]["customer_id"]
        self.store["cases"][self.case_id] = {
            "case_id": self.case_id,
            "customer_id": self.customer_id,
            "case_state": "RESOLVING",
            "resolution_mode": None,
        }

    def prepare_plan_and_risk(self, price_difference_cny: int = 180):
        match = resolve_order_reference(
            self.store,
            self.customer_id,
            {
                "hotel_name": "上海虹桥海湾花园酒店",
                "check_in_date": "2026-08-15",
            },
        )
        context = get_authorized_order(
            self.store,
            self.customer_id,
            match["order_ref"],
        )
        plan = create_resolution_plan(self.store, match["order_ref"], context)
        plan["price_difference_cny"] = price_difference_cny
        self.store["resolution_plans"][plan["resolution_plan_id"]] = copy.deepcopy(plan)
        risk = evaluate_rebooking(
            self.store,
            self.customer_id,
            match["order_ref"],
            plan,
        )
        return plan, risk

    def test_golden_path_resolves_and_writes_evidence(self):
        with tempfile.TemporaryDirectory() as output_dir:
            result = run_golden_path(FIXTURE, output_dir)
            self.assertEqual(result["case_state"], "RESOLVED")
            self.assertEqual(result["resolution_mode"], "AUTONOMOUS")
            self.assertEqual(result["order_state"], "REBOOKED")
            self.assertEqual(result["replacement_hotel_id"], "HTL-SHA-HARBOR")
            self.assertEqual(result["price_difference_cny"], 180)
            self.assertEqual(result["verification_status"], "PASSED")
            self.assertEqual(result["internal_human_interventions"], 0)

            trace_path = Path(output_dir) / "golden-trace.jsonl"
            case_card_path = Path(output_dir) / "golden-case-card.json"
            result_path = Path(output_dir) / "golden-result.json"
            self.assertTrue(trace_path.is_file())
            self.assertTrue(case_card_path.is_file())
            self.assertTrue(result_path.is_file())

            events = [json.loads(line) for line in trace_path.read_text().splitlines()]
            event_types = [event["event_type"] for event in events]
            for required_event in (
                "ORDER_MATCH_MULTIPLE",
                "CUSTOMER_INFO_REQUESTED",
                "ORDER_MATCH_UNIQUE",
                "RISK_EVALUATED",
                "CUSTOMER_CONFIRMATION_RECORDED",
                "EXECUTION_AUTHORIZED",
                "REBOOKING_EXECUTED",
                "ORDER_STATE_READ",
                "VERIFICATION_PASSED",
                "CUSTOMER_NOTIFIED",
                "CASE_RESOLVED",
                "CASE_CARD_WRITTEN",
            ):
                self.assertIn(required_event, event_types)

    def test_multiple_match_does_not_expose_candidate_details(self):
        result = resolve_order_reference(self.store, self.customer_id, {})
        self.assertEqual(
            result,
            {
                "status": "MULTIPLE",
                "candidate_count": 2,
                "missing_fields": ["hotel_name", "check_in_date"],
                "candidates": [],
            },
        )
        self.assertNotIn("H-C001-001", json.dumps(result))
        self.assertNotIn("H-C002-001", json.dumps(result))

    def test_cross_customer_order_reference_is_denied(self):
        other_match = resolve_order_reference(
            self.store,
            "C002",
            {
                "hotel_name": "上海虹桥海湾花园酒店",
                "check_in_date": "2026-08-15",
            },
        )
        with self.assertRaisesRegex(ToolError, "not authorized") as error:
            get_authorized_order(self.store, "C001", other_match["order_ref"])
        self.assertEqual(error.exception.code, "ORDER_ACCESS_DENIED")

    def test_missing_customer_confirmation_blocks_write(self):
        plan, risk = self.prepare_plan_and_risk()
        before = get_order_state(self.store, self.customer_id, plan["order_ref"])
        with self.assertRaises(ToolError) as error:
            execute_rebooking(
                self.store,
                self.case_id,
                plan["resolution_plan_id"],
                risk["risk_decision_id"],
                "NO-CONFIRMATION",
            )
        self.assertEqual(error.exception.code, "CUSTOMER_CONFIRMATION_REQUIRED")
        after = get_order_state(self.store, self.customer_id, plan["order_ref"])
        self.assertEqual(before, after)

    def test_cross_customer_case_cannot_confirm_another_customers_plan(self):
        plan, _ = self.prepare_plan_and_risk()
        other_match = resolve_order_reference(
            self.store,
            "C002",
            {
                "hotel_name": "上海虹桥海湾花园酒店",
                "check_in_date": "2026-08-15",
            },
        )
        other_plan = copy.deepcopy(plan)
        other_plan.update(
            {
                "resolution_plan_id": "PLAN-C002-001",
                "order_ref": other_match["order_ref"],
                "order_id": "H-C002-001",
            }
        )
        self.store["resolution_plans"][other_plan["resolution_plan_id"]] = other_plan
        other_risk = evaluate_rebooking(
            self.store,
            "C002",
            other_match["order_ref"],
            other_plan,
        )

        with self.assertRaises(ToolError) as error:
            record_customer_confirmation(
                self.store,
                self.case_id,
                other_plan["resolution_plan_id"],
                other_risk["risk_decision_id"],
                "MSG-CROSS-CUSTOMER",
            )
        self.assertEqual(error.exception.code, "ORDER_ACCESS_DENIED")
        self.assertEqual(self.store["confirmations"], {})

    def test_800_cny_difference_requires_internal_approval_and_blocks_write(self):
        plan, risk = self.prepare_plan_and_risk(800)
        self.assertEqual(risk["decision"], "REQUIRE_INTERNAL_APPROVAL")
        with self.assertRaises(ToolError) as error:
            execute_rebooking(
                self.store,
                self.case_id,
                plan["resolution_plan_id"],
                risk["risk_decision_id"],
                "NEEDS-APPROVAL",
            )
        self.assertEqual(error.exception.code, "INTERNAL_APPROVAL_REQUIRED")
        order = get_order_state(self.store, self.customer_id, plan["order_ref"])
        self.assertEqual(order["status"], "CONFIRMED")

    def test_false_success_is_caught_by_independent_verification(self):
        plan, risk = self.prepare_plan_and_risk()
        record_customer_confirmation(
            self.store,
            self.case_id,
            plan["resolution_plan_id"],
            risk["risk_decision_id"],
            "MSG-003",
        )
        self.store["fault_injection"]["execute_success_without_update"] = True
        execution = execute_rebooking(
            self.store,
            self.case_id,
            plan["resolution_plan_id"],
            risk["risk_decision_id"],
            "FALSE-SUCCESS",
        )
        self.assertEqual(execution["reported_status"], "SUCCESS")
        verification = verify_rebooking(
            self.store,
            self.customer_id,
            plan,
            "FALSE-SUCCESS",
        )
        self.assertEqual(verification["verification_status"], "FAILED")
        self.assertIn("order_status_matches", verification["differences"])
        self.assertIn("confirmation_number_exists", verification["differences"])

    def test_execute_is_idempotent(self):
        plan, risk = self.prepare_plan_and_risk()
        record_customer_confirmation(
            self.store,
            self.case_id,
            plan["resolution_plan_id"],
            risk["risk_decision_id"],
            "MSG-003",
        )
        first = execute_rebooking(
            self.store,
            self.case_id,
            plan["resolution_plan_id"],
            risk["risk_decision_id"],
            "IDEMPOTENT-KEY",
        )
        price_after_first = get_order_state(
            self.store,
            self.customer_id,
            plan["order_ref"],
        )["total_price_cny"]
        second = execute_rebooking(
            self.store,
            self.case_id,
            plan["resolution_plan_id"],
            risk["risk_decision_id"],
            "IDEMPOTENT-KEY",
        )
        price_after_second = get_order_state(
            self.store,
            self.customer_id,
            plan["order_ref"],
        )["total_price_cny"]
        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(second["idempotent_replay"])
        self.assertEqual(price_after_first, price_after_second)

    def test_idempotency_key_cannot_be_reused_for_a_different_request(self):
        plan, risk = self.prepare_plan_and_risk()
        record_customer_confirmation(
            self.store,
            self.case_id,
            plan["resolution_plan_id"],
            risk["risk_decision_id"],
            "MSG-003",
        )
        execute_rebooking(
            self.store,
            self.case_id,
            plan["resolution_plan_id"],
            risk["risk_decision_id"],
            "SHARED-IDEMPOTENCY-KEY",
        )
        record = self.store["execution_records"]["SHARED-IDEMPOTENCY-KEY"]
        self.assertEqual(record["case_id"], self.case_id)
        self.assertEqual(record["resolution_plan_id"], plan["resolution_plan_id"])
        self.assertEqual(record["risk_decision_id"], risk["risk_decision_id"])

        with self.assertRaises(ToolError) as error:
            execute_rebooking(
                self.store,
                "CASE-OTHER-001",
                plan["resolution_plan_id"],
                risk["risk_decision_id"],
                "SHARED-IDEMPOTENCY-KEY",
            )
        self.assertEqual(error.exception.code, "IDEMPOTENCY_KEY_CONFLICT")


if __name__ == "__main__":
    unittest.main()
