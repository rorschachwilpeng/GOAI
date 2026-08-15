# MCP Tool Contracts

## 1. 状态与口径

| 字段 | 内容 |
|---|---|
| 文档状态 | Draft — Linked Journey Revision |
| 日期 | 2026-08-15 |
| 当前基线 | 9 个 Tool、3 个角色化 MCP Surface、同一 Python Mock HTTP 后端 |
| 本次目标变更 | 高风险双重授权执行、连续两轮改订、客户隔离消息投影 |

统一错误响应：

```json
{"error": {"code": "MACHINE_READABLE_CODE", "message": "Human-readable message"}}
```

真实性标签：

- `已实现`：当前代码与测试已存在。
- `目标变更，待实现`：本轮文档确认后进入新 Tasks。

## 2. 角色化 Surface

| Surface | Tool | 当前状态 |
|---|---|---|
| Frontline | `resolve_order_reference`、`record_customer_confirmation` | 已实现 |
| Resolution | `get_authorized_order`、`evaluate_rebooking`、`record_internal_decision`、`validate_execution_authorization`、`execute_rebooking` | 已实现基线；双重授权待改 |
| Verification | `get_order_state`、`verify_rebooking` | 已实现 |
| Manager | 无业务 Tool | 已实现为权限约束 |

Agent Identity 决定能够发现和调用哪些 Tool；Skill 文案或自然语言消息不能授予额外权限。

## 3. Frontline Surface

### `resolve_order_reference`（已实现）

请求：

```json
{"customer_id": "C001", "clues": {"hotel_name": "string?", "check_in_date": "YYYY-MM-DD?"}}
```

响应为三选一：

```json
{"status": "NONE", "missing_fields": ["hotel_name", "check_in_date"], "candidates": []}
```

```json
{"status": "MULTIPLE", "candidate_count": 2, "missing_fields": ["hotel_name", "check_in_date"], "candidates": []}
```

```json
{"status": "UNIQUE", "order_ref": "oref_...", "ownership_verified": true, "matched_fields": ["hotel_name", "check_in_date"]}
```

安全约束：仅在 `customer_id` 范围内匹配；`NONE` / `MULTIPLE` 不返回候选订单详情。

### `record_customer_confirmation`（已实现；高风险复用待验收）

请求：

```json
{
  "case_id": "CASE-GOLDEN-001",
  "resolution_plan_id": "PLAN-GOLDEN-002",
  "risk_decision_id": "RISK-PLAN-GOLDEN-002",
  "message_event_id": "MSG-CUSTOMER-007"
}
```

响应字段：`confirmation_id`、`case_id`、`customer_id`、`resolution_plan_id`、`risk_decision_id`、`message_event_id`、`confirmed=true`、`recorded_at`。

主要错误：`CONFIRMATION_CONTEXT_INVALID`、`ORDER_ACCESS_DENIED`。旧方案、其他 Case 或其他客户的确认不得复用。

## 4. Resolution Surface

### `get_authorized_order`（已实现）

请求：

```json
{"customer_id": "C001", "order_ref": "oref_..."}
```

响应：`order`、`supplier_exceptions[]`、`eligible_rebooking_options[]`。只有不透明引用属于当前客户时才能返回完整内容。

### `evaluate_rebooking`（已实现基线；高风险控制列表待改）

请求中的 `resolution_plan` 必须包含：

`resolution_plan_id`、`order_ref`、`order_id`、`action`、`diagnosis`、`evidence_ids`、`replacement_hotel_id`、`replacement_hotel_name`、`check_in_date`、`check_out_date`、`price_difference_cny`、`previous_confirmation_number`、`expected_current_status`、`expected_target_status`。

180 元低风险响应：

```json
{
  "risk_decision_id": "RISK-PLAN-GOLDEN-001",
  "resolution_plan_id": "PLAN-GOLDEN-001",
  "decision": "REQUIRE_CUSTOMER_CONFIRMATION",
  "rule_version": "rebooking-v0.2",
  "reason_code": "PRICE_DIFF_WITHIN_300",
  "required_controls": ["CUSTOMER_CONFIRMATION"],
  "valid": true
}
```

800 元高风险目标响应：

```json
{
  "risk_decision_id": "RISK-PLAN-GOLDEN-002",
  "resolution_plan_id": "PLAN-GOLDEN-002",
  "decision": "REQUIRE_INTERNAL_APPROVAL",
  "rule_version": "rebooking-v0.2",
  "reason_code": "PRICE_DIFF_ABOVE_300",
  "required_controls": ["INTERNAL_APPROVAL", "CUSTOMER_CONFIRMATION"],
  "valid": true
}
```

`decision` 仅允许 `REQUIRE_CUSTOMER_CONFIRMATION | REQUIRE_INTERNAL_APPROVAL | DENY`。主要错误：`ORDER_ACCESS_DENIED`、`ORDER_PLAN_MISMATCH`。

### `record_internal_decision`（已实现；语义待改）

请求：

```json
{
  "case_id": "CASE-GOLDEN-001",
  "resolution_plan_id": "PLAN-GOLDEN-002",
  "risk_decision_id": "RISK-PLAN-GOLDEN-002",
  "decision": "APPROVE",
  "message_event_id": "MSG-OPS-002",
  "operator_id": "hotel-operations-demo"
}
```

