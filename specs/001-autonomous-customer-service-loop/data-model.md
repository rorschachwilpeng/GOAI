# Data Model：连续酒店供应异常自主改订闭环

## 文档状态

| 字段 | 内容 |
|---|---|
| 状态 | Draft — Linked Journey Revision |
| 日期 | 2026-08-15 |
| Spec | [`spec.md`](./spec.md)（待用户确认） |
| Plan | [`plan.md`](./plan.md)（待用户确认） |

## 1. 关系概览

```text
CustomerIdentity 1 ── N Order
        │
        └── 1 CustomerConversation 1 ── 1 ServiceCase 1 ── 1 ProjectRoom
                                               │
                                               ├── N SupplierIncident ── 1 Order
                                               ├── N ResolutionPlan ── 1 RiskDecision
                                               │        ├── 0..1 CustomerConfirmation
                                               │        ├── 0..1 InternalDecision
                                               │        └── 0..1 ExecutionRecord
                                               ├── N VerificationPackage ── 1 VerificationResult
                                               ├── N AuditEvent
                                               └── 0..1 CaseCard
```

同一 Service Case 可以包含多次连续供应异常。`incident_sequence` 区分第几轮处置，但不创建新的 `case_id`、客户对话或 Project Room。

## 2. 核心实体

### 2.1 Customer Identity

| 字段 | 类型 | 约束 |
|---|---|---|
| `customer_id` | string | 由已登录会话提供 |
| `identity_source` | string | MVP 固定为现有登录系统 |
| `verified_at` | datetime | 进入 Case 前已完成 |

MVP 不实现验证码、匿名匹配或生产 IAM。

### 2.2 Customer Conversation

| 字段 | 类型 | 约束 |
|---|---|---|
| `conversation_id` | string | 主键；一次连续 Demo 固定不变 |
| `customer_id` | string | 只绑定已验证客户 |
| `case_id` | string | 与当前 Service Case 一对一 |
| `messages` | array | 只保存允许向客户展示的消息投影 |
| `created_at` / `updated_at` | datetime | 带时区 |

客户投影不得包含 Project Room 消息、隐藏推理、Tool 参数、MCP 错误堆栈、内部风险规则明细或其他客户订单信息。

### 2.3 Service Case

| 字段 | 类型 | 约束 |
|---|---|---|
| `case_id` | string | 主键，稳定且不可复用 |
| `customer_id` | string | 绑定可信会话身份 |
| `conversation_id` | string | 恢复 Case 时复用 |
| `case_state` | enum | 见第 3 节 |
| `resolution_mode` | enum/null | `AUTONOMOUS | HUMAN_ASSISTED` |
| `project_id` / `project_room_id` | string | 与 Case 一对一，恢复时复用 |
| `incident_sequence` | integer | 从 1 开始；每次确认的新供应异常加 1 |
| `current_supplier_exception_id` | string/null | 当前处置轮次的异常 |
| `order_ref` | string/null | 唯一匹配后签发的不透明引用 |
| `resolution_plan_id` | string/null | 当前有效方案 |
| `risk_decision_id` | string/null | 当前有效风险决定 |
| `awaiting_response_type` | enum/null | `CUSTOMER_INFO | PLAN_CONFIRMATION` |
| `reply_deadline_at` | datetime/null | 请求成功发出后 24 小时 |
| `reopened_count` | integer | 非负 |
| `created_at` / `updated_at` | datetime | 带时区 |

### 2.4 Order

| 字段 | 类型 | 约束 |
|---|---|---|
| `order_id`、`customer_id` | string | 订单主键与归属 |
| `hotel_id`、`hotel_name` | string | 当前酒店 |
| `check_in_date`、`check_out_date` | date | 入离店日期 |
| `room_type`、`hotel_level` | string / integer | 房型与等级 |
| `total_price_cny` | number | 人民币元 |
| `status` | string | 两轮改订均通过受控接口更新 |
| `confirmation_number` | string | 每次执行后必须更新 |
| `last_idempotency_key` | string/null | 最近一次受控写入键 |

### 2.5 Supplier Incident

字段：`exception_id`、`case_id`、`incident_sequence`、`order_id`、`type`、`summary`、`source`、`occurred_at`、`reopens_case`。

- 第 1 轮为原酒店无法履约。
- 第 2 轮为替代酒店再次取消，必须恢复原 Case 与 Project Room。
- MVP 只接受预置结构化合成事实。

### 2.6 Resolution Plan

