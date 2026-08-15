"""Atomic Case-state persistence for the GOAI Mock workflow."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


class CaseTransitionError(ValueError):
    pass


def _aware_timestamp(value: str, field: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError as error:
        raise CaseTransitionError(f"{field} must be an ISO-8601 timestamp") from error
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise CaseTransitionError(f"{field} must include a timezone")
    return timestamp


TRANSITIONS = {
    ("RECEIVED", "CASE_CREATED"): "IDENTIFYING_ORDER",
    ("IDENTIFYING_ORDER", "CUSTOMER_INFO_REQUESTED"): "AWAITING_CUSTOMER_INFO",
    ("AWAITING_CUSTOMER_INFO", "CUSTOMER_INFO_RECEIVED"): "IDENTIFYING_ORDER",
    ("AWAITING_CUSTOMER_INFO", "CUSTOMER_INFO_TIMEOUT"): "CLOSED_INCOMPLETE",
    ("IDENTIFYING_ORDER", "ORDER_LINKED"): "RESOLVING",
    ("RESOLVING", "RISK_REQUIRES_CUSTOMER_CONFIRMATION"): "AWAITING_CUSTOMER_CONFIRMATION",
    ("RESOLVING", "RISK_REQUIRES_INTERNAL_APPROVAL"): "AWAITING_INTERNAL_APPROVAL",
    ("RESOLVING", "RISK_DENIED"): "MANUAL_REQUIRED",
    ("AWAITING_CUSTOMER_CONFIRMATION", "CUSTOMER_CONFIRMED"): "EXECUTING",
    ("AWAITING_CUSTOMER_CONFIRMATION", "CUSTOMER_REJECTED"): "RESOLVING",
    ("AWAITING_CUSTOMER_CONFIRMATION", "CUSTOMER_CONFIRMATION_REQUESTED"): "AWAITING_CUSTOMER_CONFIRMATION",
    ("AWAITING_INTERNAL_APPROVAL", "INTERNAL_REJECTED"): "MANUAL_REQUIRED",
    ("EXECUTING", "REBOOKING_ATTEMPTED"): "VERIFYING",
    ("VERIFYING", "VERIFICATION_PASSED"): "NOTIFYING_CUSTOMER",
    ("VERIFYING", "VERIFICATION_FAILED"): "MANUAL_REQUIRED",
    ("NOTIFYING_CUSTOMER", "CUSTOMER_NOTIFIED"): "RESOLVED",
    ("RESOLVED", "SUPPLIER_EXCEPTION_RECURRED"): "RESOLVING",
    ("AWAITING_INTERNAL_APPROVAL", "INTERNAL_APPROVED"): "AWAITING_CUSTOMER_CONFIRMATION",
    ("AWAITING_CUSTOMER_CONFIRMATION", "CUSTOMER_CONFIRMATION_TIMEOUT"): "CLOSED_INCOMPLETE",
}


class CaseStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, cases: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(cases, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    def create_case(self, case_id: str, customer_id: str, project_id: str,
                    project_room_id: str, occurred_at: str) -> dict[str, Any]:
        cases = self._read()
        if case_id in cases:
            raise CaseTransitionError(f"Case already exists: {case_id}")
        case = {
            "case_id": case_id,
            "customer_id": customer_id,
            "case_state": "RECEIVED",
            "resolution_mode": None,
            "project_id": project_id,
            "project_room_id": project_room_id,
            "reply_deadline_at": None,
            "background_tasks_active": False,
            "reopened_count": 0,
            "incident_sequence": 1,
            "created_at": occurred_at,
            "updated_at": occurred_at,
        }
        cases[case_id] = case
        self._write(cases)
        return dict(case)

    def get_case(self, case_id: str) -> dict[str, Any]:
        try:
            return dict(self._read()[case_id])
        except KeyError as error:
            raise CaseTransitionError(f"Case not found: {case_id}") from error

    def apply_event(self, case_id: str, event_type: str, occurred_at: str,
                    **payload: Any) -> dict[str, Any]:
        cases = self._read()
        if case_id not in cases:
            raise CaseTransitionError(f"Case not found: {case_id}")
        case = cases[case_id]
        if event_type == "CASE_REOPENED":
            if case["case_state"] not in {"CLOSED_INCOMPLETE", "RESOLVED"}:
                raise CaseTransitionError("Only closed or resolved Cases can be reopened")
            if "customer_id" in payload and payload["customer_id"] != case["customer_id"]:
                raise CaseTransitionError("customer_id cannot change when reopening")
            for field in ("project_id", "project_room_id"):
                if field in payload and payload[field] != case[field]:
                    raise CaseTransitionError(f"{field} cannot change when reopening")
            case["case_state"] = "IDENTIFYING_ORDER"
            case["reopened_count"] += 1
            case["reply_deadline_at"] = None
            case["background_tasks_active"] = False
        elif event_type == "LATE_CUSTOMER_CONFIRMATION_RECEIVED":
            if case["case_state"] != "CLOSED_INCOMPLETE":
                raise CaseTransitionError("Late confirmation can only restore an incomplete Case")
            if "customer_id" in payload and payload["customer_id"] != case["customer_id"]:
                raise CaseTransitionError("customer_id cannot change when restoring a Case")
            deadline = case.get("reply_deadline_at")
            if not deadline:
                raise CaseTransitionError("Customer confirmation was not requested")
            arrived_at = _aware_timestamp(
                payload.get("message_arrival_at", ""), "message_arrival_at"
            )
            if arrived_at <= _aware_timestamp(deadline, "reply_deadline_at"):
                raise CaseTransitionError("This confirmation is not late")
            case["case_state"] = "AWAITING_CUSTOMER_CONFIRMATION"
            case["reopened_count"] += 1
            case["last_reply_deadline_at"] = deadline
            case["reply_deadline_at"] = None
            case["background_tasks_active"] = False
        else:
            next_state = TRANSITIONS.get((case["case_state"], event_type))
            if not next_state:
                raise CaseTransitionError(
                    f"Event {event_type} is not allowed from {case['case_state']}"
                )
            if event_type in {"CUSTOMER_INFO_REQUESTED", "CUSTOMER_CONFIRMATION_REQUESTED"}:
                sent_at = _aware_timestamp(occurred_at, "occurred_at")
                case["reply_deadline_at"] = (sent_at + timedelta(hours=24)).isoformat()
                case["background_tasks_active"] = True
            elif event_type == "CUSTOMER_INFO_RECEIVED":
                deadline = case.get("reply_deadline_at")
                if not deadline:
                    raise CaseTransitionError("Customer information was not requested")
                received_at = _aware_timestamp(
                    payload.get("matrix_arrival_at", ""), "matrix_arrival_at"
                )
                if received_at > _aware_timestamp(deadline, "reply_deadline_at"):
                    raise CaseTransitionError("Late customer information must reopen the Case")
                case["reply_deadline_at"] = None
                case["background_tasks_active"] = False
            elif event_type == "ORDER_LINKED":
                if payload.get("order_ref"):
                    case["order_ref"] = payload["order_ref"]
            elif event_type == "CUSTOMER_CONFIRMED":
                if case.get("reply_deadline_at") and payload.get("message_arrival_at"):
                    arrived_at = _aware_timestamp(
                        payload["message_arrival_at"], "message_arrival_at"
                    )
                    if arrived_at > _aware_timestamp(
                        case["reply_deadline_at"], "reply_deadline_at"
                    ):
                        raise CaseTransitionError("Late confirmation must restore the Case first")
                case["reply_deadline_at"] = None
                case["background_tasks_active"] = False
            elif event_type == "CUSTOMER_INFO_TIMEOUT":
                deadline = case.get("reply_deadline_at")
                if not deadline:
                    raise CaseTransitionError("Customer information was not requested")
                if _aware_timestamp(occurred_at, "occurred_at") < _aware_timestamp(
                    deadline, "reply_deadline_at"
                ):
                    raise CaseTransitionError("Customer information deadline has not passed")
                case["background_tasks_active"] = False
            elif event_type == "SUPPLIER_EXCEPTION_RECURRED":
                case["incident_sequence"] = case.get("incident_sequence", 1) + 1
                case["current_supplier_exception_id"] = payload.get("exception_id")
            elif event_type == "CUSTOMER_CONFIRMATION_TIMEOUT":
                deadline = case.get("reply_deadline_at")
                if not deadline:
                    raise CaseTransitionError("Customer confirmation was not requested")
                if _aware_timestamp(occurred_at, "occurred_at") < _aware_timestamp(
                    deadline, "reply_deadline_at"
                ):
                    raise CaseTransitionError("Customer confirmation deadline has not passed")
                case["background_tasks_active"] = False
            case["case_state"] = next_state
        case["updated_at"] = occurred_at
        self._write(cases)
        return dict(case)
