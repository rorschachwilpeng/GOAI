"""Tests for the persisted Case state and Project Room binding."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

from case_control import CaseStore, CaseTransitionError  # noqa: E402


class CaseStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "cases.json"
        self.store = CaseStore(self.path)
        self.case = self.store.create_case(
            "CASE-001",
            "C001",
            "proj-goai-case-001",
            "!case-001:example.test",
            "2026-08-14T09:00:00+08:00",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_case_persists_received_case_atomically(self) -> None:
        self.assertEqual(self.case["case_state"], "RECEIVED")
        self.assertEqual(self.store.get_case("CASE-001"), self.case)
        self.assertTrue(self.path.is_file())
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_allows_the_golden_path_state_transitions(self) -> None:
        for event in (
            "CASE_CREATED",
            "ORDER_LINKED",
            "RISK_REQUIRES_CUSTOMER_CONFIRMATION",
            "CUSTOMER_CONFIRMED",
            "REBOOKING_ATTEMPTED",
            "VERIFICATION_PASSED",
            "CUSTOMER_NOTIFIED",
        ):
            self.case = self.store.apply_event(
                "CASE-001", event, "2026-08-14T09:01:00+08:00"
            )
        self.assertEqual(self.case["case_state"], "RESOLVED")

    def test_rejects_an_illegal_state_transition(self) -> None:
        with self.assertRaises(CaseTransitionError):
            self.store.apply_event(
                "CASE-001", "CUSTOMER_CONFIRMED", "2026-08-14T09:01:00+08:00"
            )

    def test_case_room_binding_is_immutable_and_reused_when_reopened(self) -> None:
        self.store.apply_event("CASE-001", "CASE_CREATED", "2026-08-14T09:01:00+08:00")
        self.store.apply_event(
            "CASE-001", "CUSTOMER_INFO_REQUESTED", "2026-08-14T09:02:00+08:00"
        )
        self.store.apply_event(
            "CASE-001", "CUSTOMER_INFO_TIMEOUT", "2026-08-15T09:02:01+08:00"
        )
        reopened = self.store.apply_event(
            "CASE-001",
            "CASE_REOPENED",
            "2026-08-15T10:00:00+08:00",
            project_id="proj-goai-case-001",
            project_room_id="!case-001:example.test",
        )
        self.assertEqual(reopened["case_state"], "IDENTIFYING_ORDER")
        self.assertEqual(reopened["reopened_count"], 1)
        self.assertEqual(reopened["project_room_id"], "!case-001:example.test")

        self.store.apply_event(
            "CASE-001", "CUSTOMER_INFO_REQUESTED", "2026-08-15T10:01:00+08:00"
        )
        self.store.apply_event(
            "CASE-001", "CUSTOMER_INFO_TIMEOUT", "2026-08-16T10:01:01+08:00"
        )
        with self.assertRaises(CaseTransitionError):
            self.store.apply_event(
                "CASE-001",
                "CASE_REOPENED",
                "2026-08-16T11:00:00+08:00",
                project_room_id="!another-room:example.test",
            )

    def test_customer_info_deadline_uses_matrix_arrival_time(self) -> None:
        self.store.apply_event("CASE-001", "CASE_CREATED", "2026-08-14T09:00:00+08:00")
        awaiting = self.store.apply_event(
            "CASE-001", "CUSTOMER_INFO_REQUESTED", "2026-08-14T09:02:00+08:00"
        )
        self.assertEqual(awaiting["reply_deadline_at"], "2026-08-15T09:02:00+08:00")
        self.assertTrue(awaiting["background_tasks_active"])

        continued = self.store.apply_event(
            "CASE-001",
            "CUSTOMER_INFO_RECEIVED",
            "2026-08-16T09:02:00+08:00",
            matrix_arrival_at="2026-08-15T09:01:59+08:00",
        )
        self.assertEqual(continued["case_state"], "IDENTIFYING_ORDER")

        self.store.create_case(
            "CASE-002", "C001", "proj-goai-case-002", "!case-002:example.test", "2026-08-14T09:00:00+08:00"
        )
        self.store.apply_event("CASE-002", "CASE_CREATED", "2026-08-14T09:00:00+08:00")
        self.store.apply_event(
            "CASE-002", "CUSTOMER_INFO_REQUESTED", "2026-08-14T09:02:00+08:00"
        )
        at_deadline = self.store.apply_event(
            "CASE-002",
            "CUSTOMER_INFO_RECEIVED",
            "2026-08-16T09:02:00+08:00",
            matrix_arrival_at="2026-08-15T09:02:00+08:00",
        )
        self.assertEqual(at_deadline["case_state"], "IDENTIFYING_ORDER")

    def test_timeout_closes_and_late_reply_reopens_original_case(self) -> None:
        self.store.apply_event("CASE-001", "CASE_CREATED", "2026-08-14T09:00:00+08:00")
        before_timeout = self.store.apply_event(
            "CASE-001", "CUSTOMER_INFO_REQUESTED", "2026-08-14T09:02:00+08:00"
        )
        closed = self.store.apply_event(
            "CASE-001", "CUSTOMER_INFO_TIMEOUT", "2026-08-15T09:02:01+08:00"
        )
        self.assertEqual(closed["case_state"], "CLOSED_INCOMPLETE")
        self.assertFalse(closed["background_tasks_active"])

        reopened = self.store.apply_event(
            "CASE-001",
            "CASE_REOPENED",
            "2026-08-15T10:00:00+08:00",
            matrix_arrival_at="2026-08-15T09:02:01+08:00",
            customer_id="C001",
        )
        self.assertEqual(reopened["case_state"], "IDENTIFYING_ORDER")
        self.assertEqual(reopened["reopened_count"], 1)
        self.assertEqual(reopened["case_id"], before_timeout["case_id"])
        self.assertEqual(reopened["project_id"], before_timeout["project_id"])
        self.assertEqual(reopened["project_room_id"], before_timeout["project_room_id"])
        self.assertEqual(len(self.store._read()), 1)

    def test_late_customer_message_cannot_continue_stopped_case(self) -> None:
        self.store.apply_event("CASE-001", "CASE_CREATED", "2026-08-14T09:00:00+08:00")
        self.store.apply_event(
            "CASE-001", "CUSTOMER_INFO_REQUESTED", "2026-08-14T09:02:00+08:00"
        )
        self.store.apply_event(
            "CASE-001", "CUSTOMER_INFO_TIMEOUT", "2026-08-15T09:02:01+08:00"
        )
        with self.assertRaises(CaseTransitionError):
            self.store.apply_event(
                "CASE-001",
                "CUSTOMER_INFO_RECEIVED",
                "2026-08-15T09:03:00+08:00",
                matrix_arrival_at="2026-08-15T09:02:01+08:00",
            )

    def test_arrival_after_deadline_cannot_continue_waiting_case(self) -> None:
        self.store.apply_event("CASE-001", "CASE_CREATED", "2026-08-14T09:00:00+08:00")
        self.store.apply_event(
            "CASE-001", "CUSTOMER_INFO_REQUESTED", "2026-08-14T09:02:00+08:00"
        )
        with self.assertRaises(CaseTransitionError):
            self.store.apply_event(
                "CASE-001",
                "CUSTOMER_INFO_RECEIVED",
                "2026-08-15T09:03:00+08:00",
                matrix_arrival_at="2026-08-15T09:02:01+08:00",
            )

    def test_resolved_case_reopens_without_new_project_room(self) -> None:
        for event in (
            "CASE_CREATED",
            "ORDER_LINKED",
            "RISK_REQUIRES_CUSTOMER_CONFIRMATION",
            "CUSTOMER_CONFIRMED",
            "REBOOKING_ATTEMPTED",
            "VERIFICATION_PASSED",
            "CUSTOMER_NOTIFIED",
        ):
            self.store.apply_event("CASE-001", event, "2026-08-14T09:01:00+08:00")
        reopened = self.store.apply_event(
            "CASE-001", "CASE_REOPENED", "2026-08-14T10:00:00+08:00", customer_id="C001"
        )
        self.assertEqual(reopened["case_state"], "IDENTIFYING_ORDER")
        self.assertEqual(reopened["reopened_count"], 1)
        self.assertEqual(reopened["project_id"], "proj-goai-case-001")
        self.assertEqual(reopened["project_room_id"], "!case-001:example.test")
