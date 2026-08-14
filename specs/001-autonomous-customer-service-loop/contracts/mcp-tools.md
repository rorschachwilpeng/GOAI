# MCP Tool Contracts

## 1. 状态与部署口径

| 字段 | 内容 |
|---|---|
| 版本 | V0.1 Design Approved；实现状态按 Tool 标注 |
| 日期 | 2026-08-14 |
| 当前基线 | 8 个 Tool 已由一个 `mcp-goai-order` 配置暴露，共用 Python Mock HTTP 后端 |
| 目标 | 在同一个 Higress Gateway 注册 3 个角色化 MCP Server 配置 |

统一错误响应：

```json
{"error": {"code": "MACHINE_READABLE_CODE", "message": "Human-readable message"}}
```

## 2. 角色化 Surface

| Surface | Tool | 状态 |
|---|---|---|
| Frontline | `resolve_order_reference`、`record_customer_confirmation` | Tool 已实现；Surface 待实现 |
| Resolution | `get_authorized_order`、`evaluate_rebooking`、`validate_execution_authorization`、`execute_rebooking` | Tool 已实现；Surface 待实现 |
| Resolution | `record_internal_decision` | 方案设计，待实现 |
| Verification | `get_order_state`、`verify_rebooking` | Tool 已实现；Surface 待实现 |
| Manager | 无业务 Tool | 方案设计 |

角色身份决定 Agent 能发现和调用哪些 Tool。Skill 文案不构成强制权限。

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

### `record_customer_confirmation`（已实现）

请求：

```json
{
  "case_id": "CASE-GOLDEN-001",
  "resolution_plan_id": "PLAN-GOLDEN-001",
  "risk_decision_id": "RISK-PLAN-GOLDEN-001",
  "message_event_id": "MSG-003"
}
```

响应：`confirmation_id`、`case_id`、`customer_id`、`resolution_plan_id`、`risk_decision_id`、`message_event_id`、`confirmed=true`。

主要错误：`CONFIRMATION_CONTEXT_INVALID`、`ORDER_ACCESS_DENIED`。

## 4. Resolution Surface

### `get_authorized_order`（已实现）

请求：

```json
{"customer_id": "C001", "order_ref": "oref_..."}
```

响应：`order`、`supplier_exceptions[]`、`eligible_rebooking_options[]`。只有不透明引用属于当前客户时才能返回完整内容。

主要错误：`ORDER_ACCESS_DENIED`、`NOT_FOUND`。

### `evaluate_rebooking`（已实现）

请求：

```json
{
  "case_id": "CASE-GOLDEN-001",
  "customer_id": "C001",
  "order_ref": "oref_...",
  "resolution_plan": {
    "resolution_plan_id": "PLAN-GOLDEN-001",
    "order_ref": "oref_...",
    "order_id": "H-C001-001",
    "action": "REBOOK",
    "diagnosis": "原酒店确认无法履约",
    "evidence_ids": ["SUP-EX-001"],
    "replacement_hotel_id": "HTL-SHA-HARBOR",
    "replacement_hotel_name": "上海虹桥海湾臻选酒店",
    "check_in_date": "2026-08-15",
    "check_out_date": "2026-08-17",
    "price_difference_cny": 180,
    "previous_confirmation_number": "CONF-C001-001",
    "expected_current_status": "CONFIRMED",
    "expected_target_status": "REBOOKED"
  }
}
```

响应：

```json
{
  "risk_decision_id": "RISK-PLAN-GOLDEN-001",
  "resolution_plan_id": "PLAN-GOLDEN-001",
  "decision": "REQUIRE_CUSTOMER_CONFIRMATION",
  "rule_version": "rebooking-v0.1",
  "reason_code": "PRICE_DIFF_WITHIN_300",
  "required_controls": ["CUSTOMER_CONFIRMATION"],
  "valid": true
}
```

`decision` 仅允许 `REQUIRE_CUSTOMER_CONFIRMATION | REQUIRE_INTERNAL_APPROVAL | DENY`。主要错误：`ORDER_ACCESS_DENIED`、`ORDER_PLAN_MISMATCH`。

### `record_internal_decision`（方案设计，待实现）

请求固定为：

```json
{
  "tool": "record_internal_decision",
  "input": {
    "case_id": "string",
    "resolution_plan_id": "string",
    "risk_decision_id": "string",
    "decision": "APPROVE | REJECT",
    "message_event_id": "string",
    "operator_id": "string"
  }
}
```

计划响应：

```json
{
  "internal_decision_id": "INTERNAL-DECISION-...",
  "case_id": "string",
  "resolution_plan_id": "string",
  "risk_decision_id": "string",
  "decision": "APPROVE",
  "message_event_id": "string",
  "operator_id": "string",
  "recorded_at": "2026-08-14T12:00:00+08:00"
}
```

约束：决定必须绑定 Case、方案、风险决定、运营人员和消息事件。`APPROVE` 可使授权判断通过，但 V0.1 不继续执行高风险改订；`REJECT` 必须使授权判断拒绝。计划错误：`INTERNAL_DECISION_CONTEXT_INVALID`、`INVALID_INTERNAL_DECISION`、`INTERNAL_DECISION_CONFLICT`。

### `validate_execution_authorization`（已实现）

请求：

```json
{"case_id": "string", "resolution_plan_id": "string", "risk_decision_id": "string"}
```

成功响应：

```json
{"authorized": true, "risk_decision_id": "string"}
```

执行前重新校验上下文、方案与风险绑定、订单前置状态和所需控制。当前 800 元分支返回 `INTERNAL_APPROVAL_REQUIRED`；待 `record_internal_decision` 实现后，`APPROVE` 才可使授权判断通过。

主要错误：`EXECUTION_CONTEXT_INVALID`、`ORDER_STATE_CONFLICT`、`CUSTOMER_CONFIRMATION_REQUIRED`、`INTERNAL_APPROVAL_REQUIRED`、`EXECUTION_DENIED`。

### `execute_rebooking`（已实现，Mock 写入）

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

同一幂等键的相同请求返回原记录并标记 `idempotent_replay=true`；不同绑定返回 `IDEMPOTENCY_KEY_CONFLICT`。

## 5. Verification Surface

### `get_order_state`（已实现，只读）

请求：

```json
{"customer_id": "C001", "order_ref": "oref_..."}
```

返回当前实际 Order 对象。主要错误：`ORDER_ACCESS_DENIED`、`NOT_FOUND`。

### `verify_rebooking`（已实现，只读）

请求：

```json
{"customer_id": "C001", "resolution_plan_id": "PLAN-GOLDEN-001", "idempotency_key": "CASE-GOLDEN-001-REBOOK"}
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

Verification 不得写订单、修改方案或把执行返回值当作核验事实。

## 6. Gateway 与审计不变量

1. MCP Gateway 按 Agent Identity 暴露对应 Surface；未授权 Tool 不应被发现。
2. 自然语言消息不能授予 Tool 权限。
3. 每次 Tool 调用记录 Agent Identity、Case、Tool、输入摘要、结果码和时间；敏感值不得进入公开证据。
4. 所有订单写入必须经过授权校验、状态前置检查和幂等绑定。
5. 当前三个 Worker 仍共享完整 MCP Server；在角色化注册完成前，以上最小权限属于目标设计。
