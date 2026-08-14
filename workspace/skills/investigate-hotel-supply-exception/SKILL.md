---
name: investigate-hotel-supply-exception
description: Diagnose an authorized hotel supply exception, produce an evidence-backed rebooking plan, obtain a deterministic risk decision, and request controlled execution. Use after one hotel order has been safely linked to the authenticated customer.
assign_when: Assign to an investigation and resolution worker handling diagnosis, rebooking planning, risk evaluation, and authorized execution.
---

# Investigate Hotel Supply Exception

## Required input

- Trusted `customer_id`, `case_id`, and opaque `order_ref` from the Manager.
- For execution: the frozen `resolution_plan_id`, `risk_decision_id`, and a unique `idempotency_key`.

Do not accept a raw order ID or expand the authorized customer scope.

## Diagnose and plan

1. Call `mcp-goai-order.get_authorized_order` with `customer_id` and `order_ref`.
2. Require structured supplier-exception evidence and at least one eligible rebooking option. If either is missing, stop and report the Tool error or evidence gap.
3. Build one flat structured Resolution Plan from returned evidence. It MUST contain exactly the contract fields accepted by `evaluate_rebooking`: `resolution_plan_id`, `order_ref`, `order_id`, `action`, `diagnosis`, `evidence_ids`, `replacement_hotel_id`, `replacement_hotel_name`, `check_in_date`, `check_out_date`, `price_difference_cny`, `previous_confirmation_number`, `expected_current_status`, and `expected_target_status`. Copy those values from the authorized order, supplier exception, and selected eligible option. Do not nest source objects and do not invent availability, price, or policy.
4. Call `mcp-goai-order.evaluate_rebooking` with the complete plan.
5. Return the diagnosis, evidence, Resolution Plan, and Risk Decision to the Manager.

## Controlled execution

- `REQUIRE_CUSTOMER_CONFIRMATION`: continue only when the Manager supplies a trusted customer confirmation `message_event_id`. First call `mcp-goai-order.record_customer_confirmation` to bind it to this Case, plan, and risk decision. Otherwise stop after planning.
- `REQUIRE_INTERNAL_APPROVAL`: stop and request internal approval. Never treat customer confirmation as internal approval.
- `DENY`: stop. Do not propose or attempt a bypass.

When a valid confirmation record exists and the Manager requested execution:

1. Call `mcp-goai-order.validate_execution_authorization` with the bound Case, plan, and risk decision.
2. Continue only if the Tool returns `authorized=true`.
3. Call `mcp-goai-order.execute_rebooking` once with the same IDs and the supplied `idempotency_key`.
4. Return the Execution Record to the Manager without claiming the order is resolved. Verification is a separate Agent's responsibility.

## Safety rules

- The only allowed business endpoints are the named `mcp-goai-order` Tools in this Skill. Do not call Higress configuration or admin APIs, inspect MCP server configuration, scan hosts or ports, discover container networks, or call the Mock HTTP backend directly.
- Do not run `mcporter list` or request Tool schemas during a task. The Tool names and sequence in this Skill are the contract.
- If an MCP Tool rejects the payload, report the exact Tool error and stop. Do not search for an alternate endpoint or bypass MCP.
- Never approve a plan, create an approval record, or reinterpret a risk decision.
- Never infer customer confirmation from conversational wording; rely on the Tool-bound confirmation record.
- Never change an order outside `execute_rebooking` or retry with a new idempotency key after an uncertain result.
- Never claim execution succeeded from model reasoning. Preserve the Tool result and hand off to independent verification.
