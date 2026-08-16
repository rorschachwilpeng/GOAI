#!/usr/bin/env python3
"""One-process controller for the linked-journey rehearsal.

The default mode is deliberately unarmed: it starts idle, waits for the first
Customer Chat message, and cannot create the five formal Demo markers.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agentteams_transport import DockerAgentTeamsTransport, MatrixAdminClient
from case_control import CaseStore
from demo_markers import DemoMarkers
from golden_path import load_fixture
from journey_orchestrator import JourneyOrchestrator
from linked_journey import LinkedJourney
from linked_journey_bridge import EvidenceCollector, LinkedJourneyBridge, RoomMapping
from linked_journey_bridge import BridgeError
from run_customer_bridge import HttpConversationProjection
from verification_package import freeze_verification_package


DEFAULT_PROJECT_META = (
    Path(__file__).parents[1]
    / "runs"
    / "2026-08-14-project-room-migration"
    / "project-meta.json"
)
DEFAULT_FIXTURE = Path(__file__).parent / "fixtures" / "golden-case.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _after(timestamp: str, seconds: int) -> str:
    return (datetime.fromisoformat(timestamp) + timedelta(seconds=seconds)).isoformat()


def _project_event(
    *,
    event_type: str,
    case_id: str,
    incident_sequence: int,
    state: str,
    sender: str,
    receiver: str,
    conclusion: str,
    next_action: str,
    evidence_ref: str,
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "business_event_id": f"{case_id}-{event_type}-{incident_sequence}",
        "case_id": case_id,
        "incident_sequence": incident_sequence,
        "state": state,
        "sender_agent": sender,
        "receiver": receiver,
        "conclusion": conclusion,
        "next_action": next_action,
        "evidence_ref": evidence_ref,
        "occurred_at": _now(),
    }


class RehearsalController:
    STAGE_IDLE = "IDLE_WAITING_FOR_FIRST_CUSTOMER"
    STAGE_ORDER_DETAILS = "WAITING_FOR_ORDER_DETAILS"
    STAGE_FIRST_CONFIRMATION = "WAITING_FOR_FIRST_CONFIRMATION"
    STAGE_OPERATIONS = "WAITING_FOR_OPERATIONS_DECISION"
    STAGE_SECOND_CONFIRMATION = "WAITING_FOR_SECOND_CONFIRMATION_TIMEOUT"
    STAGE_LATE_CONFIRMATION = "WAITING_FOR_LATE_CONFIRMATION"
    STAGE_COMPLETED = "COMPLETED"
    STAGE_REJECTED = "MANUAL_REQUIRED"

    def __init__(
        self,
        *,
        projection: Any,
        transport: Any,
        bridge: LinkedJourneyBridge,
        journey: LinkedJourney,
        orchestrator: JourneyOrchestrator,
        state_path: str | Path,
        timeout_delay_seconds: float,
        business_api: Any | None = None,
        restored_state: dict[str, Any] | None = None,
    ) -> None:
        self.projection = projection
        self.transport = transport
        self.bridge = bridge
        self.journey = journey
        self.orchestrator = orchestrator
        self.state_path = Path(state_path)
        self.timeout_delay_seconds = timeout_delay_seconds
        self.business_api = business_api
        state = restored_state or {}
        self.stage = state.get("stage", self.STAGE_IDLE)
        self.processed_message_ids = set(state.get("processed_message_ids", []))
        self.current_plan_id = state.get("current_plan_id")
        self.current_risk_id = state.get("current_risk_id")
        self.operations_after_ms = state.get("operations_after_ms")
        self.timeout_due_epoch = state.get("timeout_due_epoch")
        self.manifest = state.get("manifest")

    def initialize(self) -> dict[str, Any]:
        self._ensure_conversation()
        try:
            self.journey.case_store.get_case(self.journey.case_id)
        except ValueError:
            self.journey.start(
                self.bridge.room_mapping.project_id,
                self.bridge.room_mapping.project_room_id,
                _now(),
            )
        self._save()
        return {
            "status": self.stage,
            "case_id": self.journey.case_id,
            "conversation_id": self.bridge.conversation_id,
            "armed": self.bridge.evidence.markers is not None,
        }

    def poll_once(self, now_epoch: float | None = None) -> int:
        now_epoch = time.time() if now_epoch is None else now_epoch
        handled = 0
        conversation = self.projection.get(
            self.bridge.conversation_id,
            self.bridge.customer_id,
        )
        for message in conversation.get("messages", []):
            message_id = str(message.get("message_id", ""))
            if message.get("sender") != "CUSTOMER" or message_id in self.processed_message_ids:
                continue
            self._handle_customer_message(message)
            self.processed_message_ids.add(message_id)
            self._save()
            handled += 1

        if self.stage == self.STAGE_OPERATIONS and self.operations_after_ms is not None:
            decision = self.transport.poll_operations_decision(self.operations_after_ms)
            if decision:
                self._handle_operations_decision(decision, now_epoch)
                self._save()
                handled += 1

        if (
            self.stage == self.STAGE_SECOND_CONFIRMATION
            and self.timeout_due_epoch is not None
            and now_epoch >= self.timeout_due_epoch
        ):
            self._handle_timeout()
            self._save()
            handled += 1
        return handled

    def _handle_customer_message(self, message: dict[str, Any]) -> None:
        if self.stage == self.STAGE_IDLE:
            self.bridge.forward_customer_message(message)
            frontline_matrix_event_id = self.bridge.evidence.smoke_checkpoints[-1][
                "matrix_event_id"
            ]
            self.journey.apply_event(
                "CUSTOMER_INFO_REQUESTED",
                str(message["occurred_at"]),
            )
            self._record_marker(
                "DEMO_START",
                frontline_matrix_event_id,
            )
            self.stage = self.STAGE_ORDER_DETAILS
            return

        if self.stage == self.STAGE_ORDER_DETAILS:
            self.bridge.forward_customer_message(message)
            self.journey.apply_event(
                "CUSTOMER_INFO_RECEIVED",
                str(message["occurred_at"]),
                matrix_arrival_at=str(message["occurred_at"]),
            )
            order_ref = self.journey.link_order(
                {
                    "hotel_name": "上海虹桥海湾花园酒店",
                    "check_in_date": "2026-08-15",
                },
                str(message["occurred_at"]),
            )
            if self.business_api is not None:
                remote_match = self.business_api.call_business_tool(
                    "/resolve-order-reference",
                    {
                        "customer_id": self.journey.customer_id,
                        "clues": {
                            "hotel_name": "上海虹桥海湾花园酒店",
                            "check_in_date": "2026-08-15",
                        },
                    },
                )
                if (
                    remote_match.get("status") != "UNIQUE"
                    or remote_match.get("order_ref") != order_ref
                ):
                    raise ValueError("Mock API order match conflicts with Case state")
            handoff = _project_event(
                event_type="ORDER_LINKED",
                case_id=self.journey.case_id,
                incident_sequence=1,
                state="RESOLVING",
                sender="FRONTLINE",
                receiver="RESOLUTION",
                conclusion="Customer-owned order was uniquely linked.",
                next_action="Investigate the current supplier exception.",
                evidence_ref=f"order-ref://{order_ref}",
            )
            frontline_event = self.transport.request_frontline_project_handoff(handoff)
            self.bridge.evidence.record_smoke(
                "PROJECT_ORDER_LINKED",
                frontline_event["matrix_event_id"],
            )
            plan, risk = self.journey.prepare_resolution()
            self._mirror_resolution(plan, risk)
            self.current_plan_id = plan["resolution_plan_id"]
            self.current_risk_id = risk["risk_decision_id"]
            self.journey.route_risk(risk, _now())
            self.journey.request_customer_confirmation(_now())
            proposal = _project_event(
                event_type="RESOLUTION_PROPOSED",
                case_id=self.journey.case_id,
                incident_sequence=1,
                state="AWAITING_CUSTOMER_CONFIRMATION",
                sender="RESOLUTION",
                receiver="FRONTLINE",
                conclusion="An eligible replacement plan is ready.",
                next_action="Request customer confirmation for the current plan.",
                evidence_ref=f"resolution-plan://{plan['resolution_plan_id']}",
            )
            resolution_event = self.transport.wait_resolution_project_update(
                proposal,
                source_event_id=frontline_event["matrix_event_id"],
            )
            self.bridge.evidence.record_smoke(
                "PROJECT_RESOLUTION_PROPOSED_1",
                resolution_event["matrix_event_id"],
            )
            self.bridge.project_frontline_update(
                "PLAN",
                "Tell the customer the first replacement hotel is 上海虹桥海湾臻选酒店, dates and room type are unchanged, the price difference is 180 CNY, and ask for confirmation.",
            )
            self.stage = self.STAGE_FIRST_CONFIRMATION
            return

        if self.stage == self.STAGE_FIRST_CONFIRMATION:
            self.bridge.forward_customer_message(message)
            plan, risk = self._current_plan_and_risk()
            self.journey.confirm_customer(
                plan,
                risk,
                str(message["message_id"]),
                str(message["occurred_at"]),
                str(message["occurred_at"]),
            )
            self._mirror_customer_confirmation(plan, risk, message)
            self._mirror_execution(plan, risk, 1)
            _, verification = self.journey.execute_and_prepare_verification(
                plan,
                risk,
                f"{self.journey.case_id}-EXECUTION-1",
                _now(),
            )
            verification_event = self._route_verification(plan, verification, 1)
            if verification_event is None:
                self.journey.finalize_verification("FAILED", _now())
                self.stage = self.STAGE_REJECTED
                return
            self.journey.finalize_verification("PASSED", _now())
            self.journey.notify_customer(_now())
            self.bridge.project_frontline_update(
                "RESULT",
                "Tell the customer the first rebooking succeeded and the verified new confirmation number is RBK-GOLDEN-001-1.",
            )
            self._record_marker(
                "SCENE_1_END",
                verification_event,
                business_event_id=f"{self.journey.case_id}-VERIFICATION-1",
            )
            recurrence = self.orchestrator.advance_second_exception("SUP-EX-002", _now())
            plan, risk = self.journey.prepare_resolution()
            self._mirror_resolution(plan, risk)
            self.current_plan_id = plan["resolution_plan_id"]
            self.current_risk_id = risk["risk_decision_id"]
            self.journey.route_risk(risk, _now())
            proposal = _project_event(
                event_type="RESOLUTION_PROPOSED",
                case_id=self.journey.case_id,
                incident_sequence=2,
                state="AWAITING_INTERNAL_APPROVAL",
                sender="RESOLUTION",
                receiver="FRONTLINE",
                conclusion="A second replacement plan requires Operations review.",
                next_action="Request APPROVE or REJECT from Hotel Operations.",
                evidence_ref=f"resolution-plan://{plan['resolution_plan_id']}",
            )
            resolution_event = self.transport.wait_resolution_project_update(
                proposal,
                source_event_id=recurrence["matrix_event_id"],
            )
            request = self.transport.request_operations_review(
                {
                    "case_id": self.journey.case_id,
                    "incident_sequence": 2,
                    "price_difference_cny": 800,
                    "decision_required": "APPROVE | REJECT",
                }
            )
            self.operations_after_ms = request["after_ms"]
            self.bridge.project_frontline_update(
                "STATUS",
                "Tell the customer the first replacement hotel also became unavailable and the 800 CNY alternative is awaiting Operations review.",
            )
            self.bridge.evidence.record_smoke(
                "PROJECT_RESOLUTION_PROPOSED_2",
                resolution_event["matrix_event_id"],
            )
            self.stage = self.STAGE_OPERATIONS
            return

        if self.stage == self.STAGE_LATE_CONFIRMATION:
            self.bridge.forward_customer_message(message)
            plan, risk = self._current_plan_and_risk()
            case = self.journey.store["cases"][self.journey.case_id]
            late_at = _after(case["reply_deadline_at"], 1)
            self.journey.restore_late_confirmation(late_at, late_at)
            self.journey.confirm_customer(
                plan,
                risk,
                str(message["message_id"]),
                _after(late_at, 1),
                late_at,
            )
            self._mirror_customer_confirmation(plan, risk, message)
            self._mirror_execution(plan, risk, 2)
            _, verification = self.journey.execute_and_prepare_verification(
                plan,
                risk,
                f"{self.journey.case_id}-EXECUTION-2",
                _after(late_at, 2),
            )
            verification_event = self._route_verification(plan, verification, 2)
            if verification_event is None:
                self.journey.finalize_verification("FAILED", _after(late_at, 2))
                self.stage = self.STAGE_REJECTED
                return
            self.journey.finalize_verification("PASSED", _after(late_at, 2))
            self.journey.notify_customer(_after(late_at, 3))
            self.bridge.project_frontline_update(
                "RESULT",
                "Tell the customer the second rebooking succeeded and the verified new confirmation number is RBK-GOLDEN-001-2; the Case is complete.",
            )
            self._record_marker(
                "DEMO_END",
                verification_event,
                business_event_id=f"{self.journey.case_id}-VERIFICATION-2",
            )
            self.stage = self.STAGE_COMPLETED
            if self.bridge.evidence.markers is not None:
                self.manifest = self.bridge.evidence.manifest(2, 2, 2, "RESOLVED")
            return

        raise ValueError(f"Customer message is not expected while stage={self.stage}")

    def _handle_operations_decision(
        self,
        decision: dict[str, Any],
        now_epoch: float,
    ) -> None:
        plan, risk = self._current_plan_and_risk()
        if decision["decision"] == "REJECT":
            self.bridge.route_operations_approval(
                {
                    "case_id": self.journey.case_id,
                    **decision,
                }
            )
            self.journey.apply_event("INTERNAL_REJECTED", _now())
            self.stage = self.STAGE_REJECTED
            return
        self.journey.approve_internal(
            plan,
            risk,
            decision["message_event_id"],
            decision["operator_id"],
            _now(),
        )
        if self.business_api is not None:
            recorded = self.business_api.call_business_tool(
                "/record-internal-decision",
                {
                    "case_id": self.journey.case_id,
                    "resolution_plan_id": plan["resolution_plan_id"],
                    "risk_decision_id": risk["risk_decision_id"],
                    "decision": decision["decision"],
                    "message_event_id": decision["message_event_id"],
                    "operator_id": decision["operator_id"],
                },
            )
            if recorded.get("decision") != "APPROVE":
                raise ValueError("Mock API did not record Operations approval")
        routed_id = self.bridge.route_operations_approval(
            {
                "case_id": self.journey.case_id,
                **decision,
            }
        )
        summary = _project_event(
            event_type="OPERATIONS_DECISION_SUMMARY",
            case_id=self.journey.case_id,
            incident_sequence=2,
            state="AWAITING_CUSTOMER_CONFIRMATION",
            sender="RESOLUTION",
            receiver="FRONTLINE",
            conclusion="Operations approval is recorded for the current plan.",
            next_action="Request customer confirmation for the same plan.",
            evidence_ref=f"operations-decision://{decision['message_event_id']}",
        )
        summary_event = self.transport.request_resolution_project_update(
            summary,
            source_event_id=routed_id,
        )
        self.journey.request_customer_confirmation(_now())
        self.bridge.project_frontline_update(
            "PLAN",
            "Tell the customer Operations approved the 上海虹桥江景酒店 alternative with an 800 CNY price difference and ask for confirmation.",
        )
        self._record_marker(
            "SCENE_2_END",
            summary_event["matrix_event_id"],
            business_event_id=f"{self.journey.case_id}-OPERATIONS-APPROVED",
        )
        self.timeout_due_epoch = now_epoch + self.timeout_delay_seconds
        self.stage = self.STAGE_SECOND_CONFIRMATION

    def _handle_timeout(self) -> None:
        case = self.journey.store["cases"][self.journey.case_id]
        timeout = self.orchestrator.simulate_customer_confirmation_timeout(
            case["reply_deadline_at"]
        )
        self.bridge.project_frontline_update(
            "STATUS",
            "Tell the customer the confirmation window elapsed and the same Case is temporarily closed; a later reply will resume it.",
        )
        self._record_marker(
            "TIMEOUT_SIMULATED",
            timeout["matrix_event_id"],
            business_event_id=f"{self.journey.case_id}-TIMEOUT",
        )
        self.stage = self.STAGE_LATE_CONFIRMATION
        self.timeout_due_epoch = None

    def _route_verification(
        self,
        plan: dict[str, Any],
        verification: dict[str, Any],
        incident_sequence: int,
    ) -> str | None:
        package = freeze_verification_package(
            {
                "case_id": self.journey.case_id,
                "customer_id": self.journey.customer_id,
                "order_ref": plan["order_ref"],
                "resolution_plan": plan,
                "idempotency_key": f"{self.journey.case_id}-EXECUTION-{incident_sequence}",
            },
            _now(),
        )
        package["package_hash_valid"] = True
        try:
            response = self.bridge.request_verification(
                package,
                incident_sequence=incident_sequence,
                expected_result=verification,
            )
        except (BridgeError, RuntimeError):
            return None
        if response.payload["verification_status"] != "PASSED":
            return None
        summary = _project_event(
            event_type="VERIFICATION_SUMMARY",
            case_id=self.journey.case_id,
            incident_sequence=incident_sequence,
            state="NOTIFYING_CUSTOMER",
            sender="MANAGER",
            receiver="FRONTLINE",
            conclusion=f"Independent readback passed for execution {incident_sequence}.",
            next_action="Notify the customer with the verified result.",
            evidence_ref=response.payload["evidence_ref"],
        )
        return self.bridge.publish_project_event(summary, authenticated_agent="MANAGER")

    def _current_plan_and_risk(self) -> tuple[dict[str, Any], dict[str, Any]]:
        if not self.current_plan_id or not self.current_risk_id:
            raise ValueError("Current Resolution Plan is missing")
        return (
            self.journey.store["resolution_plans"][self.current_plan_id],
            self.journey.store["risk_decisions"][self.current_risk_id],
        )

    def _mirror_resolution(
        self,
        plan: dict[str, Any],
        risk: dict[str, Any],
    ) -> None:
        if self.business_api is None:
            return
        remote = self.business_api.call_business_tool(
            "/evaluate-rebooking",
            {
                "case_id": self.journey.case_id,
                "customer_id": self.journey.customer_id,
                "order_ref": plan["order_ref"],
                "resolution_plan": plan,
            },
        )
        if (
            remote.get("risk_decision_id") != risk["risk_decision_id"]
            or remote.get("decision") != risk["decision"]
        ):
            raise ValueError("Mock API risk decision conflicts with Case state")

    def _mirror_customer_confirmation(
        self,
        plan: dict[str, Any],
        risk: dict[str, Any],
        message: dict[str, Any],
    ) -> None:
        if self.business_api is None:
            return
        recorded = self.business_api.call_business_tool(
            "/record-customer-confirmation",
            {
                "case_id": self.journey.case_id,
                "resolution_plan_id": plan["resolution_plan_id"],
                "risk_decision_id": risk["risk_decision_id"],
                "message_event_id": str(message["message_id"]),
            },
        )
        if recorded.get("confirmed") is not True:
            raise ValueError("Mock API did not record Customer confirmation")

    def _mirror_execution(
        self,
        plan: dict[str, Any],
        risk: dict[str, Any],
        incident_sequence: int,
    ) -> None:
        if self.business_api is None:
            return
        identifiers = {
            "case_id": self.journey.case_id,
            "resolution_plan_id": plan["resolution_plan_id"],
            "risk_decision_id": risk["risk_decision_id"],
        }
        authorization = self.business_api.call_business_tool(
            "/validate-execution-authorization",
            identifiers,
        )
        if authorization.get("authorized") is not True:
            raise ValueError("Mock API execution authorization was rejected")
        execution = self.business_api.call_business_tool(
            "/execute-rebooking",
            {
                **identifiers,
                "idempotency_key": (
                    f"{self.journey.case_id}-EXECUTION-{incident_sequence}"
                ),
            },
        )
        if execution.get("reported_status") != "SUCCESS":
            raise ValueError("Mock API rebooking did not report success")

    def _record_marker(
        self,
        marker: str,
        matrix_event_id: str,
        business_event_id: str | None = None,
    ) -> None:
        if self.bridge.evidence.markers is None:
            return
        if not matrix_event_id.startswith("$"):
            matrix_event_id = f"$customer-{matrix_event_id}"
        self.bridge.evidence.record_formal(
            marker,
            matrix_event_id,
            business_event_id or f"{self.journey.case_id}-{marker}",
        )

    def _ensure_conversation(self) -> None:
        try:
            self.projection.get(self.bridge.conversation_id, self.bridge.customer_id)
            return
        except (RuntimeError, ValueError):
            pass
        self.projection.create(
            self.bridge.conversation_id,
            self.journey.case_id,
            self.bridge.customer_id,
        )

    def _save(self) -> None:
        payload = {
            "stage": self.stage,
            "processed_message_ids": sorted(self.processed_message_ids),
            "current_plan_id": self.current_plan_id,
            "current_risk_id": self.current_risk_id,
            "operations_after_ms": self.operations_after_ms,
            "timeout_due_epoch": self.timeout_due_epoch,
            "manifest": self.manifest,
            "marker_items": (
                self.bridge.evidence.markers.items
                if self.bridge.evidence.markers is not None
                else None
            ),
            "business_store": self.journey.store,
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, self.state_path)


def build_controller(args: argparse.Namespace) -> RehearsalController:
    internal_token = os.environ.get("GOAI_INTERNAL_TOKEN")
    if not internal_token:
        raise SystemExit("GOAI_INTERNAL_TOKEN must be injected into the controller")
    restored = None
    if args.state_path.exists():
        restored = json.loads(args.state_path.read_text(encoding="utf-8"))
        store = restored["business_store"]
    else:
        store = load_fixture(args.fixture)
        store["case_id"] = args.case_id
        store["cases"] = {}
    mapping = RoomMapping.from_project_meta(args.project_meta, args.project_id)
    projection = HttpConversationProjection(args.base_url, internal_token)
    transport = DockerAgentTeamsTransport.from_runtime(
        matrix=MatrixAdminClient(manager_container=args.manager_container),
        project_room_id=mapping.project_room_id,
        manager_container=args.manager_container,
    )
    case_store = CaseStore(args.case_store)
    journey = LinkedJourney(store, case_store)
    markers = None
    if args.armed:
        if not args.run_id:
            raise SystemExit("--run-id is required with --armed")
        markers = DemoMarkers(
            args.run_id,
            args.case_id,
            mapping.project_room_id,
            args.conversation_id,
        )
        if restored and restored.get("marker_items"):
            markers.items = list(restored["marker_items"])
    evidence = EvidenceCollector(markers)
    bridge = LinkedJourneyBridge(
        conversations=projection,
        transport=transport,
        room_mapping=mapping,
        customer_id=args.customer_id,
        case_id=args.case_id,
        conversation_id=args.conversation_id,
        evidence=evidence,
    )
    return RehearsalController(
        projection=projection,
        transport=transport,
        bridge=bridge,
        journey=journey,
        orchestrator=JourneyOrchestrator(journey, bridge),
        state_path=args.state_path,
        timeout_delay_seconds=args.timeout_delay_seconds,
        business_api=projection,
        restored_state=restored,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:19090")
    parser.add_argument("--manager-container", default="agentteams-manager")
    parser.add_argument("--project-meta", type=Path, default=DEFAULT_PROJECT_META)
    parser.add_argument("--project-id", default="proj-goai-case-golden-001")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--customer-id", default="C001")
    parser.add_argument("--case-id", default="CASE-SMOKE-REHEARSAL-001")
    parser.add_argument(
        "--conversation-id",
        default="conversation-smoke-rehearsal-001",
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=Path("/tmp/goai-rehearsal-controller-state.json"),
    )
    parser.add_argument(
        "--case-store",
        type=Path,
        default=Path("/tmp/goai-rehearsal-cases.json"),
    )
    parser.add_argument("--timeout-delay-seconds", type=float, default=5.0)
    parser.add_argument("--armed", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    controller = build_controller(args)
    print(json.dumps(controller.initialize(), ensure_ascii=False), flush=True)
    if args.once:
        print(json.dumps({"handled": controller.poll_once()}), flush=True)
        return
    try:
        while True:
            controller.poll_once()
            time.sleep(0.5)
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
