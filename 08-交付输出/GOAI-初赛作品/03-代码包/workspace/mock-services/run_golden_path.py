#!/usr/bin/env python3
"""Run the deterministic GOAI Golden Path and write its evidence artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from golden_path import (
    TraceRecorder,
    create_resolution_plan,
    evaluate_rebooking,
    execute_rebooking,
    get_authorized_order,
    get_order_state,
    load_fixture,
    record_customer_confirmation,
    resolve_order_reference,
    verify_rebooking,
)
from verification_package import freeze_verification_package, verify_package_hash


INITIAL_MESSAGE = "酒店说查不到我的预订，请帮我处理。"
FOLLOW_UP_MESSAGE = "上海虹桥海湾花园酒店，8月15日入住，8月17日离店。"
CONFIRMATION_MESSAGE = "确认改订"

FRONTLINE_AGENT = "Frontline Agent"
RESOLUTION_AGENT = "Resolution Agent"
MANAGER_AGENT = "Manager Agent"
VERIFICATION_AGENT = "Verification Agent"


def _transition(store: dict, trace: TraceRecorder, case_id: str, state: str) -> None:
    previous = store["cases"][case_id]["case_state"]
    store["cases"][case_id]["case_state"] = state
    trace.record("CASE_STATE_CHANGED", MANAGER_AGENT, previous=previous, current=state)


def run_golden_path(fixture_path: str | Path, output_dir: str | Path) -> dict:
    store = load_fixture(fixture_path)
    case_id = store["case_id"]
    customer_id = store["session"]["customer_id"]
    trace = TraceRecorder(case_id)
    store["cases"][case_id] = {
        "case_id": case_id,
        "customer_id": customer_id,
        "case_state": "RECEIVED",
        "resolution_mode": None,
    }
    trace.record("CASE_CREATED", MANAGER_AGENT, customer_id=customer_id, state="RECEIVED")

    _transition(store, trace, case_id, "IDENTIFYING_ORDER")
    trace.record(
        "CUSTOMER_MESSAGE_RECEIVED",
        FRONTLINE_AGENT,
        message_event_id="MSG-001",
        text=INITIAL_MESSAGE,
    )
    trace.record("SKILL_CALLED", FRONTLINE_AGENT, skill="identify-hotel-order")
    initial_match = resolve_order_reference(store, customer_id, {}, trace)
    if initial_match["status"] != "MULTIPLE":
        raise RuntimeError("Golden fixture must initially produce MULTIPLE")
    trace.record(
        "CUSTOMER_INFO_REQUESTED",
        FRONTLINE_AGENT,
        message="请提供酒店名称和入住日期，我会在你的订单范围内继续查询。",
        missing_fields=initial_match["missing_fields"],
    )
    _transition(store, trace, case_id, "AWAITING_CUSTOMER_INFO")

    trace.record(
        "CUSTOMER_INFO_RECEIVED",
        FRONTLINE_AGENT,
        message_event_id="MSG-002",
        text=FOLLOW_UP_MESSAGE,
    )
    _transition(store, trace, case_id, "IDENTIFYING_ORDER")
    match = resolve_order_reference(
        store,
        customer_id,
        {
            "hotel_name": "上海虹桥海湾花园酒店",
            "check_in_date": "2026-08-15",
        },
        trace,
    )
    if match["status"] != "UNIQUE" or not match["ownership_verified"]:
        raise RuntimeError("Golden fixture must resolve to one authorized order")

    _transition(store, trace, case_id, "RESOLVING")
    trace.record(
        "ORDER_LINKED_HANDOFF",
        FRONTLINE_AGENT,
        receiver=RESOLUTION_AGENT,
        order_ref=match["order_ref"],
        ownership_verified=match["ownership_verified"],
        matched_fields=match["matched_fields"],
    )
    trace.record(
        "SKILL_CALLED",
        RESOLUTION_AGENT,
        skill="investigate-hotel-supply-exception",
    )
    context = get_authorized_order(store, customer_id, match["order_ref"], trace)
    plan = create_resolution_plan(store, match["order_ref"], context)
    trace.record("RESOLUTION_PLAN_CREATED", RESOLUTION_AGENT, result=plan)
    risk = evaluate_rebooking(store, customer_id, match["order_ref"], plan, trace)
    if risk["decision"] != "REQUIRE_CUSTOMER_CONFIRMATION":
        raise RuntimeError("Golden fixture must require customer confirmation")
    trace.record(
        "RESOLUTION_PLAN_HANDOFF",
        RESOLUTION_AGENT,
        receiver=FRONTLINE_AGENT,
        resolution_plan_id=plan["resolution_plan_id"],
        risk_decision_id=risk["risk_decision_id"],
        price_difference_cny=plan["price_difference_cny"],
        required_controls=risk["required_controls"],
    )

    _transition(store, trace, case_id, "AWAITING_CUSTOMER_CONFIRMATION")
    trace.record(
        "CUSTOMER_CONFIRMATION_RECEIVED",
        FRONTLINE_AGENT,
        message_event_id="MSG-003",
        text=CONFIRMATION_MESSAGE,
    )
    record_customer_confirmation(
        store,
        case_id,
        plan["resolution_plan_id"],
        risk["risk_decision_id"],
        "MSG-003",
        trace,
    )

    _transition(store, trace, case_id, "EXECUTING")
    idempotency_key = "CASE-GOLDEN-001-REBOOK"
    execute_rebooking(
        store,
        case_id,
        plan["resolution_plan_id"],
        risk["risk_decision_id"],
        idempotency_key,
        trace,
    )

    _transition(store, trace, case_id, "VERIFYING")
    verification_payload = {
        "package_id": f"VP-{case_id}",
        "case_id": case_id,
        "customer_id": customer_id,
        "order_ref": match["order_ref"],
        "resolution_plan_snapshot": {
            field: plan[field]
            for field in (
                "resolution_plan_id",
                "order_ref",
                "order_id",
                "replacement_hotel_id",
                "check_in_date",
                "check_out_date",
                "previous_confirmation_number",
                "expected_target_status",
            )
        },
        "expected_result": {
            "order_status": "REBOOKED",
            "replacement_hotel_id": plan["replacement_hotel_id"],
        },
        "bdd_assertions": [
            "The authorized order is REBOOKED.",
            "The replacement hotel and stay dates match the frozen plan.",
        ],
        "evidence_refs": [f"trace://{case_id}/resolution-plan"],
        "package_version": "v0.1",
    }
    verification_package = freeze_verification_package(
        verification_payload, "2026-08-14T00:00:00+08:00"
    )
    if not verify_package_hash(verification_package):
        raise RuntimeError("Golden fixture verification package must have a valid hash")
    trace.record(
        "VERIFICATION_PACKAGE_FROZEN",
        MANAGER_AGENT,
        package_id=verification_package["package_id"],
        package_sha256=verification_package["sha256"],
    )
    trace.record("SKILL_CALLED", VERIFICATION_AGENT, skill="verify-hotel-rebooking")
    verification_plan = {
        **verification_package["resolution_plan_snapshot"],
        "expected_current_status": "CONFIRMED",
    }
    get_order_state(store, customer_id, verification_plan["order_ref"], trace)
    verification = verify_rebooking(store, customer_id, verification_plan, idempotency_key, trace)
    if verification["verification_status"] != "PASSED":
        _transition(store, trace, case_id, "MANUAL_REQUIRED")
        raise RuntimeError("Golden Path verification failed")
    trace.record(
        "VERIFICATION_PACKAGE_VERIFIED",
        VERIFICATION_AGENT,
        package_id=verification_package["package_id"],
        package_hash_valid=True,
        verification_status=verification["verification_status"],
    )

    _transition(store, trace, case_id, "NOTIFYING_CUSTOMER")
    actual_order = get_authorized_order(store, customer_id, match["order_ref"])["order"]
    trace.record(
        "CUSTOMER_NOTIFIED",
        FRONTLINE_AGENT,
        message=(
            f"已改订至{actual_order['hotel_name']}，"
            f"入住日期{actual_order['check_in_date']}，"
            f"新确认号{actual_order['confirmation_number']}。"
        ),
        delivery_status="SENT",
    )
    _transition(store, trace, case_id, "RESOLVED")
    case = store["cases"][case_id]
    case["resolution_mode"] = "AUTONOMOUS"
    trace.record("CASE_RESOLVED", MANAGER_AGENT, resolution_mode="AUTONOMOUS")

    case_card = {
        "case_id": case_id,
        "case_type": "HOTEL_SUPPLY_EXCEPTION",
        "customer_id": customer_id,
        "order_id": plan["order_id"],
        "diagnosis": plan["diagnosis"],
        "action": plan["action"],
        "replacement_hotel_id": plan["replacement_hotel_id"],
        "price_difference_cny": plan["price_difference_cny"],
        "verification_status": verification["verification_status"],
        "resolution_mode": case["resolution_mode"],
    }
    trace.record("CASE_CARD_WRITTEN", MANAGER_AGENT, result=case_card)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    trace.write_jsonl(output_path / "golden-trace.jsonl")
    (output_path / "golden-case-card.json").write_text(
        json.dumps(case_card, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    final_result = {
        "case_id": case_id,
        "case_state": case["case_state"],
        "resolution_mode": case["resolution_mode"],
        "internal_human_interventions": 0,
        "linked_order_id": actual_order["order_id"],
        "order_state": actual_order["status"],
        "replacement_hotel_id": actual_order["hotel_id"],
        "price_difference_cny": plan["price_difference_cny"],
        "confirmation_number": actual_order["confirmation_number"],
        "verification_status": verification["verification_status"],
        "verification_package_hash_valid": verify_package_hash(verification_package),
        "notification_status": "SENT",
        "case_card_status": "WRITTEN",
    }
    (output_path / "golden-result.json").write_text(
        json.dumps(final_result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return final_result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "fixture",
        nargs="?",
        default=Path(__file__).parent / "fixtures" / "golden-case.json",
        type=Path,
    )
    parser.add_argument(
        "--output-dir",
        default=Path(__file__).parent / "artifacts",
        type=Path,
    )
    args = parser.parse_args()
    result = run_golden_path(args.fixture, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
