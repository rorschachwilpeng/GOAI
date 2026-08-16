# P2 internal approval run evidence

## Scope and result

This evidence records two independent synthetic 800 CNY high-risk Operations Review Room branches. The Room is dedicated to Resolution and simulated Hotel Operations; it is not the P1 Case Project Room.

| Branch | Case | Decision | Authorization result | Order write |
| --- | --- | --- | --- | --- |
| APPROVE | `CASE-P2-APPROVE-003` | `APPROVE` | `authorized=true`, `execution_enabled=false` | none |
| REJECT | `CASE-P2-REJECT-002` | `REJECT` | `INTERNAL_APPROVAL_REJECTED` | none |

The selected credential-free real Matrix event extract is [room-events.jsonl](room-events.jsonl). Each decision artifact binds the original simulated Hotel Operations Matrix decision event with the fresh case, plan and risk identifiers: [approve-decision.json](approve-decision.json) and [reject-decision.json](reject-decision.json). The final synthetic Mock order state is [order-state.json](order-state.json), with `status=CONFIRMED`.

## Procedure

1. Resolution received a structured `P2_REVIEW_START` in its Operations Review Room and used its role MCP to produce a fresh 800 CNY plan, risk decision and review request.
2. Admin simulated Hotel Operations by sending a structured decision and a separate binding event carrying the actual decision Matrix event ID.
3. Resolution, as the real Matrix sender, bound the APPROVE/REJECT decision through `record_internal_decision` and performed `validate_execution_authorization`.
4. The Mock state was reset between the two branches. The REJECT branch used a fresh synthetic order-reference setup and a new case, plan, risk and decision event.

## Truthfulness

- **已实现**：AgentTeams Operations Review Room routing, Resolution's real Matrix sender, role-MCP plan/risk generation, decision binding and authorization checks.
- **模拟执行**：the backend is the local synthetic Mock service. No high-risk rebooking was executed; APPROVE is deliberately authorization-only and REJECT is denied.
- **方案设计 / 后续规划**：production approval identity, durable enterprise audit retention and real supplier execution are outside this run.

## Safety notes

No API key, access token, password, cookie, hidden reasoning or raw session data is included. The first rejected start (`CASE-P2-REJECT-001`) stopped at the authorization gate after the Mock reset invalidated its prior opaque reference; it is diagnostic only and is intentionally excluded from the two branch results above.
