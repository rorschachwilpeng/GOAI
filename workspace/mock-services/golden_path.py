"""Deterministic business kernel for the GOAI hotel rebooking Golden Path."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ToolError(RuntimeError):
    """A deterministic tool rejection with a machine-readable code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class TraceRecorder:
    def __init__(self, case_id: str):
        self.case_id = case_id
        self.events: list[dict[str, Any]] = []

    def record(self, event_type: str, actor: str, **details: Any) -> None:
        self.events.append(
            {
                "sequence": len(self.events) + 1,
                "case_id": self.case_id,
                "event_type": event_type,
                "actor": actor,
                "details": details,
            }
        )

    def write_jsonl(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            for event in self.events:
                file.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def load_fixture(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as file:
        fixture = json.load(file)

    store = copy.deepcopy(fixture)
    store["order_refs"] = {}
    store["cases"] = {}
    store["resolution_plans"] = {}
    store["risk_decisions"] = {}
    store["confirmations"] = {}
    store["internal_decisions"] = {}
    store["execution_records"] = {}
    return store


def _find_by_id(items: list[dict[str, Any]], key: str, value: str) -> dict[str, Any]:
    for item in items:
        if item[key] == value:
            return item
    raise ToolError("NOT_FOUND", f"No record found for {key}={value}")


def _issue_order_ref(store: dict[str, Any], customer_id: str, order_id: str) -> str:
    digest = hashlib.sha256(f"{customer_id}:{order_id}:goai-v0.1".encode()).hexdigest()[:16]
    order_ref = f"oref_{digest}"
    store["order_refs"][order_ref] = {
        "customer_id": customer_id,
        "order_id": order_id,
        "ownership_verified": True,
    }
    return order_ref


def _authorized_ref(store: dict[str, Any], customer_id: str, order_ref: str) -> dict[str, Any]:
    reference = store["order_refs"].get(order_ref)
    if not reference or reference["customer_id"] != customer_id:
        raise ToolError("ORDER_ACCESS_DENIED", "Order reference is not authorized for this customer")
    return reference


def resolve_order_reference(
    store: dict[str, Any],
    customer_id: str,
    clues: dict[str, str],
    trace: TraceRecorder | None = None,
) -> dict[str, Any]:
    """Match only inside the authenticated customer's scope."""

    candidates = [
        order
        for order in store["orders"]
        if order["customer_id"] == customer_id and order["status"] == "CONFIRMED"
    ]
    for field in ("hotel_name", "check_in_date"):
        value = clues.get(field)
        if value:
            candidates = [order for order in candidates if order[field] == value]

    if len(candidates) == 1:
        order = candidates[0]
        result = {
            "status": "UNIQUE",
            "order_ref": _issue_order_ref(store, customer_id, order["order_id"]),
            "ownership_verified": True,
            "matched_fields": [field for field in ("hotel_name", "check_in_date") if clues.get(field)],
        }
        event_type = "ORDER_MATCH_UNIQUE"
    elif len(candidates) > 1:
        result = {
            "status": "MULTIPLE",
            "candidate_count": len(candidates),
            "missing_fields": [
                field for field in ("hotel_name", "check_in_date") if not clues.get(field)
            ],
            "candidates": [],
        }
        event_type = "ORDER_MATCH_MULTIPLE"
    else:
        result = {
            "status": "NONE",
            "missing_fields": ["hotel_name", "check_in_date"],
            "candidates": [],
        }
        event_type = "ORDER_MATCH_NONE"

    if trace:
        trace.record(event_type, "resolve_order_reference", result=result)
    return result


def get_authorized_order(
    store: dict[str, Any],
    customer_id: str,
    order_ref: str,
    trace: TraceRecorder | None = None,
) -> dict[str, Any]:
    reference = _authorized_ref(store, customer_id, order_ref)
    order = _find_by_id(store["orders"], "order_id", reference["order_id"])
    exceptions = [
        item for item in store["supplier_exceptions"] if item["order_id"] == order["order_id"]
    ]
    alternatives = [
        item
        for item in store["alternatives"]
        if item["for_order_id"] == order["order_id"] and item["available"]
    ]
    result = {
        "order": copy.deepcopy(order),
        "supplier_exceptions": copy.deepcopy(exceptions),
        "eligible_rebooking_options": copy.deepcopy(alternatives),
    }
    if trace:
        trace.record(
            "ORDER_AUTHORIZED",
            "get_authorized_order",
            order_ref=order_ref,
            order_id=order["order_id"],
            exception_count=len(exceptions),
            option_count=len(alternatives),
        )
    return result


def evaluate_rebooking(
    store: dict[str, Any],
    customer_id: str,
    order_ref: str,
    resolution_plan: dict[str, Any],
    trace: TraceRecorder | None = None,
) -> dict[str, Any]:
    reference = _authorized_ref(store, customer_id, order_ref)
    if reference["order_id"] != resolution_plan["order_id"]:
        raise ToolError("ORDER_PLAN_MISMATCH", "Resolution plan does not belong to the authorized order")

    price_difference = resolution_plan["price_difference_cny"]
    policy = store["policy"]
    if price_difference <= policy["customer_confirmation_max_price_difference_cny"]:
        decision = "REQUIRE_CUSTOMER_CONFIRMATION"
        reason_code = "PRICE_DIFF_WITHIN_300"
        required_controls = ["CUSTOMER_CONFIRMATION"]
    elif price_difference <= policy["internal_approval_max_price_difference_cny"]:
        decision = "REQUIRE_INTERNAL_APPROVAL"
        reason_code = "PRICE_DIFF_REQUIRES_INTERNAL_APPROVAL"
        required_controls = ["INTERNAL_APPROVAL"]
    else:
        decision = "DENY"
        reason_code = "PRICE_DIFF_EXCEEDS_POLICY_LIMIT"
        required_controls = []

    risk_decision_id = f"RISK-{resolution_plan['resolution_plan_id']}"
    result = {
        "risk_decision_id": risk_decision_id,
        "resolution_plan_id": resolution_plan["resolution_plan_id"],
        "decision": decision,
        "rule_version": policy["rule_version"],
        "reason_code": reason_code,
        "required_controls": required_controls,
        "valid": True,
    }
    store["risk_decisions"][risk_decision_id] = copy.deepcopy(result)
    if trace:
        trace.record("RISK_EVALUATED", "evaluate_rebooking", result=result)
    return result


def record_customer_confirmation(
    store: dict[str, Any],
    case_id: str,
    resolution_plan_id: str,
    risk_decision_id: str,
    message_event_id: str,
    trace: TraceRecorder | None = None,
) -> dict[str, Any]:
    case = store["cases"].get(case_id)
    plan = store["resolution_plans"].get(resolution_plan_id)
    risk = store["risk_decisions"].get(risk_decision_id)
    if not case or not plan or not risk:
        raise ToolError("CONFIRMATION_CONTEXT_INVALID", "Case, plan, and risk decision must exist")
    if risk["resolution_plan_id"] != resolution_plan_id:
        raise ToolError("CONFIRMATION_CONTEXT_INVALID", "Risk decision is not bound to this plan")
    reference = _authorized_ref(store, case["customer_id"], plan["order_ref"])
    if reference["order_id"] != plan["order_id"]:
        raise ToolError("CONFIRMATION_CONTEXT_INVALID", "Plan order does not match its authorized reference")

    confirmation_id = f"CONFIRM-{case_id}-{message_event_id}"
    result = {
        "confirmation_id": confirmation_id,
        "case_id": case_id,
        "customer_id": case["customer_id"],
        "resolution_plan_id": resolution_plan_id,
        "risk_decision_id": risk_decision_id,
        "message_event_id": message_event_id,
        "confirmed": True,
    }
    store["confirmations"][confirmation_id] = result
    if trace:
        trace.record("CUSTOMER_CONFIRMATION_RECORDED", "record_customer_confirmation", result=result)
    return copy.deepcopy(result)


def record_internal_decision(
    store: dict[str, Any],
    case_id: str,
    resolution_plan_id: str,
    risk_decision_id: str,
    decision: str,
    message_event_id: str,
    operator_id: str,
    trace: TraceRecorder | None = None,
) -> dict[str, Any]:
    """Record one Operations Review decision for a bound high-risk plan."""

    if decision not in {"APPROVE", "REJECT"}:
        raise ToolError("INVALID_INTERNAL_DECISION", "decision must be APPROVE or REJECT")
    case = store["cases"].get(case_id)
    plan = store["resolution_plans"].get(resolution_plan_id)
    risk = store["risk_decisions"].get(risk_decision_id)
    if (
        not case
        or not plan
        or not risk
        or risk["resolution_plan_id"] != resolution_plan_id
        or risk["decision"] != "REQUIRE_INTERNAL_APPROVAL"
    ):
        raise ToolError(
            "INTERNAL_DECISION_CONTEXT_INVALID",
            "Decision must bind an existing high-risk Case, plan, and risk decision",
        )

    key = f"{case_id}:{resolution_plan_id}:{risk_decision_id}"
    requested = {
        "case_id": case_id,
        "resolution_plan_id": resolution_plan_id,
        "risk_decision_id": risk_decision_id,
        "decision": decision,
        "message_event_id": message_event_id,
        "operator_id": operator_id,
    }
    existing = store["internal_decisions"].get(key)
    if existing:
        if all(existing[field] == value for field, value in requested.items()):
            return copy.deepcopy(existing)
        raise ToolError(
            "INTERNAL_DECISION_CONFLICT",
            "A different decision is already recorded for this high-risk plan",
        )

    result = {
        "internal_decision_id": f"INTERNAL-DECISION-{case_id}-{resolution_plan_id}",
        **requested,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    store["internal_decisions"][key] = result
    if trace:
        trace.record("INTERNAL_DECISION_RECORDED", "record_internal_decision", result=result)
    return copy.deepcopy(result)


def validate_execution_authorization(
    store: dict[str, Any],
    case_id: str,
    resolution_plan_id: str,
    risk_decision_id: str,
    trace: TraceRecorder | None = None,
) -> dict[str, Any]:
    case = store["cases"].get(case_id)
    plan = store["resolution_plans"].get(resolution_plan_id)
    risk = store["risk_decisions"].get(risk_decision_id)
    if not case or not plan or not risk or not risk["valid"]:
        raise ToolError("EXECUTION_CONTEXT_INVALID", "Execution context is missing or invalid")
    if risk["resolution_plan_id"] != resolution_plan_id:
        raise ToolError("EXECUTION_CONTEXT_INVALID", "Risk decision is not bound to this plan")

    reference = _authorized_ref(store, case["customer_id"], plan["order_ref"])
    order = _find_by_id(store["orders"], "order_id", reference["order_id"])
    if order["status"] != plan["expected_current_status"]:
        raise ToolError("ORDER_STATE_CONFLICT", "Order is no longer in the expected state")

    if risk["decision"] == "REQUIRE_CUSTOMER_CONFIRMATION":
        confirmed = any(
            item["case_id"] == case_id
            and item["resolution_plan_id"] == resolution_plan_id
            and item["risk_decision_id"] == risk_decision_id
            and item["confirmed"]
            for item in store["confirmations"].values()
        )
        if not confirmed:
            raise ToolError("CUSTOMER_CONFIRMATION_REQUIRED", "Customer confirmation is required")
    elif risk["decision"] == "REQUIRE_INTERNAL_APPROVAL":
        key = f"{case_id}:{resolution_plan_id}:{risk_decision_id}"
        internal_decision = store["internal_decisions"].get(key)
        if not internal_decision:
            raise ToolError("INTERNAL_APPROVAL_REQUIRED", "Internal approval is required")
        if internal_decision["decision"] == "REJECT":
            raise ToolError("INTERNAL_APPROVAL_REJECTED", "Internal approval rejected this plan")
        result = {
            "authorized": True,
            "execution_enabled": False,
            "risk_decision_id": risk_decision_id,
        }
        if trace:
            trace.record("EXECUTION_AUTHORIZED", "validate_execution_authorization", result=result)
        return result
    else:
        raise ToolError("EXECUTION_DENIED", "Risk policy denied execution")

    result = {"authorized": True, "risk_decision_id": risk_decision_id}
    if trace:
        trace.record("EXECUTION_AUTHORIZED", "validate_execution_authorization", result=result)
    return result


def execute_rebooking(
    store: dict[str, Any],
    case_id: str,
    resolution_plan_id: str,
    risk_decision_id: str,
    idempotency_key: str,
    trace: TraceRecorder | None = None,
) -> dict[str, Any]:
    if idempotency_key in store["execution_records"]:
        previous = copy.deepcopy(store["execution_records"][idempotency_key])
        current_binding = {
            "case_id": case_id,
            "resolution_plan_id": resolution_plan_id,
            "risk_decision_id": risk_decision_id,
        }
        previous_binding = {field: previous[field] for field in current_binding}
        if current_binding != previous_binding:
            raise ToolError(
                "IDEMPOTENCY_KEY_CONFLICT",
                "Idempotency key is already bound to a different execution request",
            )
        previous["idempotent_replay"] = True
        if trace:
            trace.record("REBOOKING_REPLAYED", "execute_rebooking", result=previous)
        return previous

    risk = store["risk_decisions"].get(risk_decision_id)
    if risk and risk["decision"] == "REQUIRE_INTERNAL_APPROVAL":
        raise ToolError(
            "HIGH_RISK_EXECUTION_NOT_ENABLED",
            "High-risk execution is not enabled in V0.1",
        )

    validate_execution_authorization(
        store,
        case_id,
        resolution_plan_id,
        risk_decision_id,
        trace,
    )
    plan = store["resolution_plans"][resolution_plan_id]
    case = store["cases"][case_id]
    reference = _authorized_ref(store, case["customer_id"], plan["order_ref"])
    order = _find_by_id(store["orders"], "order_id", reference["order_id"])

    confirmation_number = f"RBK-{case_id.removeprefix('CASE-')}"
    if not store["fault_injection"].get("execute_success_without_update", False):
        order.update(
            {
                "hotel_id": plan["replacement_hotel_id"],
                "hotel_name": plan["replacement_hotel_name"],
                "check_in_date": plan["check_in_date"],
                "check_out_date": plan["check_out_date"],
                "total_price_cny": order["total_price_cny"] + plan["price_difference_cny"],
                "status": "REBOOKED",
                "confirmation_number": confirmation_number,
                "last_idempotency_key": idempotency_key,
            }
        )

    result = {
        "execution_id": f"EXEC-{case_id}",
        "case_id": case_id,
        "resolution_plan_id": resolution_plan_id,
        "risk_decision_id": risk_decision_id,
        "order_id": order["order_id"],
        "reported_status": "SUCCESS",
        "confirmation_number": confirmation_number,
        "idempotency_key": idempotency_key,
        "idempotent_replay": False,
    }
    store["execution_records"][idempotency_key] = copy.deepcopy(result)
    if trace:
        trace.record("REBOOKING_EXECUTED", "execute_rebooking", result=result)
    return result


def get_order_state(
    store: dict[str, Any],
    customer_id: str,
    order_ref: str,
    trace: TraceRecorder | None = None,
) -> dict[str, Any]:
    reference = _authorized_ref(store, customer_id, order_ref)
    order = _find_by_id(store["orders"], "order_id", reference["order_id"])
    result = copy.deepcopy(order)
    if trace:
        trace.record(
            "ORDER_STATE_READ",
            "get_order_state",
            order_id=result["order_id"],
            status=result["status"],
        )
    return result


def verify_rebooking(
    store: dict[str, Any],
    customer_id: str,
    resolution_plan: dict[str, Any],
    idempotency_key: str,
    trace: TraceRecorder | None = None,
) -> dict[str, Any]:
    actual = get_order_state(store, customer_id, resolution_plan["order_ref"], trace)
    checks = {
        "target_order_matches": actual["order_id"] == resolution_plan["order_id"],
        "ownership_unchanged": actual["customer_id"] == customer_id,
        "replacement_hotel_matches": actual["hotel_id"] == resolution_plan["replacement_hotel_id"],
        "stay_dates_match": (
            actual["check_in_date"] == resolution_plan["check_in_date"]
            and actual["check_out_date"] == resolution_plan["check_out_date"]
        ),
        "order_status_matches": actual["status"] == resolution_plan["expected_target_status"],
        "confirmation_number_exists": (
            bool(actual["confirmation_number"])
            and actual["confirmation_number"] != resolution_plan["previous_confirmation_number"]
        ),
        "idempotency_key_matches": actual["last_idempotency_key"] == idempotency_key,
    }
    differences = [name for name, passed in checks.items() if not passed]
    result = {
        "verification_status": "PASSED" if not differences else "FAILED",
        "order_id": actual["order_id"],
        "checks": checks,
        "differences": differences,
    }
    if trace:
        trace.record(
            "VERIFICATION_PASSED" if not differences else "VERIFICATION_FAILED",
            "verify_rebooking",
            result=result,
        )
    return result


def create_resolution_plan(
    store: dict[str, Any],
    order_ref: str,
    authorized_context: dict[str, Any],
) -> dict[str, Any]:
    order = authorized_context["order"]
    if not authorized_context["supplier_exceptions"]:
        raise ToolError("SUPPLIER_EVIDENCE_MISSING", "No supplier exception supports rebooking")
    if not authorized_context["eligible_rebooking_options"]:
        raise ToolError("REBOOKING_OPTION_MISSING", "No eligible rebooking option is available")
    alternative = authorized_context["eligible_rebooking_options"][0]
    plan = {
        "resolution_plan_id": "PLAN-GOLDEN-001",
        "order_ref": order_ref,
        "order_id": order["order_id"],
        "action": "REBOOK",
        "diagnosis": authorized_context["supplier_exceptions"][0]["summary"],
        "evidence_ids": [authorized_context["supplier_exceptions"][0]["exception_id"]],
        "replacement_hotel_id": alternative["hotel_id"],
        "replacement_hotel_name": alternative["hotel_name"],
        "check_in_date": alternative["check_in_date"],
        "check_out_date": alternative["check_out_date"],
        "price_difference_cny": alternative["price_difference_cny"],
        "previous_confirmation_number": order["confirmation_number"],
        "expected_current_status": "CONFIRMED",
        "expected_target_status": "REBOOKED",
    }
    store["resolution_plans"][plan["resolution_plan_id"]] = copy.deepcopy(plan)
    return plan
