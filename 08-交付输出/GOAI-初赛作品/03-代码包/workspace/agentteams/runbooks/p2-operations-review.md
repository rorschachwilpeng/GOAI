# P2 Operations Review Room runbook

## Scope

This runbook covers the synthetic 800 CNY high-risk rebooking review only. Resolution receives `P2_REVIEW_START` and a matching Hotel Operations decision in its dedicated Operations Review Room. It must use only `mcp-goai-resolution` to investigate, create the plan and risk decision, record the internal decision, and validate authorization.

## Boundaries

- Hotel Operations is simulated by the Matrix admin account and supplies the structured `APPROVE` or `REJECT` decision.
- The decision must bind the current `case_id`, `resolution_plan_id`, `risk_decision_id`, `operator_id`, and the original Matrix decision event ID.
- `APPROVE` may result in `authorized=true`, but P2 always has `execution_enabled=false`; Resolution must not call `execute_rebooking`.
- `REJECT` must result in `INTERNAL_APPROVAL_REJECTED`; Resolution stops without attempting an execution.
- The Case Project Room remains a P1 boundary: only an actual Frontline `ORDER_LINKED` may supply an order reference there. Admin and Manager must not inject order or plan data into that room.

## Evidence procedure

1. Reset only the synthetic Mock state before each independent decision branch.
2. Send a structured, mentioned `P2_REVIEW_START` to Resolution's Operations Review Room.
3. Wait for Resolution's real Matrix sender to publish a fresh 800 CNY plan, risk decision and review request.
4. Send the simulated Hotel Operations decision, then a structured binding event containing that decision event ID.
5. Preserve a credential-free, selected Matrix event extract and the Mock order-state result.

## Truthfulness

The Room interaction, Resolution sender, role MCP calls, decision binding, and authorization decisions are **implemented** in AgentTeams. Order data and all backend effects are **Mock execution** using synthetic data. P2 deliberately does not execute a high-risk rebooking.
