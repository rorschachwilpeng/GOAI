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
    load_fixture,
    record_customer_confirmation,
    resolve_order_reference,
    verify_rebooking,
)


INITIAL_MESSAGE = "酒店说查不到我的预订，请帮我处理。"
FOLLOW_UP_MESSAGE = "上海虹桥海湾花园酒店，8月15日入住，8月17日离店。"
CONFIRMATION_MESSAGE = "确认改订"


def _transition(store: dict, trace: TraceRecorder, case_id: str, state: str) -> None:
    previous = store["cases"][case_id]["case_state"]
    store["cases"][case_id]["case_state"] = state
    trace.record("CASE_STATE_CHANGED", "Manager Agent", previous=previous, current=state)


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
    trace.record("CASE_CREATED", "Manager Agent", customer_id=customer_id, state="RECEIVED")

    _transition(store, trace, case_id, "IDENTIFYING_ORDER")
    trace.record(
        "CUSTOMER_MESSAGE_RECEIVED",
        "Manager Agent",
        message_event_id="MSG-001",
        text=INITIAL_MESSAGE,
    )
    trace.record("SKILL_CALLED", "Intake & Order Matching Agent", skill="identify-hotel-order")
    initial_match = resolve_order_reference(store, customer_id, {}, trace)
    if initial_match["status"] != "MULTIPLE":
        raise RuntimeError("Golden fixture must initially produce MULTIPLE")
    trace.record(
        "CUSTOMER_INFO_REQUESTED",
        "Intake & Order Matching Agent",
        message="请提供酒店名称和入住日期，我会在你的订单范围内继续查询。",
        missing_fields=initial_match["missing_fields"],
    )
    _transition(store, trace, case_id, "AWAITING_CUSTOMER_INFO")

    trace.record(
        "CUSTOMER_INFO_RECEIVED",
        "Manager Agent",
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
        "SKILL_CALLED",
        "Investigation & Resolution Agent",
        skill="investigate-hotel-supply-exception",
    )
    context = get_authorized_order(store, customer_id, match["order_ref"], trace)
    plan = create_resolution_plan(store, match["order_ref"], context)
    trace.record("RESOLUTION_PLAN_CREATED", "Investigation & Resolution Agent", result=plan)
    risk = evaluate_rebooking(store, customer_id, match["order_ref"], plan, trace)
    if risk["decision"] != "REQUIRE_CUSTOMER_CONFIRMATION":
        raise RuntimeError("Golden fixture must require customer confirmation")

    _transition(store, trace, case_id, "AWAITING_CUSTOMER_CONFIRMATION")
    trace.record(
        "CUSTOMER_CONFIRMATION_RECEIVED",
        "Manager Agent",
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
    trace.record("SKILL_CALLED", "Verification Agent", skill="verify-hotel-rebooking")
    verification = verify_rebooking(store, customer_id, plan, idempotency_key, trace)
    if verification["verification_status"] != "PASSED":
        _transition(store, trace, case_id, "MANUAL_REQUIRED")
        raise RuntimeError("Golden Path verification failed")

    _transition(store, trace, case_id, "NOTIFYING_CUSTOMER")
    actual_order = get_authorized_order(store, customer_id, match["order_ref"])["order"]
    trace.record(
        "CUSTOMER_NOTIFIED",
        "Manager Agent",
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
    trace.record("CASE_RESOLVED", "Manager Agent", resolution_mode="AUTONOMOUS")

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
    trace.record("CASE_CARD_WRITTEN", "Verification Agent", result=case_card)

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
