"""Safe bridge primitives for the linked-journey rehearsal.

The bridge keeps customer projection, Matrix collaboration, and deterministic
business state as separate trust domains.  It does not create AgentTeams
Projects or Rooms and it never publishes hidden Agent output to Customer Chat.
"""

from __future__ import annotations

import json
import queue
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from conversation_store import ConversationStore
from demo_markers import DemoMarkers, MARKERS, MarkerError


PROJECT_EVENT_FIELDS = {
    "event_type",
    "business_event_id",
    "case_id",
    "incident_sequence",
    "state",
    "sender_agent",
    "receiver",
    "conclusion",
    "next_action",
    "evidence_ref",
    "occurred_at",
}
CUSTOMER_REPLY_FIELDS = {
    "event_type",
    "case_id",
    "conversation_id",
    "message_type",
    "body",
}
ALLOWED_CUSTOMER_MESSAGE_TYPES = {"TEXT", "PLAN", "STATUS", "RESULT"}
ALLOWED_PROJECT_SENDERS = {"FRONTLINE", "RESOLUTION", "MANAGER"}
ALLOWED_PROJECT_RECEIVERS = {"FRONTLINE", "RESOLUTION", "MANAGER"}
ALLOWED_OPERATIONS_DECISIONS = {"APPROVE", "REJECT"}
FORBIDDEN_CUSTOMER_TERMS = {
    "hidden_reasoning",
    "project room",
    "mcp",
    "tool payload",
    "risk_decision_id",
    "resolution_plan_id",
    "order_ref",
    "operator_id",
    "verification package",
}
FORBIDDEN_PROJECT_TERMS = {
    "hidden_reasoning",
    "password",
    "api_key",
    "access_token",
    "customer_id",
    "candidate_orders",
    "tool_payload",
}
FORBIDDEN_VERIFICATION_FIELDS = {
    "hidden_reasoning",
    "project_room_transcript",
    "execution_response",
}
VERIFICATION_RESULT_FIELDS = {
    "event_type",
    "business_event_id",
    "case_id",
    "incident_sequence",
    "sender_agent",
    "verification_result_id",
    "verification_status",
    "evidence_ref",
    "differences",
    "occurred_at",
}


class BridgeError(ValueError):
    pass


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BridgeError(f"{field} is required")
    return value


