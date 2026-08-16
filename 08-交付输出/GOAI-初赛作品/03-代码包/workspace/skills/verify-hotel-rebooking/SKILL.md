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
## Verification Result format

Verification does not join or write to Project Room. Return one strict Result
to Manager in the dedicated Verification Room. Manager validates this Result
before it may publish a separate summary to Project Room:

```json
{
  "event_type": "VERIFICATION_RESULT",
  "business_event_id": "<business_event_id>",
  "case_id": "<case_id>",
  "incident_sequence": 1,
  "sender_agent": "VERIFICATION",
  "verification_result_id": "<verification_result_id>",
  "verification_status": "PASSED",
  "evidence_ref": "verification-result://<verification_result_id>",
  "differences": [],
  "occurred_at": "<RFC3339 timestamp>"
}
```

Return this one JSON object only. Do not add an acknowledgement, explanation,
Markdown fence, Verification Package, Tool transcript, or reasoning.

For `FAILED`, set `verification_status` to `FAILED` and include every failed
check name in `differences`. Never return `PASSED` with non-empty differences.

Do not copy the Verification Package, reasoning, Tool payloads, credentials, execution response, or customer-sensitive data into the Result.
