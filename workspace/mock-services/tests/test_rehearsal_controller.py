from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from case_control import CaseStore
from conversation_store import ConversationStore
from demo_markers import DemoMarkers, validate_manifest
from golden_path import load_fixture
from journey_orchestrator import JourneyOrchestrator
from linked_journey import LinkedJourney
from linked_journey_bridge import AgentReply, EvidenceCollector, LinkedJourneyBridge, RoomMapping
from rehearsal_controller import RehearsalController


class FakeTransport:
    def __init__(self) -> None:
        self.frontline_requests: list[dict] = []
        self.frontline_project_events: list[dict] = []
        self.resolution_project_events: list[dict] = []
        self.manager_project_events: list[dict] = []
        self.operations_requests: list[dict] = []
        self.operations_routes: list[dict] = []
        self.verification_routes: list[dict] = []
        self.verification_replies: list[AgentReply] = []
        self.verification_matrix_id = "@verification:example.test"
        self.verification_mode = "PASSED"
        self.verification_differences: list[str] | None = None
        self.verification_request_hook = None
        self.next_operations_decision: dict | None = None
        self._sequence = 0

    def _event_id(self, label: str) -> str:
        self._sequence += 1
        return f"$smoke-{label}-{self._sequence}"

    def request_frontline(self, envelope: dict) -> AgentReply:
        self.frontline_requests.append(dict(envelope))
        body = "Synthetic customer-safe Frontline response."
        return AgentReply(
            self._event_id("frontline"),
            {
                "event_type": "CUSTOMER_SAFE_REPLY",
                "case_id": envelope["case_id"],
                "conversation_id": envelope["conversation_id"],
                "message_type": "STATUS",
                "body": body,
            },
        )

    def request_frontline_project_handoff(self, event: dict) -> dict:
        self.frontline_project_events.append(dict(event))
        return {"matrix_event_id": self._event_id("frontline-project"), "payload": event}

    def request_resolution_project_update(
        self,
        event: dict,
        source_event_id: str,
    ) -> dict:
        self.resolution_project_events.append(
            {"event": dict(event), "source_event_id": source_event_id}
        )
        return {"matrix_event_id": self._event_id("resolution-project"), "payload": event}

    def wait_resolution_project_update(
        self,
        event: dict,
        source_event_id: str,
    ) -> dict:
        return self.request_resolution_project_update(event, source_event_id)

    def publish_project_event(self, event: dict) -> str:
        self.manager_project_events.append(dict(event))
        return self._event_id("manager-project")

    def request_operations_review(self, request: dict) -> dict:
        self.operations_requests.append(dict(request))
        return {"matrix_event_id": self._event_id("operations-request"), "after_ms": 1}

    def request_resolution_operations_summary(
        self,
        event: dict,
        source_event_id: str,
    ) -> dict:
        return self.request_resolution_project_update(event, source_event_id)

    def poll_operations_decision(self, after_ms: int) -> dict | None:
        decision = self.next_operations_decision
        self.next_operations_decision = None
        return decision

    def route_operations(self, decision: dict) -> str:
        self.operations_routes.append(dict(decision))
        return self._event_id("operations-route")

    def route_verification(self, package: dict) -> str:
        self.verification_routes.append(dict(package))
        return self._event_id("verification-route")

    def request_verification(self, package: dict) -> AgentReply:
        self.verification_routes.append(dict(package))
        if self.verification_request_hook is not None:
            self.verification_request_hook()
        if self.verification_mode == "TIMEOUT":
            raise RuntimeError("synthetic Verification timeout")
        status = self.verification_mode
        differences = (
            list(self.verification_differences)
            if self.verification_differences is not None
            else ([] if status == "PASSED" else ["order_status_matches"])
        )
        result_id = f"VR-SMOKE-{len(self.verification_routes)}"
        reply = AgentReply(
            self._event_id("verification-reply"),
            {
                "event_type": "VERIFICATION_RESULT",
                "business_event_id": f"BUS-{result_id}",
                "case_id": package["case_id"],
                "incident_sequence": package["resolution_plan"]["incident_sequence"],
                "sender_agent": "VERIFICATION",
                "verification_result_id": result_id,
                "verification_status": status,
                "evidence_ref": f"verification-result://{result_id}",
                "differences": differences,
                "occurred_at": "2026-08-15T12:00:00+08:00",
            },
            self.verification_matrix_id,
        )
        self.verification_replies.append(reply)
        return reply