响应字段：`internal_decision_id`、请求绑定字段、`recorded_at`。

约束：

- `APPROVE` 只满足 `INTERNAL_APPROVAL`，不得自动触发写入。
- `REJECT` 使授权校验返回 `INTERNAL_APPROVAL_REJECTED`。
- 决定必须绑定当前 Case、当前方案、当前风险决定、运营人员和消息事件。

主要错误：`INTERNAL_DECISION_CONTEXT_INVALID`、`INVALID_INTERNAL_DECISION`、`INTERNAL_DECISION_CONFLICT`。

### `validate_execution_authorization`（已实现基线；双重授权待改）

请求：

```json
{"case_id": "string", "resolution_plan_id": "string", "risk_decision_id": "string"}
```

目标成功响应：

```json
{
  "authorized": true,
  "execution_enabled": true,
  "risk_decision_id": "RISK-PLAN-GOLDEN-002",
  "satisfied_controls": ["INTERNAL_APPROVAL", "CUSTOMER_CONFIRMATION"]
}
```

执行前必须重新校验：Case/方案/风险绑定、风险决定有效期、订单当前状态、运营决定、客户确认和所有 `required_controls`。

主要错误：`EXECUTION_CONTEXT_INVALID`、`ORDER_STATE_CONFLICT`、`CUSTOMER_CONFIRMATION_REQUIRED`、`INTERNAL_APPROVAL_REQUIRED`、`INTERNAL_APPROVAL_REJECTED`、`EXECUTION_DENIED`。

### `execute_rebooking`（已实现基线；高风险目标行为待改）

请求：

```json
{
  "case_id": "string",
  "resolution_plan_id": "string",
  "risk_decision_id": "string",
  "idempotency_key": "string"
}
```

响应字段：`execution_id`、`case_id`、`resolution_plan_id`、`risk_decision_id`、`order_id`、`reported_status`、`confirmation_number`、`idempotency_key`、`idempotent_replay`。

目标行为：

- 180 元方案在有效客户确认后允许执行。
- 800 元方案仅在内部 `APPROVE` 与客户确认都有效时允许执行。
- 每轮使用独立 `resolution_plan_id`、`risk_decision_id` 和 `idempotency_key`。
- 同一幂等键的同一请求返回原记录并标记 `idempotent_replay=true`；不同绑定返回 `IDEMPOTENCY_KEY_CONFLICT`。
- 当前代码仍以 `HIGH_RISK_EXECUTION_NOT_ENABLED` 阻断高风险写入；该限制只属于改造前基线，完成新任务后删除。

## 5. Verification Surface

### `get_order_state`（已实现，只读）

请求：

```json
{"customer_id": "C001", "order_ref": "oref_..."}
```

返回当前实际 Order 对象。主要错误：`ORDER_ACCESS_DENIED`、`NOT_FOUND`。

### `verify_rebooking`（已实现；连续两次调用待验收）

请求：

```json
{"customer_id": "C001", "resolution_plan_id": "PLAN-GOLDEN-002", "idempotency_key": "CASE-GOLDEN-001-INCIDENT-2-REBOOK"}
```

响应：

```json
{
  "verification_status": "PASSED | FAILED",
  "order_id": "H-C001-001",
  "checks": {
    "target_order_matches": true,
    "ownership_unchanged": true,
    "replacement_hotel_matches": true,
    "stay_dates_match": true,
    "order_status_matches": true,
    "confirmation_number_exists": true,
    "idempotency_key_matches": true
  },
  "differences": []
}
```

Verification 不得写订单、修改方案或把执行返回值当作核验事实。两轮订单写入必须分别独立调用并保存结果。

## 6. 非 MCP：客户消息投影契约（目标变更，待实现）

Customer Chat Facade 通过本地 Conversation API 读写允许客户看到的消息，不直接访问 Matrix、Project Room 或 MCP。

允许字段：

```json
{
  "message_id": "string",
  "conversation_id": "string",
  "case_id": "string",
  "sender": "CUSTOMER | FRONTLINE",
  "message_type": "TEXT | PLAN | STATUS | RESULT",
  "body": "string",
  "occurred_at": "RFC3339 timestamp"
}
```

禁止输出：Agent 隐藏推理、Project Room 消息、Tool 名称和参数、MCP 响应、内部风险规则细节、运营人员身份细节、其他客户订单信息。

## 7. Gateway 与审计不变量

1. MCP Gateway 按 Agent Identity 暴露对应 Surface；未授权 Tool 不应被发现。
2. 自然语言消息不能授予 Tool 权限。
3. 每次 Tool 调用记录 Agent Identity、Case、`incident_sequence`、Tool、输入摘要、结果码和时间；凭据与敏感值不得进入公开证据。
4. 所有订单写入必须经过授权校验、状态前置检查和幂等绑定。
5. 风险规则是独立确定性控制；Gateway 负责调用与权限，不替代风险判断。
6. Customer Chat Facade 与 Project Room 使用不同消息投影，不能依赖前端隐藏来实现隔离。
