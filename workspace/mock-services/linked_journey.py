"""Reusable linked-journey orchestration over the deterministic business kernel."""

from __future__ import annotations

import copy
from typing import Any

from case_control import CaseStore
from golden_path import (
    ToolError,
    create_resolution_plan,
    evaluate_rebooking,
    execute_rebooking,
    get_authorized_order,
    record_customer_confirmation,
    record_internal_decision,
    resolve_order_reference,
    verify_rebooking,
)


class LinkedJourney:
    """Drive one Service Case through multiple supplier incidents via formal events."""

    def __init__(self, store: dict[str, Any], case_store: CaseStore):
        self.store = store
        self.case_store = case_store
        self.case_id = store["case_id"]
        self.customer_id = store["session"]["customer_id"]

    def _sync(self) -> dict[str, Any]:
        case = self.case_store.get_case(self.case_id)
        self.store["cases"][self.case_id] = copy.deepcopy(case)
        return case

    def start(
        self,
        project_id: str,
        project_room_id: str,
        occurred_at: str,
    ) -> dict[str, Any]:
        self.case_store.create_case(
            self.case_id,
            self.customer_id,
            project_id,
            project_room_id,
            occurred_at,
        )
        self.case_store.apply_event(self.case_id, "CASE_CREATED", occurred_at)
        return self._sync()

    def apply_event(self, event_type: str, occurred_at: str, **payload: Any) -> dict[str, Any]:
        self.case_store.apply_event(self.case_id, event_type, occurred_at, **payload)
        return self._sync()

    def link_order(self, clues: dict[str, str], occurred_at: str) -> str:
        match = resolve_order_reference(self.store, self.customer_id, clues)
        if match["status"] != "UNIQUE":
            raise ToolError("ORDER_NOT_UNIQUE", "Linked journey requires one authorized order")
        self.apply_event("ORDER_LINKED", occurred_at, order_ref=match["order_ref"])
        return match["order_ref"]

    def prepare_resolution(self) -> tuple[dict[str, Any], dict[str, Any]]:
        case = self._sync()
        if case["case_state"] != "RESOLVING":
            raise ToolError("CASE_STATE_CONFLICT", "Case must be RESOLVING")
        order_ref = case.get("order_ref")
        if not order_ref:
            raise ToolError("ORDER_NOT_LINKED", "Case has no authorized order reference")
        context = get_authorized_order(self.store, self.customer_id, order_ref)
        plan = create_resolution_plan(
            self.store,
            order_ref,
            context,
            incident_sequence=case["incident_sequence"],
            case_id=self.case_id,
        )
        risk = evaluate_rebooking(self.store, self.customer_id, order_ref, plan)
        return plan, risk

    def route_risk(self, risk: dict[str, Any], occurred_at: str) -> dict[str, Any]:
        event_by_decision = {
            "REQUIRE_CUSTOMER_CONFIRMATION": "RISK_REQUIRES_CUSTOMER_CONFIRMATION",
            "REQUIRE_INTERNAL_APPROVAL": "RISK_REQUIRES_INTERNAL_APPROVAL",
            "DENY": "RISK_DENIED",
        }
        return self.apply_event(event_by_decision[risk["decision"]], occurred_at)

    def approve_internal(
        self,
        plan: dict[str, Any],
        risk: dict[str, Any],
        message_event_id: str,
        operator_id: str,
        occurred_at: str,
    ) -> dict[str, Any]:
        decision = record_internal_decision(
            self.store,
            self.case_id,
            plan["resolution_plan_id"],
            risk["risk_decision_id"],
            "APPROVE",
            message_event_id,
            operator_id,
        )
        self.apply_event("INTERNAL_APPROVED", occurred_at)
        return decision

    def request_customer_confirmation(self, occurred_at: str) -> dict[str, Any]:
        return self.apply_event("CUSTOMER_CONFIRMATION_REQUESTED", occurred_at)

    def timeout_customer_confirmation(self, occurred_at: str) -> dict[str, Any]:
        return self.apply_event("CUSTOMER_CONFIRMATION_TIMEOUT", occurred_at)

    def restore_late_confirmation(
        self, occurred_at: str, message_arrival_at: str
    ) -> dict[str, Any]:
        return self.apply_event(
            "LATE_CUSTOMER_CONFIRMATION_RECEIVED",
            occurred_at,
            message_arrival_at=message_arrival_at,
            customer_id=self.customer_id,
        )

    def confirm_customer(
        self,
        plan: dict[str, Any],
        risk: dict[str, Any],
        message_event_id: str,
        occurred_at: str,
        message_arrival_at: str,
    ) -> dict[str, Any]:
        confirmation = record_customer_confirmation(
            self.store,
            self.case_id,
            plan["resolution_plan_id"],
            risk["risk_decision_id"],
            message_event_id,
        )
        self.apply_event(
            "CUSTOMER_CONFIRMED",
            occurred_at,
            message_arrival_at=message_arrival_at,
        )
        return confirmation

    def execute_and_verify(
        self,
        plan: dict[str, Any],
        risk: dict[str, Any],
        idempotency_key: str,
        occurred_at: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        execution, verification = self.execute_and_prepare_verification(
            plan,
            risk,
            idempotency_key,
            occurred_at,
        )
        self.finalize_verification(
            verification["verification_status"],
            occurred_at,
        )
        return execution, verification

    def execute_and_prepare_verification(
        self,
        plan: dict[str, Any],
        risk: dict[str, Any],
        idempotency_key: str,
        occurred_at: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Execute and compute deterministic expectations while Case stays VERIFYING."""

        execution = execute_rebooking(
            self.store,
            self.case_id,
            plan["resolution_plan_id"],
            risk["risk_decision_id"],
            idempotency_key,
        )
        self.apply_event("REBOOKING_ATTEMPTED", occurred_at)
        verification = verify_rebooking(
            self.store, self.customer_id, plan, idempotency_key
        )
        return execution, verification

    def finalize_verification(
        self,
        verification_status: str,
        occurred_at: str,
    ) -> dict[str, Any]:
        if verification_status not in {"PASSED", "FAILED"}:
            raise ValueError("verification_status must be PASSED or FAILED")
        event = (
            "VERIFICATION_PASSED"
            if verification_status == "PASSED"
            else "VERIFICATION_FAILED"
        )
        return self.apply_event(event, occurred_at)

    def notify_customer(self, occurred_at: str) -> dict[str, Any]:
        return self.apply_event("CUSTOMER_NOTIFIED", occurred_at)

    def recur_supplier_exception(self, exception_id: str, occurred_at: str) -> dict[str, Any]:
        case = self._sync()
        context = get_authorized_order(
            self.store, self.customer_id, case.get("order_ref", "")
        )
        supplier_exception = next(
            (
                item
                for item in self.store["supplier_exceptions"]
                if item["exception_id"] == exception_id
            ),
            None,
        )
        if not supplier_exception:
            raise ToolError("SUPPLIER_EVIDENCE_MISSING", "Supplier exception does not exist")
        if (
            supplier_exception.get("incident_sequence")
            != case.get("incident_sequence", 1) + 1
            or supplier_exception.get("affected_hotel_id")
            != context["order"]["hotel_id"]
        ):
            raise ToolError(
                "SUPPLIER_EXCEPTION_CONTEXT_INVALID",
                "Supplier exception does not affect the current rebooked order",
            )
        return self.apply_event(
            "SUPPLIER_EXCEPTION_RECURRED", occurred_at, exception_id=exception_id
        )