class FakeBusinessAPI:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def call_business_tool(self, path: str, payload: dict) -> dict:
        self.calls.append((path, dict(payload)))
        if path == "/resolve-order-reference":
            return {
                "status": "UNIQUE",
                "order_ref": "oref_29b6d09964387d23",
            }
        if path == "/evaluate-rebooking":
            plan = payload["resolution_plan"]
            decision = (
                "REQUIRE_CUSTOMER_CONFIRMATION"
                if plan["price_difference_cny"] == 180
                else "REQUIRE_INTERNAL_APPROVAL"
            )
            return {
                "risk_decision_id": f"RISK-{plan['resolution_plan_id']}",
                "decision": decision,
            }
        if path == "/record-customer-confirmation":
            return {"confirmed": True}
        if path == "/record-internal-decision":
            return {"decision": payload["decision"]}
        if path == "/validate-execution-authorization":
            return {"authorized": True}
        if path == "/execute-rebooking":
            return {"reported_status": "SUCCESS"}
        raise AssertionError(f"Unexpected business path: {path}")

class RehearsalControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.state_path = root / "controller.json"
        self.case_path = root / "cases.json"
        self.conversations = ConversationStore()
        self.transport = FakeTransport()
        self.case_id = "CASE-SMOKE-CONTROLLER-001"
        self.conversation_id = "conversation-smoke-controller-001"
        self.mapping = RoomMapping(
            "proj-goai-case-golden-001",
            "!smoke-project-room:example.test",
            ("frontline", "resolution"),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_controller(
        self,
        *,
        armed: bool = False,
        business_api=None,
    ) -> RehearsalController:
        store = load_fixture(
            Path(__file__).resolve().parents[1] / "fixtures" / "golden-case.json"
        )
        store["case_id"] = self.case_id
        store["cases"] = {}
        journey = LinkedJourney(store, CaseStore(self.case_path))
        markers = (
            DemoMarkers(
                "RUN-SMOKE-CONTROLLER-001",
                self.case_id,
                self.mapping.project_room_id,
                self.conversation_id,
            )
            if armed
            else None
        )
        bridge = LinkedJourneyBridge(
            conversations=self.conversations,
            transport=self.transport,
            room_mapping=self.mapping,
            customer_id="C001",
            case_id=self.case_id,
            conversation_id=self.conversation_id,
            evidence=EvidenceCollector(markers),
        )
        return RehearsalController(
            projection=self.conversations,
            transport=self.transport,
            bridge=bridge,
            journey=journey,
            orchestrator=JourneyOrchestrator(journey, bridge),
            state_path=self.state_path,
            timeout_delay_seconds=5,
            business_api=business_api,
        )

    def restore_controller(self) -> RehearsalController:
        restored = json.loads(self.state_path.read_text(encoding="utf-8"))
        journey = LinkedJourney(restored["business_store"], CaseStore(self.case_path))
        bridge = LinkedJourneyBridge(
            conversations=self.conversations,
            transport=self.transport,
            room_mapping=self.mapping,
            customer_id="C001",
            case_id=self.case_id,
            conversation_id=self.conversation_id,
            evidence=EvidenceCollector(),
        )
        return RehearsalController(
            projection=self.conversations,
            transport=self.transport,
            bridge=bridge,
            journey=journey,
            orchestrator=JourneyOrchestrator(journey, bridge),
            state_path=self.state_path,
            timeout_delay_seconds=5,
            restored_state=restored,
        )

    def append_customer(self, body: str) -> dict:
        return self.conversations.append_customer(
            self.conversation_id,
            "C001",
            body,
        )

    def approve(self) -> None:
        self.transport.next_operations_decision = {
            "decision": "APPROVE",
            "message_event_id": "$smoke-operations-approval",
            "operator_id": "operations-smoke",
        }

    def run_complete_journey(self, controller: RehearsalController) -> None:
        controller.initialize()
        self.append_customer("Synthetic initial customer message.")
        self.assertEqual(controller.poll_once(now_epoch=10), 1)
        self.append_customer("Synthetic hotel and date clues.")
        self.assertEqual(controller.poll_once(now_epoch=20), 1)
        self.append_customer("Synthetic first plan confirmation.")
        self.assertEqual(controller.poll_once(now_epoch=30), 1)
        self.approve()
        self.assertEqual(controller.poll_once(now_epoch=40), 1)
        self.assertEqual(controller.poll_once(now_epoch=46), 1)
        self.append_customer("Synthetic late second plan confirmation.")
        self.assertEqual(controller.poll_once(now_epoch=50), 1)

    def advance_to_operations(self, controller: RehearsalController) -> None:
        controller.initialize()
        self.append_customer("Synthetic initial customer message.")
        controller.poll_once(now_epoch=10)
        self.append_customer("Synthetic hotel and date clues.")
        controller.poll_once(now_epoch=20)
        self.append_customer("Synthetic first plan confirmation.")
        controller.poll_once(now_epoch=30)

    def test_starts_idle_and_sends_nothing_until_customer_message(self):
        controller = self.make_controller()

        status = controller.initialize()
        handled = controller.poll_once(now_epoch=0)

        self.assertEqual(status["status"], controller.STAGE_IDLE)
        self.assertFalse(status["armed"])
        self.assertEqual(handled, 0)
        self.assertEqual(self.transport.frontline_requests, [])
        self.assertEqual(self.transport.manager_project_events, [])
        visible = self.conversations.get(self.conversation_id, "C001")
        self.assertEqual(visible["messages"], [])

    def test_default_rehearsal_drives_one_case_without_formal_evidence(self):
        controller = self.make_controller()
        states_before_worker_reply: list[str] = []

        def capture_case_state() -> None:
            case = controller.journey.case_store.get_case(self.case_id)
            states_before_worker_reply.append(case["case_state"])

        self.transport.verification_request_hook = capture_case_state

        self.run_complete_journey(controller)

        self.assertEqual(controller.stage, controller.STAGE_COMPLETED)
        self.assertIsNone(controller.manifest)
        case = controller.journey.case_store.get_case(self.case_id)
        self.assertEqual(case["case_state"], "RESOLVED")
        self.assertEqual(case["incident_sequence"], 2)
        self.assertEqual(case["project_room_id"], self.mapping.project_room_id)
        self.assertEqual(len(self.transport.frontline_project_events), 2)
        self.assertEqual(
            [event["incident_sequence"] for event in self.transport.frontline_project_events],
            [1, 2],
        )
        self.assertEqual(len(self.transport.resolution_project_events), 3)
        self.assertEqual(len(self.transport.operations_routes), 1)
        self.assertEqual(len(self.transport.verification_routes), 2)
        self.assertEqual(len(self.transport.verification_replies), 2)
        self.assertEqual(states_before_worker_reply, ["VERIFYING", "VERIFYING"])
        self.assertTrue(
            all(
                reply.sender == self.transport.verification_matrix_id
                for reply in self.transport.verification_replies
            )
        )
        manager_types = {
            event["event_type"] for event in self.transport.manager_project_events
        }
        self.assertEqual(
            manager_types,
            {
                "VERIFICATION_SUMMARY",
                "SUPPLIER_EXCEPTION_RECURRED",
                "CUSTOMER_CONFIRMATION_TIMEOUT",
            },
        )

    def test_complete_journey_mirrors_all_business_writes_to_mock_api(self):
        business_api = FakeBusinessAPI()
        controller = self.make_controller(business_api=business_api)

        self.run_complete_journey(controller)

        paths = [path for path, _ in business_api.calls]
        self.assertEqual(paths.count("/resolve-order-reference"), 1)
        self.assertEqual(paths.count("/evaluate-rebooking"), 2)
        self.assertEqual(paths.count("/record-customer-confirmation"), 2)
        self.assertEqual(paths.count("/record-internal-decision"), 1)
        self.assertEqual(paths.count("/validate-execution-authorization"), 2)
        self.assertEqual(paths.count("/execute-rebooking"), 2)

    def test_repeated_poll_does_not_process_same_customer_message_twice(self):
        controller = self.make_controller()
        controller.initialize()
        self.append_customer("Synthetic idempotency message.")

        self.assertEqual(controller.poll_once(now_epoch=10), 1)
        self.assertEqual(controller.poll_once(now_epoch=11), 0)

        self.assertEqual(len(self.transport.frontline_requests), 1)
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["processed_message_ids"], ["MSG-1"])

    def test_restart_does_not_reprocess_persisted_message_id(self):
        controller = self.make_controller()
        controller.initialize()
        self.append_customer("Synthetic restart idempotency message.")
        self.assertEqual(controller.poll_once(now_epoch=10), 1)

        restored = self.restore_controller()
        self.assertEqual(restored.initialize()["status"], restored.STAGE_ORDER_DETAILS)
        self.assertEqual(restored.poll_once(now_epoch=11), 0)

        self.assertEqual(len(self.transport.frontline_requests), 1)

    def test_armed_mode_generates_five_markers_and_valid_manifest(self):
        controller = self.make_controller(armed=True)

        self.run_complete_journey(controller)

        self.assertTrue(validate_manifest(controller.manifest))
        self.assertEqual(
            [item["marker"] for item in controller.manifest["markers"]],
            [
                "DEMO_START",
                "SCENE_1_END",
                "SCENE_2_END",
                "TIMEOUT_SIMULATED",
                "DEMO_END",
            ],
        )
        self.assertTrue(
            all(
                item["matrix_event_id"].startswith("$smoke-")
                for item in controller.manifest["markers"]
            )
        )

    def test_operations_reject_is_routed_and_stops_the_journey(self):
        controller = self.make_controller()
        self.advance_to_operations(controller)
        self.transport.next_operations_decision = {
            "decision": "REJECT",
            "message_event_id": "$smoke-operations-reject",
            "operator_id": "operations-smoke",
        }

        self.assertEqual(controller.poll_once(now_epoch=40), 1)

        self.assertEqual(controller.stage, controller.STAGE_REJECTED)
        self.assertEqual(self.transport.operations_routes[0]["decision"], "REJECT")
        case = controller.journey.case_store.get_case(self.case_id)
        self.assertEqual(case["case_state"], "MANUAL_REQUIRED")

    def test_mismatched_verification_reply_blocks_success_and_recurrence(self):
        controller = self.make_controller()
        controller.initialize()
        self.append_customer("Synthetic initial customer message.")
        controller.poll_once(now_epoch=10)
        self.append_customer("Synthetic hotel and date clues.")
        controller.poll_once(now_epoch=20)
        self.transport.verification_mode = "FAILED"
        self.append_customer("Synthetic first plan confirmation.")

        self.assertEqual(controller.poll_once(now_epoch=30), 1)

        self.assertEqual(controller.stage, controller.STAGE_REJECTED)
        self.assertEqual(
            controller.journey.case_store.get_case(self.case_id)["case_state"],
            "MANUAL_REQUIRED",
        )
        self.assertEqual(len(self.transport.verification_routes), 1)
        self.assertFalse(
            any(
                event["event_type"] == "VERIFICATION_SUMMARY"
                for event in self.transport.manager_project_events
            )
        )
        self.assertEqual(self.transport.operations_requests, [])

    def test_matching_failed_verification_moves_case_to_manual_required(self):
        controller = self.make_controller()
        controller.initialize()
        self.append_customer("Synthetic initial customer message.")
        controller.poll_once(now_epoch=10)
        self.append_customer("Synthetic hotel and date clues.")
        controller.poll_once(now_epoch=20)
        controller.journey.store["fault_injection"][
            "execute_success_without_update"
        ] = True
        self.transport.verification_mode = "FAILED"

        def use_deterministic_differences() -> None:
            results = list(controller.journey.store["verification_results"].values())
            result = results[-1]
            self.transport.verification_differences = result["differences"]

        self.transport.verification_request_hook = use_deterministic_differences
        self.append_customer("Synthetic first plan confirmation.")

        self.assertEqual(controller.poll_once(now_epoch=30), 1)

        self.assertEqual(controller.stage, controller.STAGE_REJECTED)
        self.assertEqual(
            controller.journey.case_store.get_case(self.case_id)["case_state"],
            "MANUAL_REQUIRED",
        )
        self.assertEqual(len(self.transport.verification_replies), 1)
        self.assertEqual(
            self.transport.verification_replies[0].payload["verification_status"],
            "FAILED",
        )

    def test_verification_timeout_blocks_success_notification(self):
        controller = self.make_controller()
        controller.initialize()
        self.append_customer("Synthetic initial customer message.")
        controller.poll_once(now_epoch=10)
        self.append_customer("Synthetic hotel and date clues.")
        controller.poll_once(now_epoch=20)
        self.transport.verification_mode = "TIMEOUT"
        self.append_customer("Synthetic first plan confirmation.")

        self.assertEqual(controller.poll_once(now_epoch=30), 1)

        self.assertEqual(controller.stage, controller.STAGE_REJECTED)
        self.assertEqual(
            controller.journey.case_store.get_case(self.case_id)["case_state"],
            "MANUAL_REQUIRED",
        )
        visible = self.conversations.get(self.conversation_id, "C001")
        self.assertFalse(
            any(
                message["message_type"] == "RESULT"
                for message in visible["messages"]
            )
        )


if __name__ == "__main__":
    unittest.main()
