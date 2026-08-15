from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from case_control import CaseStore
from conversation_store import ConversationStore
from demo_markers import DemoMarkers, MARKERS, MarkerError, validate_manifest
from golden_path import load_fixture
from journey_orchestrator import JourneyOrchestrator
from linked_journey import LinkedJourney
from linked_journey_bridge import (
    AgentReply,
    EvidenceCollector,
    LinkedJourneyBridge,
    RoomMapping,
)


SERVICE_DIR = Path(__file__).resolve().parents[1]
FIXTURE = SERVICE_DIR / "fixtures" / "golden-case.json"


class FakeTransport:
    def __init__(self) -> None:
        self.project_events: list[dict] = []

    def request_frontline(self, envelope: dict) -> AgentReply:
        raise AssertionError("Frontline is not used by automatic journey events")

    def publish_project_event(self, event: dict) -> str:
        self.project_events.append(dict(event))
        return f"$matrix-smoke-{len(self.project_events)}"

    def route_operations(self, decision: dict) -> str:
        raise AssertionError("Operations is not used by automatic journey events")

    def route_verification(self, package: dict) -> str:
        raise AssertionError("Verification is not used by automatic journey events")


class JourneyOrchestratorTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = load_fixture(FIXTURE)
        self.store["case_id"] = "CASE-SMOKE-ORCHESTRATOR-001"
        self.store["cases"] = {}
        self.case_store = CaseStore(Path(directory.name) / "cases.json")
        self.journey = LinkedJourney(self.store, self.case_store)
        self.transport = FakeTransport()
        self.evidence = EvidenceCollector()
        conversations = ConversationStore()
        conversations.create(
            "conversation-smoke-orchestrator-001",
            self.journey.case_id,
            self.journey.customer_id,
        )
        self.bridge = LinkedJourneyBridge(
            conversations=conversations,
            transport=self.transport,
            room_mapping=RoomMapping(
                "proj-goai-case-golden-001",
                "!smoke-project-room:example.test",
                ("frontline", "resolution"),
            ),
            customer_id=self.journey.customer_id,
            case_id=self.journey.case_id,
            conversation_id="conversation-smoke-orchestrator-001",
            evidence=self.evidence,
        )
        self.orchestrator = JourneyOrchestrator(self.journey, self.bridge)
        self._complete_first_incident()

    def _complete_first_incident(self) -> None:
        self.journey.start(
            "proj-goai-case-golden-001",
            "!smoke-project-room:example.test",
            "2026-08-14T09:00:00+08:00",
        )
        self.journey.link_order(
            {
                "hotel_name": "上海虹桥海湾花园酒店",
                "check_in_date": "2026-08-15",
            },
            "2026-08-14T09:01:00+08:00",
        )
        plan, risk = self.journey.prepare_resolution()
        self.journey.route_risk(risk, "2026-08-14T09:02:00+08:00")
        self.journey.request_customer_confirmation("2026-08-14T09:03:00+08:00")
        self.journey.confirm_customer(
            plan,
            risk,
            "$customer-smoke-1",
            "2026-08-14T09:04:00+08:00",
            "2026-08-14T09:04:00+08:00",
        )
        self.journey.execute_and_verify(
            plan,
            risk,
            "CASE-SMOKE-EXECUTION-1",
            "2026-08-14T09:05:00+08:00",
        )
        self.journey.notify_customer("2026-08-14T09:06:00+08:00")

    def test_second_exception_and_timeout_advance_without_human_input(self) -> None:
        recurrence = self.orchestrator.advance_second_exception(
            "SUP-EX-002",
            "2026-08-15T10:00:00+08:00",
        )
        self.assertEqual(recurrence["case"]["incident_sequence"], 2)
        self.assertEqual(recurrence["case"]["case_state"], "RESOLVING")

        plan, risk = self.journey.prepare_resolution()
        self.journey.route_risk(risk, "2026-08-15T10:01:00+08:00")
        self.journey.approve_internal(
            plan,
            risk,
            "$operations-smoke-reject-free",
            "operations-smoke",
            "2026-08-15T10:02:00+08:00",
        )
        awaiting = self.journey.request_customer_confirmation(
            "2026-08-15T10:04:00+08:00"
        )
        timeout = self.orchestrator.simulate_customer_confirmation_timeout(
            awaiting["reply_deadline_at"]
        )

        self.assertEqual(timeout["case"]["case_state"], "CLOSED_INCOMPLETE")
        self.assertEqual(
            [event["event_type"] for event in self.transport.project_events],
            ["SUPPLIER_EXCEPTION_RECURRED", "CUSTOMER_CONFIRMATION_TIMEOUT"],
        )
        self.assertEqual(
            {event["case_id"] for event in self.transport.project_events},
            {"CASE-SMOKE-ORCHESTRATOR-001"},
        )

    def test_prep_mode_cannot_record_formal_markers_or_manifest(self) -> None:
        with self.assertRaisesRegex(MarkerError, "disabled"):
            self.evidence.record_formal(
                "DEMO_START",
                "$matrix-smoke-formal",
                "BUS-SMOKE-FORMAL",
            )
        with self.assertRaisesRegex(MarkerError, "disabled"):
            self.evidence.manifest(2, 2, 2, "RESOLVED")

    def test_armed_mode_can_generate_a_complete_synthetic_manifest(self) -> None:
        markers = DemoMarkers(
            "RUN-SYNTHETIC-ARMED-001",
            "CASE-SMOKE-ORCHESTRATOR-001",
            "!smoke-project-room:example.test",
            "conversation-smoke-orchestrator-001",
        )
        collector = EvidenceCollector(markers)
        for index, marker in enumerate(MARKERS, start=1):
            collector.record_formal(
                marker,
                f"$matrix-synthetic-{index}",
                f"BUS-SYNTHETIC-{index}",
                f"2026-08-15T12:0{index}:00+08:00",
            )

        manifest = collector.manifest(2, 2, 2, "RESOLVED")

        self.assertTrue(validate_manifest(manifest))
        self.assertEqual(manifest["run_id"], "RUN-SYNTHETIC-ARMED-001")


if __name__ == "__main__":
    unittest.main()
