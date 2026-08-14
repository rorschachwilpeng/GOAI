---
name: verify-hotel-rebooking
description: Independently read back a rebooked hotel order, compare actual state with the frozen Resolution Plan, and produce a Verification Result and Case Card. Use after an execution attempt, including success, timeout, or unknown outcomes.
assign_when: Assign to a verification worker that independently validates hotel rebooking results and prepares auditable closure evidence.
---

# Verify Hotel Rebooking

## Required input

- Trusted `customer_id`, `case_id`, and opaque `order_ref` from the Manager.
- The frozen Resolution Plan and execution `idempotency_key`.
- The Risk Decision and Execution Record for trace context only; do not treat them as proof of success.

## Independent verification

1. Ignore the execution Tool's reported status when deciding success.
2. Call `mcp-goai-order.get_order_state` with `customer_id` and `order_ref`.
3. Compare the returned order with the frozen plan. All checks must pass:
   - target order matches;
   - customer ownership is unchanged;
   - replacement hotel matches;
   - check-in and check-out dates match;
   - order status equals the expected target status;
   - a new confirmation number exists;
   - the stored idempotency key matches.
4. Return `verification_status=PASSED` only when every check passes. Otherwise return `FAILED`, list exact `differences`, and recommend `MANUAL_REQUIRED`.

## Case Card

Only after verification passes, return a Case Card with:

- `case_id`, `case_type=HOTEL_SUPPLY_EXCEPTION`, `customer_id`, and verified `order_id`;
- diagnosis, action, replacement hotel, and price difference from the frozen plan;
- `verification_status=PASSED` and `resolution_mode=AUTONOMOUS`.

The Case Card is an output artifact, not a knowledge-memory write. The Manager decides whether customer notification succeeded and whether the Case may enter `RESOLVED`.

## Safety rules

- Use only the read-only `get_order_state` Tool. Never call execution, confirmation, approval, or order-write Tools.
- Never repair or reinterpret a mismatch. Report it exactly.
- Never mark a Case resolved, claim the customer was notified, or hide failed checks.
- Never use an unverified order state or candidate-order information.

