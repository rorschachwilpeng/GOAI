# Data Model：酒店供应异常自主改订最小闭环

## 文档状态

| 字段 | 内容 |
|---|---|
| 状态 | Approved as Plan artifact |
| 日期 | 2026-08-14 |
| Spec | [`spec.md`](./spec.md)（Approved） |
| Plan | [`plan.md`](./plan.md)（Approved） |

## 1. 关系概览

```text
CustomerIdentity 1 ── N Order
        │                 │
        └── 1 Case 1 ── 1 ProjectRoom
                 │
                 ├── 0..1 OrderReference ── 1 Order
                 ├── N ResolutionPlan ── 1 RiskDecision
                 │        ├── 0..1 CustomerConfirmation
                 │        ├── 0..1 InternalDecision
                 │        └── 0..1 ExecutionRecord
                 ├── N VerificationPackage ── 1 VerificationResult
                 ├── N AuditEvent
                 └── 0..1 CaseCard
```

## 2. 核心实体

### 2.1 Case

| 字段 | 类型 | 约束 |
|---|---|---|
| `case_id` | string | 主键，稳定且不可复用 |
| `customer_id` | string | 绑定可信会话身份 |
| `case_state` | enum | 见第 3 节 |
| `resolution_mode` | enum/null | `AUTONOMOUS | HUMAN_ASSISTED` |
| `project_id` | string | 与 Case 一对一 |
| `project_room_id` | string | 与 Case 一对一，恢复 Case 时复用 |
| `order_ref` | string/null | 唯一匹配后签发的不透明引用 |
| `resolution_plan_id` | string/null | 当前有效方案 |
| `risk_decision_id` | string/null | 当前有效风险决定 |
| `reply_deadline_at` | datetime/null | 追问成功发出后 24 小时 |
| `reopened_count` | integer | 非负 |
| `created_at` / `updated_at` | datetime | 带时区 |

### 2.2 Customer Identity

| 字段 | 类型 | 约束 |
|---|---|---|
| `customer_id` | string | 由已登录会话提供 |
| `identity_source` | string | MVP 固定为现有登录系统 |
| `verified_at` | datetime | 进入 Case 前已完成 |

MVP 不实现验证码、匿名匹配或生产 IAM。

### 2.3 Order

| 字段 | 类型 | 现有 Mock 字段 |
|---|---|---|
| `order_id`、`customer_id` | string | 订单主键与归属 |
| `hotel_id`、`hotel_name` | string | 当前酒店 |
| `check_in_date`、`check_out_date` | date | 入离店日期 |
| `room_type`、`hotel_level` | string / integer | 房型与等级 |
| `total_price_cny` | number | 人民币元 |
| `status` | string | Golden Case 为 `CONFIRMED → REBOOKED` |
| `confirmation_number` | string | 执行后必须更新 |
| `last_idempotency_key` | string/null | 最近一次受控写入键 |

### 2.4 Supplier Exception

`exception_id`、`order_id`、`type`、`summary`、`source`、`occurred_at`。MVP 只接受预置结构化合成事实。

### 2.5 Resolution Plan

当前 `evaluate_rebooking` 要求以下字段完整：

`resolution_plan_id`、`order_ref`、`order_id`、`action`、`diagnosis`、`evidence_ids`、`replacement_hotel_id`、`replacement_hotel_name`、`check_in_date`、`check_out_date`、`price_difference_cny`、`previous_confirmation_number`、`expected_current_status`、`expected_target_status`。

计划一旦进入风险评估即冻结；修改内容必须生成新的 `resolution_plan_id`。

### 2.6 Risk Decision

| 字段 | 类型 | 约束 |
|---|---|---|
| `risk_decision_id` | string | 主键 |
| `resolution_plan_id` | string | 绑定冻结方案 |
| `decision` | enum | `REQUIRE_CUSTOMER_CONFIRMATION | REQUIRE_INTERNAL_APPROVAL | DENY` |
| `rule_version` | string | 当前为 `rebooking-v0.1` |
| `reason_code` | string | 确定性原因码 |
| `required_controls` | string[] | 必需控制 |
| `valid` | boolean | 执行前必须为 true |

### 2.7 Customer Confirmation

`confirmation_id`、`case_id`、`customer_id`、`resolution_plan_id`、`risk_decision_id`、`message_event_id`、`confirmed`。确认只能绑定当前客户、当前 Case 和当前版本方案。

### 2.8 Internal Decision

| 字段 | 类型 | 状态 |
|---|---|---|
| `internal_decision_id` | string | 方案设计 |
| `case_id`、`resolution_plan_id`、`risk_decision_id` | string | 方案设计 |
| `decision` | enum | `APPROVE | REJECT` |
| `message_event_id`、`operator_id` | string | 绑定 Room 消息和运营人员 |
| `recorded_at` | datetime | 服务端生成 |

V0.1 的 800 元样例只验收决定记录和授权判断；`APPROVE` 后不继续执行高风险改订。

### 2.9 Execution Record

