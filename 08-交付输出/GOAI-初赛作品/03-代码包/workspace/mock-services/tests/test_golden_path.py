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
    record_internal_decision,
    record_customer_confirmation,
    resolve_order_reference,
    validate_execution_authorization,
    verify_rebooking,
)
from run_golden_path import run_golden_path  # noqa: E402
from case_control import CaseStore  # noqa: E402
from linked_journey import LinkedJourney  # noqa: E402
from verification_package import verify_package_hash  # noqa: E402


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
            self.assertTrue(result["verification_package_hash_valid"])
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
                "ORDER_LINKED_HANDOFF",
                "RISK_EVALUATED",
                "RESOLUTION_PLAN_HANDOFF",
                "CUSTOMER_CONFIRMATION_RECORDED",
                "EXECUTION_AUTHORIZED",
                "REBOOKING_EXECUTED",
                "ORDER_STATE_READ",
                "VERIFICATION_PACKAGE_FROZEN",
                "VERIFICATION_PASSED",
                "VERIFICATION_PACKAGE_VERIFIED",
                "CUSTOMER_NOTIFIED",
                "CASE_RESOLVED",
                "CASE_CARD_WRITTEN",
            ):
                self.assertIn(required_event, event_types)

            actors_by_event = {event["event_type"]: event["actor"] for event in events}
            self.assertEqual(actors_by_event["ORDER_LINKED_HANDOFF"], "Frontline Agent")
            self.assertEqual(actors_by_event["RESOLUTION_PLAN_HANDOFF"], "Resolution Agent")
            self.assertEqual(actors_by_event["VERIFICATION_PACKAGE_FROZEN"], "Manager Agent")
            self.assertEqual(actors_by_event["VERIFICATION_PACKAGE_VERIFIED"], "Verification Agent")
            self.assertEqual(actors_by_event["CUSTOMER_NOTIFIED"], "Frontline Agent")
            self.assertEqual(actors_by_event["CASE_RESOLVED"], "Manager Agent")

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

    def test_approved_internal_decision_requires_customer_confirmation(self):
        plan, risk = self.prepare_plan_and_risk(800)
        decision = record_internal_decision(
            self.store,
            self.case_id,
            plan["resolution_plan_id"],
            risk["risk_decision_id"],
            "APPROVE",
            "MSG-OPS-APPROVE",
            "hotel-operations-001",
        )
        self.assertEqual(decision["decision"], "APPROVE")
        self.assertEqual(decision["case_id"], self.case_id)
        self.assertTrue(decision["recorded_at"])
        with self.assertRaises(ToolError) as error:
            validate_execution_authorization(
                self.store, self.case_id, plan["resolution_plan_id"], risk["risk_decision_id"]
            )
        self.assertEqual(error.exception.code, "CUSTOMER_CONFIRMATION_REQUIRED")
        record_customer_confirmation(
            self.store, self.case_id, plan["resolution_plan_id"], risk["risk_decision_id"], "MSG-CUSTOMER-APPROVE"
        )
        self.assertTrue(validate_execution_authorization(
            self.store, self.case_id, plan["resolution_plan_id"], risk["risk_decision_id"]
        )["execution_enabled"])
        execute_rebooking(
            self.store,
            self.case_id,
            plan["resolution_plan_id"],
            risk["risk_decision_id"],
            "HIGH-RISK-APPROVE",
        )
        self.assertEqual(
            get_order_state(self.store, self.customer_id, plan["order_ref"])["status"],
            "REBOOKED",
        )

    def test_rejected_internal_decision_blocks_authorization_and_conflicts_on_change(self):
        plan, risk = self.prepare_plan_and_risk(800)
        decision = record_internal_decision(
            self.store,
            self.case_id,
            plan["resolution_plan_id"],
            risk["risk_decision_id"],
            "REJECT",
            "MSG-OPS-REJECT",
            "hotel-operations-001",
        )
        self.assertEqual(decision["decision"], "REJECT")
        with self.assertRaises(ToolError) as error:
            validate_execution_authorization(
                self.store,
                self.case_id,
                plan["resolution_plan_id"],
                risk["risk_decision_id"],
            )
        self.assertEqual(error.exception.code, "INTERNAL_APPROVAL_REJECTED")
        with self.assertRaises(ToolError) as error:
            record_internal_decision(
                self.store,
                self.case_id,
                plan["resolution_plan_id"],
                risk["risk_decision_id"],
                "APPROVE",
                "MSG-OPS-APPROVE",
                "hotel-operations-001",
            )
        self.assertEqual(error.exception.code, "INTERNAL_DECISION_CONFLICT")

    def test_internal_decision_rejects_invalid_decision_and_context(self):
        plan, risk = self.prepare_plan_and_risk(800)
        with self.assertRaises(ToolError) as error:
            record_internal_decision(
                self.store,
                self.case_id,
                plan["resolution_plan_id"],
                risk["risk_decision_id"],
                "ESCALATE",
                "MSG-OPS-INVALID",
                "hotel-operations-001",
            )
        self.assertEqual(error.exception.code, "INVALID_INTERNAL_DECISION")
        low_risk_plan, low_risk = self.prepare_plan_and_risk(180)
        with self.assertRaises(ToolError) as error:
            record_internal_decision(
                self.store,
                self.case_id,
                low_risk_plan["resolution_plan_id"],
                low_risk["risk_decision_id"],
                "APPROVE",
                "MSG-OPS-LOW-RISK",
                "hotel-operations-001",
            )
        self.assertEqual(error.exception.code, "INTERNAL_DECISION_CONTEXT_INVALID")

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

    def _prepare_second_incident(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        store = load_fixture(FIXTURE)
        journey = LinkedJourney(store, CaseStore(Path(directory.name) / "cases.json"))
        journey.start("proj-1", "!room-1", "2026-08-14T09:00:00+08:00")
        journey.link_order(
            {
                "hotel_name": "上海虹桥海湾花园酒店",
                "check_in_date": "2026-08-15",
            },
            "2026-08-14T09:01:00+08:00",
        )
        first_plan, first_risk = journey.prepare_resolution()
        journey.route_risk(first_risk, "2026-08-14T09:02:00+08:00")
        journey.request_customer_confirmation("2026-08-14T09:03:00+08:00")
        journey.confirm_customer(
            first_plan,
            first_risk,
            "MSG-CUSTOMER-1",
            "2026-08-14T09:04:00+08:00",
            "2026-08-14T09:04:00+08:00",
        )
        first_execution, first_verification = journey.execute_and_verify(
            first_plan,
            first_risk,
            "CASE-INCIDENT-1",
            "2026-08-14T09:05:00+08:00",
        )
        journey.notify_customer("2026-08-14T09:06:00+08:00")
        journey.recur_supplier_exception("SUP-EX-002", "2026-08-15T10:00:00+08:00")
        second_plan, second_risk = journey.prepare_resolution()
        return (
            store,
            journey,
            (first_plan, first_risk, first_execution, first_verification),
            (second_plan, second_risk),
        )

    def test_supplier_recurrence_reopens_same_case_and_room(self):
        store, _, _, (plan, risk) = self._prepare_second_incident()
        case = store["cases"][store["case_id"]]
        self.assertEqual(case["case_id"], store["case_id"])
        self.assertEqual(case["incident_sequence"], 2)
        self.assertEqual((case["project_id"], case["project_room_id"]), ("proj-1", "!room-1"))
        self.assertEqual(plan["evidence_ids"], ["SUP-EX-002"])
        self.assertEqual(plan["replacement_hotel_id"], "HTL-SHA-RIVERSIDE")
        self.assertEqual(plan["price_difference_cny"], 800)
        self.assertEqual(risk["required_controls"], ["INTERNAL_APPROVAL", "CUSTOMER_CONFIRMATION"])

    def test_high_risk_execution_requires_internal_and_customer_confirmation(self):
        store, journey, _, (plan, risk) = self._prepare_second_incident()
        journey.route_risk(risk, "2026-08-15T10:01:00+08:00")
        with self.assertRaises(ToolError) as missing_approval:
            execute_rebooking(store, journey.case_id, plan["resolution_plan_id"], risk["risk_decision_id"], "CASE-INCIDENT-2")
        self.assertEqual(missing_approval.exception.code, "INTERNAL_APPROVAL_REQUIRED")
        journey.approve_internal(
            plan, risk, "OPS-2", "hotel-operations-demo", "2026-08-15T10:02:00+08:00"
        )
        with self.assertRaises(ToolError) as missing_confirmation:
            execute_rebooking(store, journey.case_id, plan["resolution_plan_id"], risk["risk_decision_id"], "CASE-INCIDENT-2")
        self.assertEqual(missing_confirmation.exception.code, "CUSTOMER_CONFIRMATION_REQUIRED")
        journey.request_customer_confirmation("2026-08-15T10:03:00+08:00")
        journey.confirm_customer(
            plan,
            risk,
            "CUSTOMER-2",
            "2026-08-15T10:04:00+08:00",
            "2026-08-15T10:04:00+08:00",
        )
        execution, verification = journey.execute_and_verify(
            plan, risk, "CASE-INCIDENT-2", "2026-08-15T10:05:00+08:00"
        )
        self.assertEqual(execution["reported_status"], "SUCCESS")
        self.assertEqual(verification["verification_status"], "PASSED")

    def test_customer_confirmation_timeout_and_late_resume(self):
        store, journey, _, (plan, risk) = self._prepare_second_incident()
        journey.route_risk(risk, "2026-08-15T10:01:00+08:00")
        journey.approve_internal(
            plan, risk, "OPS-2", "hotel-operations-demo", "2026-08-15T10:02:00+08:00"
        )
        awaiting = journey.request_customer_confirmation("2026-08-15T10:04:00+08:00")
        self.assertEqual(awaiting["reply_deadline_at"], "2026-08-16T10:04:00+08:00")
        with self.assertRaisesRegex(ValueError, "deadline has not passed"):
            journey.timeout_customer_confirmation("2026-08-16T10:03:59+08:00")
        closed = journey.timeout_customer_confirmation("2026-08-16T10:04:00+08:00")
        self.assertEqual(closed["case_state"], "CLOSED_INCOMPLETE")
        reopened = journey.restore_late_confirmation(
            "2026-08-16T10:05:00+08:00", "2026-08-16T10:05:00+08:00"
        )
        self.assertEqual(reopened["case_state"], "AWAITING_CUSTOMER_CONFIRMATION")
        self.assertEqual((reopened["case_id"], reopened["project_id"], reopened["project_room_id"]), (store["case_id"], "proj-1", "!room-1"))
        journey.confirm_customer(
            plan,
            risk,
            "CUSTOMER-LATE-2",
            "2026-08-16T10:05:01+08:00",
            "2026-08-16T10:05:00+08:00",
        )
        execution, verification = journey.execute_and_verify(
            plan, risk, "CASE-INCIDENT-2-LATE", "2026-08-16T10:06:00+08:00"
        )
        self.assertEqual(execution["incident_sequence"], 2)
        self.assertEqual(verification["verification_status"], "PASSED")

    def test_second_execution_is_idempotent(self):
        store, journey, _, (plan, risk) = self._prepare_second_incident()
        journey.route_risk(risk, "2026-08-15T10:01:00+08:00")
        journey.approve_internal(plan, risk, "OPS-2", "hotel-operations-demo", "2026-08-15T10:02:00+08:00")
        journey.request_customer_confirmation("2026-08-15T10:03:00+08:00")
        journey.confirm_customer(plan, risk, "CUSTOMER-2", "2026-08-15T10:04:00+08:00", "2026-08-15T10:04:00+08:00")
        first, _ = journey.execute_and_verify(plan, risk, "CASE-INCIDENT-2", "2026-08-15T10:05:00+08:00")
        replay = execute_rebooking(store, journey.case_id, plan["resolution_plan_id"], risk["risk_decision_id"], "CASE-INCIDENT-2")
        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(len(store["execution_records"]), 2)

    def test_each_execution_requires_independent_verification(self):
        store, journey, first, (plan, risk) = self._prepare_second_incident()
        journey.route_risk(risk, "2026-08-15T10:01:00+08:00")
        journey.approve_internal(plan, risk, "OPS-2", "hotel-operations-demo", "2026-08-15T10:02:00+08:00")
        journey.request_customer_confirmation("2026-08-15T10:03:00+08:00")
        journey.confirm_customer(plan, risk, "CUSTOMER-2", "2026-08-15T10:04:00+08:00", "2026-08-15T10:04:00+08:00")
        _, second_verification = journey.execute_and_verify(
            plan, risk, "CASE-INCIDENT-2", "2026-08-15T10:05:00+08:00"
        )
        packages = list(store["verification_packages"].values())
        results = list(store["verification_results"].values())
        self.assertEqual(len(packages), 2)
        self.assertTrue(all(verify_package_hash(package) for package in packages))
        self.assertEqual({item["incident_sequence"] for item in packages}, {1, 2})
        self.assertEqual(len(results), 2)
        self.assertEqual({item["incident_sequence"] for item in results}, {1, 2})
        self.assertEqual(first[3]["verification_status"], "PASSED")
        self.assertEqual(second_verification["verification_status"], "PASSED")
        self.assertEqual(
            {item["execution_id"] for item in results},
            {item["execution_id"] for item in packages},
        )


if __name__ == "__main__":
    unittest.main()