def _validate_timestamp(value: Any) -> str:
    timestamp = _required_string(value, "occurred_at")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise BridgeError("occurred_at must be an RFC3339 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise BridgeError("occurred_at must include a timezone")
    return timestamp


def _reject_terms(value: Any, forbidden: set[str], label: str) -> None:
    serialized = json.dumps(value, ensure_ascii=False).lower()
    matched = sorted(term for term in forbidden if term in serialized)
    if matched:
        raise BridgeError(f"{label} contains forbidden content: {matched[0]}")


def _reject_nested_fields(value: Any, forbidden: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in forbidden:
                raise BridgeError(f"Verification Package contains forbidden field: {key}")
            _reject_nested_fields(item, forbidden)
    elif isinstance(value, list):
        for item in value:
            _reject_nested_fields(item, forbidden)


@dataclass(frozen=True)
class RoomMapping:
    project_id: str
    project_room_id: str
    workers: tuple[str, ...]

    @classmethod
    def from_project_meta(
        cls,
        path: str | Path,
        expected_project_id: str,
    ) -> "RoomMapping":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        project_id = _required_string(payload.get("project_id"), "project_id")
        room_id = payload.get("project_room_id") or payload.get("room_id")
        project_room_id = _required_string(room_id, "project_room_id")
        workers = payload.get("workers")
        if project_id != expected_project_id:
            raise BridgeError("Project metadata does not match the required Project")
        if not isinstance(workers, list) or set(workers) != {"frontline", "resolution"}:
            raise BridgeError("Project must contain only Frontline and Resolution workers")
        return cls(project_id, project_room_id, tuple(sorted(workers)))


@dataclass(frozen=True)
class AgentReply:
    matrix_event_id: str
    payload: dict[str, Any]
    sender: str | None = None


class AgentTeamsTransport(Protocol):
    def request_frontline(self, envelope: dict[str, Any]) -> AgentReply: ...

    def publish_project_event(self, event: dict[str, Any]) -> str: ...

    def route_operations(self, decision: dict[str, Any]) -> str: ...

    def route_verification(self, package: dict[str, Any]) -> str: ...

    def request_verification(self, package: dict[str, Any]) -> AgentReply: ...


def validate_customer_reply(
    payload: dict[str, Any],
    *,
    case_id: str,
    conversation_id: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != CUSTOMER_REPLY_FIELDS:
        raise BridgeError("Customer-safe reply fields are incomplete or unexpected")
    if payload["event_type"] != "CUSTOMER_SAFE_REPLY":
        raise BridgeError("Frontline reply must be CUSTOMER_SAFE_REPLY")
    if payload["case_id"] != case_id or payload["conversation_id"] != conversation_id:
        raise BridgeError("Frontline reply identity does not match the conversation")
    if payload["message_type"] not in ALLOWED_CUSTOMER_MESSAGE_TYPES:
        raise BridgeError("Frontline reply message_type is not customer-visible")
    _required_string(payload["body"], "body")
    _reject_terms(payload, FORBIDDEN_CUSTOMER_TERMS, "Customer-safe reply")
    return dict(payload)


def validate_project_event(
    event: dict[str, Any],
    *,
    case_id: str,
    sender_agent: str | None = None,
) -> dict[str, Any]:
    if not isinstance(event, dict) or set(event) != PROJECT_EVENT_FIELDS:
        raise BridgeError("Project event fields are incomplete or unexpected")
    if event["case_id"] != case_id:
        raise BridgeError("Project event belongs to a different Case")
    if sender_agent and event["sender_agent"] != sender_agent:
        raise BridgeError("Project event sender does not match the authenticated Agent")
    if event["sender_agent"] not in ALLOWED_PROJECT_SENDERS:
        raise BridgeError("Project event sender is not allowed")
    if event["receiver"] not in ALLOWED_PROJECT_RECEIVERS:
        raise BridgeError("Project event receiver is not allowed")
    incident_sequence = event["incident_sequence"]
    if isinstance(incident_sequence, bool) or not isinstance(incident_sequence, int):
        raise BridgeError("incident_sequence must be an integer")
    if incident_sequence not in {1, 2}:
        raise BridgeError("incident_sequence must be 1 or 2")
    for field in (
        "event_type",
        "business_event_id",
        "state",
        "conclusion",
        "next_action",
        "evidence_ref",
    ):
        _required_string(event[field], field)
    _validate_timestamp(event["occurred_at"])
    _reject_terms(event, FORBIDDEN_PROJECT_TERMS, "Project event")
    return dict(event)


def validate_verification_result(
    payload: dict[str, Any],
    *,
    case_id: str,
    incident_sequence: int,
) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != VERIFICATION_RESULT_FIELDS:
        raise BridgeError("Verification Result fields are incomplete or unexpected")
    if payload["event_type"] != "VERIFICATION_RESULT":
        raise BridgeError("Verification Agent must return VERIFICATION_RESULT")
    if payload["sender_agent"] != "VERIFICATION":
        raise BridgeError("Verification Result sender is invalid")
    if payload["case_id"] != case_id:
        raise BridgeError("Verification Result belongs to a different Case")
    if payload["incident_sequence"] != incident_sequence:
        raise BridgeError("Verification Result belongs to a different incident")
    if payload["verification_status"] not in {"PASSED", "FAILED"}:
        raise BridgeError("Verification status must be PASSED or FAILED")
    for field in ("business_event_id", "verification_result_id", "evidence_ref"):
        _required_string(payload[field], field)
    expected_evidence = f"verification-result://{payload['verification_result_id']}"
    if payload["evidence_ref"] != expected_evidence:
        raise BridgeError("Verification evidence does not match the Result identity")
    differences = payload["differences"]
    if not isinstance(differences, list) or not all(
        isinstance(item, str) and item.strip() for item in differences
    ):
        raise BridgeError("Verification differences must be a list of strings")
    if payload["verification_status"] == "PASSED" and differences:
        raise BridgeError("PASSED Verification Result cannot contain differences")
    if payload["verification_status"] == "FAILED" and not differences:
        raise BridgeError("FAILED Verification Result must contain differences")
    _validate_timestamp(payload["occurred_at"])
    _reject_terms(payload, FORBIDDEN_PROJECT_TERMS, "Verification Result")
    return dict(payload)


class EvidenceCollector:
    """Separate rehearsal checkpoints from the formal five-marker manifest."""

    def __init__(self, markers: DemoMarkers | None = None) -> None:
        self.markers = markers
        self.smoke_checkpoints: list[dict[str, str]] = []

    def record_smoke(self, checkpoint: str, matrix_event_id: str) -> dict[str, str]:
        if checkpoint in MARKERS:
            raise MarkerError("Smoke checkpoints cannot use formal Demo marker names")
        item = {
            "checkpoint": _required_string(checkpoint, "checkpoint"),
            "matrix_event_id": _required_string(matrix_event_id, "matrix_event_id"),
        }
        self.smoke_checkpoints.append(item)
        return dict(item)

    def record_formal(
        self,
        marker: str,
        matrix_event_id: str,
        business_event_id: str,
        occurred_at: str | None = None,
    ) -> dict[str, str]:
        if self.markers is None:
            raise MarkerError("Formal Demo markers are disabled for this rehearsal")
        return self.markers.record(
            marker,
            matrix_event_id,
            business_event_id,
            occurred_at,
        )

    def manifest(
        self,
        incident_count: int,
        execution_count: int,
        verification_count: int,
        final_case_state: str,
    ) -> dict[str, Any]:
        if self.markers is None:
            raise MarkerError("Formal Run Manifest is disabled for this rehearsal")
        return self.markers.manifest(
            incident_count,
            execution_count,
            verification_count,
            final_case_state,
        )


class LinkedJourneyBridge:
    def __init__(
        self,
        *,
        conversations: ConversationStore,
        transport: AgentTeamsTransport,
        room_mapping: RoomMapping,
        customer_id: str,
        case_id: str,
        conversation_id: str,
        evidence: EvidenceCollector | None = None,
    ) -> None:
        self.conversations = conversations
        self.transport = transport
        self.room_mapping = room_mapping
        self.customer_id = _required_string(customer_id, "customer_id")
        self.case_id = _required_string(case_id, "case_id")
        self.conversation_id = _required_string(conversation_id, "conversation_id")
        self.evidence = evidence or EvidenceCollector()

    def forward_customer_message(self, message: dict[str, Any]) -> dict[str, str]:
        if message.get("sender") != "CUSTOMER":
            raise BridgeError("Only CUSTOMER messages may enter Frontline")
        if message.get("case_id") != self.case_id:
            raise BridgeError("Customer message belongs to a different Case")
        if message.get("conversation_id") != self.conversation_id:
            raise BridgeError("Customer message belongs to a different conversation")
        body = _required_string(message.get("body"), "body")
        envelope = {
            "event_type": "CUSTOMER_MESSAGE_RECEIVED",
            "case_id": self.case_id,
            "conversation_id": self.conversation_id,
            "customer_id": self.customer_id,
            "message_id": _required_string(message.get("message_id"), "message_id"),
            "body": body,
            "project_id": self.room_mapping.project_id,
            "project_room_id": self.room_mapping.project_room_id,
        }
        response = self.transport.request_frontline(envelope)
        reply = validate_customer_reply(
            response.payload,
            case_id=self.case_id,
            conversation_id=self.conversation_id,
        )
        projected = self.conversations.append_frontline_projection(
            self.conversation_id,
            self.customer_id,
            reply["message_type"],
            reply["body"],
        )
        self.evidence.record_smoke("CUSTOMER_FRONTLINE_ROUNDTRIP", response.matrix_event_id)
        return projected

    def project_frontline_update(
        self,
        message_type: str,
        customer_safe_facts: str,
    ) -> dict[str, str]:
        envelope = {
            "event_type": "FRONTLINE_NOTIFICATION_REQUESTED",
            "case_id": self.case_id,
            "conversation_id": self.conversation_id,
            "customer_id": self.customer_id,
            "message_id": f"INTERNAL-{len(self.evidence.smoke_checkpoints) + 1}",
            "body": _required_string(customer_safe_facts, "customer_safe_facts"),
            "project_id": self.room_mapping.project_id,
            "project_room_id": self.room_mapping.project_room_id,
        }
        response = self.transport.request_frontline(envelope)
        reply = validate_customer_reply(
            response.payload,
            case_id=self.case_id,
            conversation_id=self.conversation_id,
        )
        projected = self.conversations.append_frontline_projection(
            self.conversation_id,
            self.customer_id,
            message_type,
            reply["body"],
        )
        self.evidence.record_smoke("FRONTLINE_CUSTOMER_UPDATE", response.matrix_event_id)
        return projected

    def publish_project_event(
        self,
        event: dict[str, Any],
        *,
        authenticated_agent: str,
    ) -> str:
        validated = validate_project_event(
            event,
            case_id=self.case_id,
            sender_agent=authenticated_agent,
        )
        matrix_event_id = self.transport.publish_project_event(validated)
        self.evidence.record_smoke(
            f"PROJECT_{validated['event_type']}",
            matrix_event_id,
        )
        return matrix_event_id

    def route_operations_approval(self, decision: dict[str, Any]) -> str:
        if set(decision) != {
            "case_id",
            "decision",
            "message_event_id",
            "operator_id",
        }:
            raise BridgeError("Operations decision fields are incomplete or unexpected")
        if decision["case_id"] != self.case_id:
            raise BridgeError("Operations decision belongs to a different Case")
        if decision["decision"] not in ALLOWED_OPERATIONS_DECISIONS:
            raise BridgeError("Operations decision must be APPROVE or REJECT")
        for field in ("message_event_id", "operator_id"):
            _required_string(decision[field], field)
        matrix_event_id = self.transport.route_operations(dict(decision))
        self.evidence.record_smoke("OPERATIONS_DECISION_ROUTED", matrix_event_id)
        return matrix_event_id

    def route_verification(self, package: dict[str, Any]) -> str:
        if package.get("case_id") != self.case_id:
            raise BridgeError("Verification Package belongs to a different Case")
        if package.get("package_hash_valid") is not True:
            raise BridgeError("Verification Package hash must be valid before routing")
        _reject_nested_fields(package, FORBIDDEN_VERIFICATION_FIELDS)
        matrix_event_id = self.transport.route_verification(dict(package))
        self.evidence.record_smoke("VERIFICATION_ROUTED", matrix_event_id)
        return matrix_event_id

    def request_verification(
        self,
        package: dict[str, Any],
        *,
        incident_sequence: int,
        expected_result: dict[str, Any],
    ) -> AgentReply:
        if package.get("case_id") != self.case_id:
            raise BridgeError("Verification Package belongs to a different Case")
        if package.get("package_hash_valid") is not True:
            raise BridgeError("Verification Package hash must be valid before routing")
        _reject_nested_fields(package, FORBIDDEN_VERIFICATION_FIELDS)
        response = self.transport.request_verification(dict(package))
        expected_sender = getattr(self.transport, "verification_matrix_id", None)
        if not expected_sender or response.sender != expected_sender:
            raise BridgeError("Verification reply did not come from the assigned Agent")
        payload = validate_verification_result(
            response.payload,
            case_id=self.case_id,
            incident_sequence=incident_sequence,
        )
        if payload["verification_status"] != expected_result.get("verification_status"):
            raise BridgeError("Verification Result conflicts with deterministic readback")
        expected_differences = sorted(expected_result.get("differences", []))
        if sorted(payload["differences"]) != expected_differences:
            raise BridgeError("Verification differences conflict with deterministic readback")
        self.evidence.record_smoke(
            "VERIFICATION_REPLY_CONSUMED",
            response.matrix_event_id,
        )
        return AgentReply(response.matrix_event_id, payload, response.sender)

    def publish_automatic_event(
        self,
        event: dict[str, Any],
    ) -> str:
        """Publish orchestrator-owned recurrence or timeout events as Manager."""

        if event.get("event_type") not in {
            "SUPPLIER_EXCEPTION_RECURRED",
            "CUSTOMER_CONFIRMATION_TIMEOUT",
        }:
            raise BridgeError("Event is not an allowed automatic journey event")
        return self.publish_project_event(event, authenticated_agent="MANAGER")


class QueuedCustomerBridge:
    """Process customer messages off the HTTP request thread."""

    def __init__(
        self,
        *,
        transport: AgentTeamsTransport,
        room_mapping: RoomMapping,
        customer_id: str,
        case_id: str,
        conversation_id: str,
    ) -> None:
        self.transport = transport
        self.room_mapping = room_mapping
        self.customer_id = customer_id
        self.case_id = case_id
        self.conversation_id = conversation_id
        self._messages: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._bridge: LinkedJourneyBridge | None = None
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None

    def bind(self, conversations: ConversationStore) -> None:
        if self._bridge is not None:
            raise BridgeError("Customer bridge is already bound")
        self._bridge = LinkedJourneyBridge(
            conversations=conversations,
            transport=self.transport,
            room_mapping=self.room_mapping,
            customer_id=self.customer_id,
            case_id=self.case_id,
            conversation_id=self.conversation_id,
        )
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, message: dict[str, Any]) -> None:
        if self._bridge is None:
            raise BridgeError("Customer bridge is not bound")
        self._messages.put(dict(message))

    def reset(self) -> None:
        self.last_error = None
        while True:
            try:
                self._messages.get_nowait()
                self._messages.task_done()
            except queue.Empty:
                return

    def wait_until_idle(self, timeout: float = 5.0) -> None:
        completed = threading.Event()

        def wait_for_queue() -> None:
            self._messages.join()
            completed.set()

        threading.Thread(target=wait_for_queue, daemon=True).start()
        if not completed.wait(timeout):
            raise BridgeError("Customer bridge did not become idle before timeout")

    def close(self) -> None:
        if self._thread is None:
            return
        self._messages.put(None)
        self._thread.join(timeout=2)
        self._thread = None

    def _run(self) -> None:
        while True:
            message = self._messages.get()
            try:
                if message is None:
                    return
                if self._bridge is None:
                    raise BridgeError("Customer bridge is not bound")
                self._bridge.forward_customer_message(message)
            except (BridgeError, RuntimeError) as error:
                self.last_error = str(error)
            finally:
                self._messages.task_done()