当前字段：`execution_id`、`case_id`、`resolution_plan_id`、`risk_decision_id`、`order_id`、`reported_status`、`confirmation_number`、`idempotency_key`、`idempotent_replay`。

同一幂等键永久绑定同一组 Case、方案和风险决定；不同绑定必须拒绝。

### 2.10 Verification Package

计划字段：`package_id`、`case_id`、`customer_id`、`order_ref`、`resolution_plan_snapshot`、`expected_result`、`bdd_assertions`、`evidence_refs`、`package_version`、`frozen_at`、`sha256`。

冻结规则：

- 对规范化 JSON 计算 SHA-256；
- 冻结后不可原地修改；
- 不包含隐藏推理、Project Room 讨论全文或执行 Tool 的返回值；
- 只包含完成独立回查所需的最小信息。

### 2.11 Verification Result

当前字段：`verification_status`（`PASSED | FAILED`）、`order_id`、`checks`、`differences`。七项检查为目标订单、归属、替代酒店、日期、状态、新确认号和幂等键。

### 2.12 Audit Event 与 Case Card

- `AuditEvent`：`sequence`、`case_id`、`event_type`、`actor`、`details`；按 Case 有序追加。
- `CaseCard`：结构化问题类型、诊断、动作、替代酒店、价差、核验结果和闭环方式；V0.1 只写入，不做召回。

## 3. Case 状态机

### 3.1 主链路

```text
RECEIVED
→ IDENTIFYING_ORDER
→ RESOLVING
→ AWAITING_CUSTOMER_CONFIRMATION / AWAITING_INTERNAL_APPROVAL
→ EXECUTING
→ VERIFYING
→ NOTIFYING_CUSTOMER
→ RESOLVED
```

`AWAITING_*` 是按风险决定选择的分支，不表示两者依次发生。

### 3.2 转换表

| 当前状态 | 事件 / 条件 | 下一状态 | 约束 |
|---|---|---|---|
| `RECEIVED` | 创建 Case | `IDENTIFYING_ORDER` | 创建唯一 Project Room |
| `IDENTIFYING_ORDER` | 信息不足且追问发送成功 | `AWAITING_CUSTOMER_INFO` | 设置 `reply_deadline_at` |
| `AWAITING_CUSTOMER_INFO` | 有效回复到达 | `IDENTIFYING_ORDER` | 以消息到达时间为准 |
| `AWAITING_CUSTOMER_INFO` | 截止后仍无有效回复 | `CLOSED_INCOMPLETE` | 停止后台处理 |
| `IDENTIFYING_ORDER` | 唯一匹配且归属验证通过 | `RESOLVING` | 不允许跳过归属验证 |
| `RESOLVING` | 需客户确认 | `AWAITING_CUSTOMER_CONFIRMATION` | 绑定方案和风险决定 |
| `RESOLVING` | 需内部审批 | `AWAITING_INTERNAL_APPROVAL` | 进入 Operations Review |
| `RESOLVING` | 风险拒绝 | `MANUAL_REQUIRED` | 不执行 |
| `AWAITING_CUSTOMER_CONFIRMATION` | 客户确认 | `EXECUTING` | 确认必须有效 |
| `AWAITING_CUSTOMER_CONFIRMATION` | 客户拒绝 | `RESOLVING` | 原方案失效 |
| `AWAITING_INTERNAL_APPROVAL` | `APPROVE` | `EXECUTING`* | *V0.1 只验授权，不实际进入高风险执行 |
| `AWAITING_INTERNAL_APPROVAL` | `REJECT` | `MANUAL_REQUIRED` | 不执行 |
| `EXECUTING` | 写入成功或结果未知 | `VERIFYING` | 结果未知也不得重复写入 |
| `VERIFYING` | 核验通过 | `NOTIFYING_CUSTOMER` | 必须为独立回读 |
| `VERIFYING` | 核验失败 | `MANUAL_REQUIRED` | 不宣告成功 |
| `NOTIFYING_CUSTOMER` | 通知成功 | `RESOLVED` | 通知失败保持本状态重试 |
| `CLOSED_INCOMPLETE` | 同一客户同一问题回复 | `IDENTIFYING_ORDER` | 恢复原 Case 与 Project Room |
| `RESOLVED` | 客户对结果提出异议 | `IDENTIFYING_ORDER` | 恢复原 Case，`reopened_count + 1` |

### 3.3 时间语义

- 24 小时从“补充信息请求成功发送”的服务端时间开始计算。
- 客户消息的 `origin_server_ts` 不晚于截止时间即视为有效，即使后台稍后才处理。
- 超时关闭后的迟到回复不会继续已停止的后台任务，而是显式重开原 Case。

## 4. 全局不变量

1. 未验证客户归属不得返回订单详情。
2. `MULTIPLE` 只返回数量、缺失字段和空候选列表。
3. 未满足风险控制不得写入订单。
4. 同一幂等键不得绑定不同执行请求。
5. Verification 不采信执行 Tool 返回值作为成功证据。
6. 核验失败不得进入 `NOTIFYING_CUSTOMER` 或 `RESOLVED`。
7. Case 重开时复用原 Project Room，不创建重复 Case。
