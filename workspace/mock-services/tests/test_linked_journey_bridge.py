from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conversation_store import ConversationStore
from demo_markers import MarkerError
from linked_journey_bridge import (
    AgentReply,
    BridgeError,
    EvidenceCollector,
    LinkedJourneyBridge,
    RoomMapping,
    validate_project_event,
    validate_verification_result,
)


class FakeTransport:
    def __init__(self) -> None:
        self.frontline_requests: list[dict] = []
        self.project_events: list[dict] = []
        self.operations: list[dict] = []
        self.verification_packages: list[dict] = []
        self.verification_matrix_id = "@verification:example.test"
        self.verification_sender = self.verification_matrix_id
        self.frontline_reply = {
            "event_type": "CUSTOMER_SAFE_REPLY",
            "case_id": "CASE-SMOKE-001",
            "conversation_id": "conversation-smoke-001",
            "message_type": "STATUS",
            "body": "我正在核对您的预订信息。",
        }

    def request_frontline(self, envelope: dict) -> AgentReply:
        self.frontline_requests.append(envelope)
        return AgentReply("$matrix-frontline-smoke", dict(self.frontline_reply))

    def publish_project_event(self, event: dict) -> str:
        self.project_events.append(event)
        return f"$matrix-project-smoke-{len(self.project_events)}"

    def route_operations(self, decision: dict) -> str:
        self.operations.append(decision)
        return "$matrix-operations-smoke"

    def route_verification(self, package: dict) -> str:
        self.verification_packages.append(package)
        return "$matrix-verification-smoke"

    def request_verification(self, package: dict) -> AgentReply:
        self.verification_packages.append(package)
        return AgentReply(
            "$matrix-verification-reply-smoke",
            {
                "event_type": "VERIFICATION_RESULT",
                "business_event_id": "BUS-SMOKE-VERIFICATION-1",
                "case_id": package["case_id"],
                "incident_sequence": 1,
                "sender_agent": "VERIFICATION",
                "verification_result_id": "VR-SMOKE-1",
                "verification_status": "PASSED",
                "evidence_ref": "verification-result://VR-SMOKE-1",
                "differences": [],
                "occurred_at": "2026-08-15T12:00:00+08:00",
            },
            self.verification_sender,
        )


def project_event(**overrides: object) -> dict:
    event = {
        "event_type": "ORDER_LINKED",
        "business_event_id": "BUS-SMOKE-ORDER-LINKED",
        "case_id": "CASE-SMOKE-001",
        "incident_sequence": 1,
        "state": "RESOLVING",
        "sender_agent": "FRONTLINE",
        "receiver": "RESOLUTION",
        "conclusion": "A customer-owned order was uniquely linked.",
        "next_action": "Investigate the synthetic supplier exception.",
        "evidence_ref": "order-ref://opaque-smoke-reference",
        "occurred_at": "2026-08-15T12:00:00+08:00",
    }
    event.update(overrides)
    return event


class LinkedJourneyBridgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.conversations = ConversationStore()
        self.conversations.create(
            "conversation-smoke-001",
            "CASE-SMOKE-001",
            "C001",
        )
        self.transport = FakeTransport()
        self.evidence = EvidenceCollector()
        self.bridge = LinkedJourneyBridge(
            conversations=self.conversations,
            transport=self.transport,
            room_mapping=RoomMapping(
                "proj-goai-case-golden-001",
                "!smoke-project-room:example.test",
                ("frontline", "resolution"),
            ),
            customer_id="C001",
            case_id="CASE-SMOKE-001",
            conversation_id="conversation-smoke-001",
            evidence=self.evidence,
        )

    def append_customer(self) -> dict:
        return self.conversations.append_customer(
            "conversation-smoke-001",
            "C001",
            "请帮我核对一笔测试预订。",
        )

    def test_customer_message_round_trip_projects_only_safe_frontline_reply(self):
        projected = self.bridge.forward_customer_message(self.append_customer())

        self.assertEqual(projected["sender"], "FRONTLINE")
        self.assertEqual(projected["body"], "我正在核对您的预订信息。")
        envelope = self.transport.frontline_requests[0]
        self.assertEqual(envelope["customer_id"], "C001")
        self.assertEqual(envelope["project_room_id"], "!smoke-project-room:example.test")
        visible = self.conversations.get("conversation-smoke-001", "C001")
        self.assertEqual(
            [message["sender"] for message in visible["messages"]],
            ["CUSTOMER", "FRONTLINE"],
        )

    def test_non_customer_message_cannot_enter_frontline(self):
        message = dict(self.append_customer(), sender="FRONTLINE")

        with self.assertRaisesRegex(BridgeError, "Only CUSTOMER"):
            self.bridge.forward_customer_message(message)
        self.assertEqual(self.transport.frontline_requests, [])

    def test_frontline_internal_content_is_not_projected(self):
        self.transport.frontline_reply["body"] = "MCP tool payload: order_ref=secret"

        with self.assertRaisesRegex(BridgeError, "forbidden content"):
            self.bridge.forward_customer_message(self.append_customer())

        visible = self.conversations.get("conversation-smoke-001", "C001")
        self.assertEqual(len(visible["messages"]), 1)

    def test_project_event_sender_is_bound_to_authenticated_agent(self):
        event_id = self.bridge.publish_project_event(
            project_event(),
            authenticated_agent="FRONTLINE",
        )
        self.assertEqual(event_id, "$matrix-project-smoke-1")

        with self.assertRaisesRegex(BridgeError, "authenticated Agent"):
            self.bridge.publish_project_event(
                project_event(sender_agent="RESOLUTION"),
                authenticated_agent="FRONTLINE",
            )

    def test_project_event_rejects_customer_identity_and_raw_payload_terms(self):
        with self.assertRaisesRegex(BridgeError, "forbidden content"):
            validate_project_event(
                project_event(conclusion="customer_id=C001"),
                case_id="CASE-SMOKE-001",
                sender_agent="FRONTLINE",
            )

    def test_operations_approval_and_verification_are_routed_by_case(self):
        operations_event = self.bridge.route_operations_approval(
            {
                "case_id": "CASE-SMOKE-001",
                "decision": "APPROVE",
                "message_event_id": "$matrix-approve-smoke",
                "operator_id": "operations-smoke",
            }
        )
        verification_event = self.bridge.route_verification(
            {
                "case_id": "CASE-SMOKE-001",
                "package_hash_valid": True,
                "package_hash": "sha256-smoke",
                "order_ref": "opaque-smoke-reference",
            }
        )

        self.assertEqual(operations_event, "$matrix-operations-smoke")
        self.assertEqual(verification_event, "$matrix-verification-smoke")
        self.assertEqual(self.transport.operations[0]["decision"], "APPROVE")
        self.assertTrue(self.transport.verification_packages[0]["package_hash_valid"])

    def test_verification_route_rejects_invalid_hash_and_execution_context(self):
        with self.assertRaisesRegex(BridgeError, "hash must be valid"):
            self.bridge.route_verification(
                {"case_id": "CASE-SMOKE-001", "package_hash_valid": False}
            )

    def test_verification_reply_requires_assigned_sender_and_matches_readback(self):
        package = {
            "case_id": "CASE-SMOKE-001",
            "package_hash_valid": True,
        }
        response = self.bridge.request_verification(
            package,
            incident_sequence=1,
            expected_result={"verification_status": "PASSED", "differences": []},
        )
        self.assertEqual(response.matrix_event_id, "$matrix-verification-reply-smoke")
        self.assertEqual(response.payload["verification_status"], "PASSED")

        self.transport.verification_sender = "@intruder:example.test"
        with self.assertRaisesRegex(BridgeError, "assigned Agent"):
            self.bridge.request_verification(
                package,
                incident_sequence=1,
                expected_result={"verification_status": "PASSED", "differences": []},
            )

    def test_verification_reply_status_mismatch_is_rejected(self):
        with self.assertRaisesRegex(BridgeError, "deterministic readback"):
            self.bridge.request_verification(
                {"case_id": "CASE-SMOKE-001", "package_hash_valid": True},
                incident_sequence=1,
                expected_result={
                    "verification_status": "FAILED",
                    "differences": ["order_status_matches"],
                },
            )
        with self.assertRaisesRegex(BridgeError, "forbidden field"):
            self.bridge.route_verification(
                {
                    "case_id": "CASE-SMOKE-001",
                    "package_hash_valid": True,
                    "nested": {"execution_response": {"status": "SUCCESS"}},
                }
            )

    def test_verification_result_binds_case_incident_status_and_evidence(self):
        valid = {
            "event_type": "VERIFICATION_RESULT",
            "business_event_id": "BUS-SMOKE-VERIFY-CONTRACT",
            "case_id": "CASE-SMOKE-001",
            "incident_sequence": 1,
            "sender_agent": "VERIFICATION",
            "verification_result_id": "VR-SMOKE-CONTRACT",
            "verification_status": "PASSED",
            "evidence_ref": "verification-result://VR-SMOKE-CONTRACT",
            "differences": [],
            "occurred_at": "2026-08-15T12:00:00+08:00",
        }
        self.assertEqual(
            validate_verification_result(
                valid,
                case_id="CASE-SMOKE-001",
                incident_sequence=1,
            )["verification_status"],
            "PASSED",
        )
        invalid = (
            (dict(valid, case_id="CASE-SMOKE-OTHER"), "different Case"),
            (dict(valid, incident_sequence=2), "different incident"),
            (dict(valid, verification_status="UNKNOWN"), "PASSED or FAILED"),
            (
                dict(valid, evidence_ref="verification-result://VR-SMOKE-OTHER"),
                "evidence",
            ),
        )
        for payload, message in invalid:
            with self.subTest(message=message):
                with self.assertRaisesRegex(BridgeError, message):
                    validate_verification_result(
                        payload,
                        case_id="CASE-SMOKE-001",
                        incident_sequence=1,
                    )

    def test_automatic_events_keep_the_same_case_and_room(self):
        recurrence = project_event(
            event_type="SUPPLIER_EXCEPTION_RECURRED",
            business_event_id="BUS-SMOKE-RECURRENCE",
            incident_sequence=2,
            state="RESOLVING",
            sender_agent="MANAGER",
            receiver="RESOLUTION",
            conclusion="A second synthetic supplier exception was accepted.",
            next_action="Prepare a second replacement plan.",
            evidence_ref="supplier-exception://synthetic-smoke-2",
        )
        timeout = project_event(
            event_type="CUSTOMER_CONFIRMATION_TIMEOUT",
            business_event_id="BUS-SMOKE-TIMEOUT",
            incident_sequence=2,
            state="CLOSED_INCOMPLETE",
            sender_agent="MANAGER",
            receiver="FRONTLINE",
            conclusion="The deterministic customer confirmation deadline elapsed.",
            next_action="Wait for a late reply on the same Case.",
            evidence_ref="case-timer://synthetic-smoke",
        )

        self.bridge.publish_automatic_event(recurrence)
        self.bridge.publish_automatic_event(timeout)

        self.assertEqual(
            {event["case_id"] for event in self.transport.project_events},
            {"CASE-SMOKE-001"},
        )
        self.assertEqual(self.bridge.room_mapping.project_room_id, "!smoke-project-room:example.test")

    def test_smoke_evidence_cannot_occupy_formal_marker_or_manifest(self):
        self.evidence.record_smoke("GATE2_SYNTHETIC", "$matrix-smoke")

        with self.assertRaisesRegex(MarkerError, "formal Demo marker"):
            self.evidence.record_smoke("DEMO_START", "$matrix-formal")
        with self.assertRaisesRegex(MarkerError, "Manifest is disabled"):
            self.evidence.manifest(2, 2, 2, "RESOLVED")

    def test_formal_room_mapping_is_loaded_from_existing_metadata(self):
        metadata = (
            Path(__file__).resolve().parents[2]
            / "runs"
            / "2026-08-14-project-room-migration"
            / "project-meta.json"
        )

        mapping = RoomMapping.from_project_meta(
            metadata,
            "proj-goai-case-golden-001",
        )

        self.assertEqual(mapping.project_id, "proj-goai-case-golden-001")
        self.assertEqual(
            mapping.project_room_id,
            "!tARkhuXsazrkPWbLfV:matrix-local.agentteams.io:18080",
        )
        self.assertEqual(mapping.workers, ("frontline", "resolution"))


if __name__ == "__main__":
    unittest.main()