字段：`resolution_plan_id`、`case_id`、`incident_sequence`、`order_ref`、`order_id`、`action`、`diagnosis`、`evidence_ids`、`replacement_hotel_id`、`replacement_hotel_name`、`check_in_date`、`check_out_date`、`price_difference_cny`、`previous_confirmation_number`、`expected_current_status`、`expected_target_status`。

计划进入风险评估后即冻结；修改内容必须生成新的 `resolution_plan_id`。

### 2.7 Risk Decision

| 字段 | 类型 | 约束 |
|---|---|---|
| `risk_decision_id` | string | 主键 |
| `resolution_plan_id` | string | 绑定冻结方案 |
| `decision` | enum | `REQUIRE_CUSTOMER_CONFIRMATION | REQUIRE_INTERNAL_APPROVAL | DENY` |
| `rule_version` | string | 规则版本 |
| `reason_code` | string | 确定性原因码 |
| `required_controls` | string[] | 可同时包含 `INTERNAL_APPROVAL` 与 `CUSTOMER_CONFIRMATION` |
| `valid_until` | datetime/null | 过期后必须重新评估 |
| `valid` | boolean | 执行前必须为 true |

180 元方案要求 `CUSTOMER_CONFIRMATION`；800 元方案返回 `REQUIRE_INTERNAL_APPROVAL`，且 `required_controls` 必须同时包含内部批准和客户确认。

### 2.8 Customer Confirmation

字段：`confirmation_id`、`case_id`、`incident_sequence`、`customer_id`、`resolution_plan_id`、`risk_decision_id`、`message_event_id`、`confirmed`、`recorded_at`。

确认只能绑定当前客户、当前 Case、当前轮次和当前版本方案；旧方案确认不得复用。

### 2.9 Internal Decision

字段：`internal_decision_id`、`case_id`、`incident_sequence`、`resolution_plan_id`、`risk_decision_id`、`decision`（`APPROVE | REJECT`）、`message_event_id`、`operator_id`、`recorded_at`。

`APPROVE` 只满足内部控制，不等于订单可立即执行；800 元方案仍需有效客户确认。`REJECT` 必须阻断执行。

### 2.10 Execution Record

字段：`execution_id`、`case_id`、`incident_sequence`、`resolution_plan_id`、`risk_decision_id`、`order_id`、`reported_status`、`confirmation_number`、`idempotency_key`、`idempotent_replay`、`executed_at`。

- 两轮改订使用不同幂等键并形成两条记录。
- 同一幂等键永久绑定同一组 Case、轮次、方案和风险决定；不同绑定必须拒绝。
- Tool 返回的成功只代表“已受理写入”，不能作为最终成功证据。

### 2.11 Verification Package

字段：`package_id`、`case_id`、`incident_sequence`、`execution_id`、`customer_id`、`order_ref`、`resolution_plan_snapshot`、`expected_result`、`bdd_assertions`、`evidence_refs`、`package_version`、`frozen_at`、`sha256`。

冻结规则：

- 每次订单写入都生成独立 Package；
- 对规范化 JSON 计算 SHA-256，冻结后不可原地修改；
- 不包含隐藏推理、Project Room 讨论全文或执行 Tool 返回值；
- 只包含完成独立回查所需的最小信息。

### 2.12 Verification Result

字段：`verification_status`（`PASSED | FAILED`）、`case_id`、`incident_sequence`、`execution_id`、`order_id`、`checks`、`differences`、`verified_at`。

每轮检查目标订单、归属、替代酒店、日期、状态、新确认号和幂等键。第 1、2 次写入必须分别产生 Verification #1、#2。

### 2.13 Audit Event 与 Case Card

- `AuditEvent`：`sequence`、`case_id`、`incident_sequence`、`event_type`、`actor`、`details`；按 Case 有序追加。
- `CaseCard`：汇总两轮异常、风险控制、执行和核验结果；MVP 只写入，不做召回。

## 3. Case 状态机

### 3.1 第一轮低风险主链路

```text
RECEIVED
→ IDENTIFYING_ORDER
→ RESOLVING
→ AWAITING_CUSTOMER_CONFIRMATION
→ EXECUTING
→ VERIFYING
→ NOTIFYING_CUSTOMER
→ RESOLVED
```

### 3.2 第二轮高风险连续链路

