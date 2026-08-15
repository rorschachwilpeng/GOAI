# P1 Golden Case Runbook

## Runtime entry and evidence boundary

Use only synthetic customer `C001` and the local Mock service. The test harness may send customer messages as admin and read Matrix events; it must not impersonate a Worker or call a role MCP Tool.

For a Case Project Room, Frontline publishes `ORDER_LINKED` directly to Resolution. Resolution publishes its plan directly to Frontline. Verification remains outside the Project Room and receives only a frozen package.

The platform Manager remains a Room member. For a Case Project Room, its runtime Matrix override disables inbound automatic replies (`allow: false`, `requireMention: true`, `autoReply: false`); deterministic control-plane state changes and necessary outgoing notifications remain allowed.

## RUN-003 procedure

1. Initialize `CASE-GOLDEN-002` / `proj-goai-case-golden-002`; mention Frontline and Resolution only to establish their Room sessions.
2. Send C001's initial message, then hotel name and date. Frontline performs `MULTIPLE → UNIQUE` and sends `ORDER_LINKED` with the opaque ref only to the Project Room.
3. Resolution uses its MCP surface to plan the 180 CNY rebooking and request confirmation. Frontline records the customer's real Matrix confirmation event.
4. Resolution validates authorization and performs one idempotent Mock rebooking.
5. The deterministic control plane creates and verifies the frozen Verification Package. Manager sends it to the isolated Verification Room. Verification accepts the control-plane `valid=true` hash result and performs only its two read Tools.
6. On `PASSED`, Frontline notifies the customer and the deterministic CaseStore closes the Case.

## Truthfulness

- **已实现**: real AgentTeams Matrix senders, Project Room handoff, role MCP calls, isolated Verification read-back, and deterministic package hash verification.
- **模拟执行**: hotel order lookup and rebooking use the local synthetic Mock API.
- **方案设计 / 后续规划**: no production supplier, customer, or payment system is represented.
