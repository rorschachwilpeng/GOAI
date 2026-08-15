---
name: investigate-hotel-supply-exception
description: Diagnose an authorized hotel supply exception, produce an evidence-backed rebooking plan, obtain a deterministic risk decision, and request controlled execution. Use after one hotel order has been safely linked to the authenticated customer.
assign_when: Assign to the Resolution Agent after the Frontline Agent has published an authorized opaque order reference in the Case Project Room.
---

# Investigate Hotel Supply Exception

## Required input

- Trusted `customer_id`, `case_id`, and opaque `order_ref` from the Frontline
  Agent's structured Case Project Room handoff.
- For execution: the frozen `resolution_plan_id`, `risk_decision_id`, and a unique `idempotency_key`.

Do not accept a raw order ID or expand the authorized customer scope.

## Diagnose and plan

1. Call `mcp-goai-resolution.get_authorized_order` with `customer_id` and `order_ref`.
2. Require structured supplier-exception evidence and at least one eligible rebooking option. If either is missing, stop and report the Tool error or evidence gap.
3. Build one flat structured Resolution Plan from returned evidence. It MUST contain exactly the contract fields accepted by `evaluate_rebooking`: `resolution_plan_id`, `order_ref`, `order_id`, `action`, `diagnosis`, `evidence_ids`, `replacement_hotel_id`, `replacement_hotel_name`, `check_in_date`, `check_out_date`, `price_difference_cny`, `previous_confirmation_number`, `expected_current_status`, and `expected_target_status`. Copy those values from the authorized order, supplier exception, and selected eligible option. Do not nest source objects and do not invent availability, price, or policy.
4. Call `mcp-goai-resolution.evaluate_rebooking` with the complete plan.
5. Publish the diagnosis, evidence, Resolution Plan, and Risk Decision directly
   to the Case Project Room for the Frontline Agent. Do not require Manager to
   relay this business handoff.

## Controlled execution

- `REQUIRE_CUSTOMER_CONFIRMATION`: stop after planning until the Frontline Agent
  publishes the trusted confirmation record in the Case Project Room.
- `REQUIRE_INTERNAL_APPROVAL`: stop and request internal approval. Never treat customer confirmation as internal approval.
- `DENY`: stop. Do not propose or attempt a bypass.

When a valid confirmation record exists and the Case state allows execution:

1. Call `mcp-goai-resolution.validate_execution_authorization` with the bound Case, plan, and risk decision.
2. Continue only if the Tool returns `authorized=true`.
3. Call `mcp-goai-resolution.execute_rebooking` once with the same IDs and the supplied `idempotency_key`.
4. Publish the Execution Record to the Case Project Room without claiming the order is resolved. Verification is a separate Agent's responsibility.

## P2 Operations Review exception

Only in the dedicated Operations Review Room, an admin-mention
`P2_REVIEW_START` may initiate the synthetic 800 CNY review Case. It is not a
Case Project Room handoff and does not relax that Room's Frontline-only
`ORDER_LINKED` requirement.

1. Use its trusted `case_id`, `customer_id`, and opaque `order_ref` to call
   `mcp-goai-resolution.get_authorized_order`. For this explicit synthetic P2
   test only, set the flat plan's `price_difference_cny` to the assigned 800
   CNY review value, then call `evaluate_rebooking`.
2. Publish the current Case, plan, risk reason, SLA, and requested
   `APPROVE | REJECT` decision in the Operations Review Room. Do not execute a
   rebooking.
3. Accept `APPROVE` or `REJECT` only from the same admin in that Room after
   the current plan and risk IDs exist. A structured `P2_DECISION_EVENT_ID`
   supplies the exact `message_event_id`; use that field directly. Before
   calling `mcp-goai-resolution.record_internal_decision`, require its
   `case_id`, `resolution_plan_id`, `risk_decision_id`, `decision`, and
   `operator_id` to match the current review context. If any field is missing
   or inconsistent, state the exact missing or mismatched field and stop.
   Never search local logs, sessions, Tool schemas, containers, or other
   messages to infer an event ID.
4. For `APPROVE`, report that authorization is valid but
   `execution_enabled=false`. For `REJECT`, report that authorization remains
   blocked. Never call `execute_rebooking` for either P2 outcome.

## Safety rules

- The only allowed business endpoints are the named `mcp-goai-resolution` Tools in this Skill. Do not call Higress configuration or admin APIs, inspect MCP server configuration, scan hosts or ports, discover container networks, or call the Mock HTTP backend directly.
- Do not run `mcporter list` or request Tool schemas during a task. The Tool names and sequence in this Skill are the contract.
- If an MCP Tool rejects the payload, report the exact Tool error and stop. Do not search for an alternate endpoint or bypass MCP.
- Never approve a plan or reinterpret a risk decision. Only record the
  external admin's bound APPROVE or REJECT through the P2 Operations Review
  exception above.
- Never infer customer confirmation from conversational wording; rely on the Tool-bound confirmation record.
- Never change an order outside `execute_rebooking` or retry with a new idempotency key after an uncertain result.
- Never claim execution succeeded from model reasoning. Preserve the Tool result and hand off to independent verification.