```text
RESOLVED
→ [SUPPLIER_EXCEPTION_RECURRED；incident_sequence + 1]
→ RESOLVING
→ AWAITING_INTERNAL_APPROVAL
→ AWAITING_CUSTOMER_CONFIRMATION
→ CLOSED_INCOMPLETE               （24 小时无回复）
→ EXECUTING                       （迟到确认到达且双重授权复核通过）
→ VERIFYING
→ NOTIFYING_CUSTOMER
→ RESOLVED
```

### 3.3 转换表

| 当前状态 | 事件 / 条件 | 下一状态 | 约束 |
|---|---|---|---|
| `RECEIVED` | 创建 Case | `IDENTIFYING_ORDER` | 创建唯一 Customer Conversation 与 Project Room |
| `IDENTIFYING_ORDER` | 信息不足且追问发送成功 | `AWAITING_CUSTOMER_INFO` | `awaiting_response_type=CUSTOMER_INFO` |
| `AWAITING_CUSTOMER_INFO` | 有效回复到达 | `IDENTIFYING_ORDER` | 以消息到达时间为准 |
| `IDENTIFYING_ORDER` | 唯一匹配且归属通过 | `RESOLVING` | 不允许跳过归属验证 |
| `RESOLVING` | 低风险，需客户确认 | `AWAITING_CUSTOMER_CONFIRMATION` | 绑定当前方案与风险决定 |
| `RESOLVING` | 高风险，需内部批准 | `AWAITING_INTERNAL_APPROVAL` | 进入 Operations Review |
| `RESOLVING` | 风险拒绝 | `MANUAL_REQUIRED` | 不执行 |
| `AWAITING_INTERNAL_APPROVAL` | `APPROVE` | `AWAITING_CUSTOMER_CONFIRMATION` | 批准不替代客户确认 |
| `AWAITING_INTERNAL_APPROVAL` | `REJECT` | `MANUAL_REQUIRED` | 不执行 |
| `AWAITING_CUSTOMER_CONFIRMATION` | 客户确认且所需控制全部有效 | `EXECUTING` | 执行前再次校验授权和前置状态 |
| `AWAITING_CUSTOMER_CONFIRMATION` | 客户拒绝 | `RESOLVING` | 原方案失效 |
| `AWAITING_CUSTOMER_INFO` / `AWAITING_CUSTOMER_CONFIRMATION` | 截止后仍无有效回复 | `CLOSED_INCOMPLETE` | 停止后台处理 |
| `CLOSED_INCOMPLETE` | 同一客户回复信息 | `IDENTIFYING_ORDER` | 恢复原 Case、Conversation 与 Room |
| `CLOSED_INCOMPLETE` | 同一客户有效确认当前方案 | `EXECUTING` | 先重验方案、风险、批准、确认和订单状态 |
| `EXECUTING` | 写入成功或结果未知 | `VERIFYING` | 不得因结果未知重复写入 |
| `VERIFYING` | 独立核验通过 | `NOTIFYING_CUSTOMER` | 只采信业务系统回读 |
| `VERIFYING` | 核验失败 | `MANUAL_REQUIRED` | 不宣告成功 |
| `NOTIFYING_CUSTOMER` | 通知成功 | `RESOLVED` | 通知失败保持本状态重试 |
| `RESOLVED` | 新供应异常命中当前订单 | `RESOLVING` | `incident_sequence + 1`，复用原 Case 与 Room |
| `RESOLVED` | 客户对结果提出异议 | `IDENTIFYING_ORDER` | 复用原 Case，`reopened_count + 1` |

### 3.4 时间语义

- 24 小时从补充信息或方案确认请求“成功投递到客户会话”的服务端时间开始。
- 客户消息的到达时间不晚于截止时间即视为有效，即使后台稍后才处理。
- 超时关闭后的回复不得恢复已停止任务；系统必须显式恢复原 Case，重新校验当前方案和授权上下文。

## 4. 全局不变量

1. 未验证客户归属不得返回订单详情；`MULTIPLE` 只返回数量和缺失字段。
2. 同一客户连续供应异常复用原 Case、Customer Conversation 与 Project Room。
3. 客户侧只展示 Customer Conversation 投影，任何内部协作或 Tool 细节不得泄漏。
4. 未满足风险决定列出的全部控制不得写入订单。
5. 同一幂等键不得绑定不同执行请求；结果未知时不得盲目重试。
6. 每次订单写入必须生成独立 Verification Package 并由 Verification 回读业务系统。
7. 核验失败不得进入 `NOTIFYING_CUSTOMER` 或 `RESOLVED`。
8. Case Card 写入失败不得回滚已核验的客户业务结果，但 Demo 验收必须标记失败。
