---
name: verify-hotel-rebooking
description: Independently read back a rebooked hotel order, compare actual state with the frozen Resolution Plan, and produce a Verification Result and Case Card. Use after an execution attempt, including success, timeout, or unknown outcomes.
assign_when: Assign to the Verification Agent after the Manager freezes a valid Verification Package for independent read-only validation.
---

# Verify Hotel Rebooking

## Required input

- A valid frozen Verification Package from the Manager containing trusted
  `customer_id`, `case_id`, opaque `order_ref`, the Resolution Plan snapshot,
  and execution `idempotency_key`.

The Manager/Control Plane must use T003's deterministic `verify_package_hash`
function before dispatch and mark the Package valid. Do not calculate, infer,
or guess the hash yourself. If the Package is missing or not marked valid, you
must stop without calling an order Tool.

## Independent verification

1. Ignore all execution-side context when deciding success; use only the
   frozen Package's allowed expected values and the independent readback.
2. Call `mcp-goai-verification.get_order_state` with `customer_id` and `order_ref`.
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

- Use only the read-only `mcp-goai-verification.get_order_state` Tool. Never call execution, confirmation, approval, or order-write Tools.
- You must not join the Case Project Room or receive its discussion transcript.
- Never repair or reinterpret a mismatch. Report it exactly.
- Never mark a Case resolved, claim the customer was notified, or hide failed checks.
- Never use an unverified order state or candidate-order information.
