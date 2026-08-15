# Implementation Plan：酒店供应异常自主改订最小闭环

## Plan Metadata

| 字段 | 内容 |
|---|---|
| Feature | `001-autonomous-customer-service-loop` |
| 状态 | Draft — Linked Journey Revision |
| 日期 | 2026-08-15 |
| 确认日期 | 待用户评审 |
| Spec | [`spec.md`](./spec.md)（Draft — Linked Journey Revision） |
| 既有架构参考 | [`GOAI-Multi-Agent-MCP-Architecture-V7.pdf`](../../07-参赛材料/架构图/GOAI-Multi-Agent-MCP-Architecture-V7.pdf) |

## 1. Summary

在已实现的 AgentTeams Project Room、角色化 MCP Surface、运营审批和 Case 恢复能力上，构建一条可录制的连续客户旅程：客户通过独立 Chatbot 网页与 Frontline 对话；同一个 Service Case 和 Project Room 先完成 180 元低风险改订与独立核验，供应异常复发后恢复原 Case，再完成 800 元高风险方案的运营审批、客户确认超时、迟到回复、双重授权执行和第二次独立核验。

本 Plan 是目标设计。当前可运行基线与目标差距见 [`research.md`](./research.md)。

## 2. Technical Context

| 项目 | 选择 | 状态 |
|---|---|---|
| 多 Agent 框架 | AgentTeams 1.2.2 | 已实现基线 |
| Agent Runtime | CoPaw | 已实现基线 |
| 模型 | Kimi K2.6 | 已实现基线 |
| 消息与 UI | Matrix / Element | 已实现基线 |
| 客户应用层 | 原生 HTML / CSS / JavaScript；由本地 Python 服务提供 Conversation API | 待实现 |
| MCP Gateway | Higress MCP | 三个角色化 Surface 已实现并已验证配置 |
| Mock 后端 | Python 3.13 HTTP 服务 | 模拟执行 |
| 数据 | JSON 合成订单、供应异常、替代酒店与规则 | 模拟执行 |
| 测试 | Python `unittest` | 已实现 |
| 运行环境 | Docker Desktop + 本地 Mock 服务 | 已实现基线 |

## 3. Constitution Check

- 只使用合成数据，不接入真实客户、订单、邮件或内部规则。
- 2026-08-14 版 Spec 与 Plan 已作为改造前基线冻结在 Git 提交 `edef185`；本次连续旅程变更必须重新评审。
- Project Room、角色级 MCP Surface、内部决定记录和原 Case 重开已经实现并有证据；客户隔离层、双重授权执行、连续旅程和 Demo 埋点仍为方案设计。
- Manager 不获得订单写权限；Verification 只读并独立核验。
- 本 Plan 通过用户评审后，实施必须按更新后的 `tasks.md` 执行并逐项留证。

## 4. Target Architecture

### 4.1 Agent 职责

| Agent | 职责 | 不承担 |
|---|---|---|
| Frontline Agent | 客户对话、安全定位订单、索取缺失信息、记录客户确认 | 候选订单详情读取、异常调查、订单写入 |
| Resolution Agent | 查询已授权订单、调查供应异常、生成方案、申请风险判断、受控执行 | 客户身份判定、自行批准高风险方案、核验自身结果 |
| Manager Agent | 创建与维护 Case、SLA、任务所有权、Room 路由、阶段闸门、冻结 Verification Package | 订单查询或写入、替代风险服务、替代 Verification |
| Verification Agent | 按冻结输入只读回查、执行 BDD Assertions、返回 PASS / FAIL 与证据 | 读取处置讨论、修改方案、订单写入、自证执行成功 |

### 4.2 原生 Room 映射

| Room | 成员与入口 | 用途 | admin 口径 |
|---|---|---|---|
| Customer Conversation | 独立 Chatbot 网页；只展示 `C001` 与 Frontline 的正式消息 | 对客交互与持续对话历史 | 不显示 Manager、内部事件或 Tool 元数据 |
| Frontline Runtime Room | Frontline Worker 专属 Room | AgentTeams 运行与内部任务入口，不作为客户产品界面 | admin 仅作为本地测试工具 |
| Case Project Room | Frontline、Resolution、Manager；AgentTeams 强制包含 admin | 一个 Case 的共享上下文、任务状态、结构化交接与风险告警 | 只观察，不计业务人工介入 |
| Operations Review Room | Resolution Worker 专属 Room | 风险触发后向 Hotel Operations 请求 `APPROVE / REJECT` | P2 中模拟运营人员 |
| Independent Verification Room | Verification Worker 专属 Room；Manager 与 admin 按框架存在 | 传入冻结 Package，返回独立核验结果 | 只观察，不计业务人工介入 |

约束：一个 `Case` 对应一个 AgentTeams `Project` 和一个 `Case Project Room`。供应异常复发、超时关闭和迟到回复均恢复原 Case 与原 Room；通过 `incident_sequence` 区分异常轮次。Verification 不加入 Case Project Room。

### 4.3 协作流程

1. Customer Conversation 接收客户消息并持久化客户可见历史；Channel Adapter 将输入交给 Frontline，但不把 Frontline Runtime Room 暴露给客户。
2. Manager 创建 `CASE-JOURNEY-001` 与唯一 Project Room；Frontline 和 Resolution 在 Room 中使用结构化交接消息协作。
3. 第一次异常产生 180 元方案；客户确认后 Resolution 受控执行，Manager 冻结 Package，Verification 独立回查；`PASS` 后 Frontline 通知客户并关闭 Case。
4. Mock Order System 注入新的结构化供应异常；Manager 以 `SUPPLIER_EXCEPTION_RECURRED` 恢复同一 Case 与 Project Room，并将 `incident_sequence` 增加为 2。
5. 第二次异常只存在 800 元候补方案；Resolution 将审批请求路由至 Operations Review Room。运营 `APPROVE` 结果同步回 Project Room，但不能单独授权执行。
6. Frontline 向客户发布当前方案确认请求；24 小时无有效回复后 Manager 暂停 Case。迟到确认恢复原 Case、Conversation 与 Room。
7. Resolution 只有在运营 `APPROVE`、客户确认、订单前置状态和幂等标识同时有效时才执行第二次 Mock 改订。
8. Manager 再次冻结 Verification Package；Verification 独立回查并返回 `PASS | FAIL`。第二次 `PASS` 后 Frontline 通知客户并关闭 Case。

Manager 不逐条转发 Frontline 与 Resolution 的协作消息，只在状态、SLA、任务所有权和阶段闸门上介入。

### 4.4 客户隔离与可录制输出

- Customer Conversation 是客户唯一入口；客户不可加入或读取 Frontline Runtime Room、Case Project Room、Operations Review Room 或 Verification Room。
- Channel Adapter 只发布符合 Customer Message Schema 的正式回复；拒绝或剥离 Tool 名称、Matrix Event ID、内部订单引用、风险决定 ID、调度指令和原始 Tool 返回值。
- Case Project Room 只使用结构化短消息：`CASE_OPENED`、`ORDER_LINKED`、`PLAN_READY`、`EXECUTION_COMPLETED`、`VERIFICATION_PASS | FAIL`、`CASE_REOPENED`、`CUSTOMER_CONFIRMATION_REQUESTED`、`CUSTOMER_INFO_TIMEOUT`。
- 每次 Demo 运行生成 `run_id`、场景起止时间、客户消息 ID 与 Matrix Event ID；字幕属于录制材料，不写入客户对话或内部业务记录。

## 5. MCP 与业务服务

保留一个 Higress Gateway，计划注册三个独立 MCP Server 配置；三个 Surface 可以共用同一个 Mock HTTP 后端。

| Surface | 可发现 Tool | 状态 |
|---|---|---|
| Frontline | `resolve_order_reference`、`record_customer_confirmation` | 已实现，Mock |
| Resolution | `get_authorized_order`、`evaluate_rebooking`、`record_internal_decision`、`validate_execution_authorization`、`execute_rebooking` | 已实现，Mock；双重授权执行待扩展 |
| Verification | `get_order_state`、`verify_rebooking` | 已实现，只读 Mock |
| Manager | 无业务 Tool | 已实现配置约束 |

Tool Schema 与拒绝行为见 [`contracts/mcp-tools.md`](./contracts/mcp-tools.md)。

## 6. 状态与数据所有权

- AgentTeams / Manager 持有 Case 状态、SLA、任务所有权、Room 映射和 Verification Package 引用。
- Customer Conversation Store 持有客户可见消息、发布状态和 `conversation_id`；不保存内部推理或 Project Room 全文。
- Mock Order System 持有合成订单、供应异常、替代酒店、执行记录与订单审计。
- Risk & Policy 逻辑确定性返回控制要求和规则版本；MVP 可与 Mock HTTP 后端同进程，但逻辑职责独立。
- Verification Package 冻结后生成 SHA-256，不包含隐藏推理或执行 Tool 的返回值。
- 完整实体与状态约束见 [`data-model.md`](./data-model.md)。

## 7. Skills

| Skill | Agent | 用途 | 状态 |
|---|---|---|---|
| `identify-hotel-order` | Frontline | 提取线索、判断信息缺口、安全追问 | 已实现；需增加客户消息投影约束 |
| `investigate-hotel-supply-exception` | Resolution | 证据查询、异常诊断、方案生成 | 已实现；需增加异常复发与双重授权说明 |
| `verify-hotel-rebooking` | Verification | 预期与实际结果比对 | 已实现并接入冻结 Package；需支持第二次核验取证 |

## 8. Current-to-Target Migration

| 方面 | 当前实现 | 目标设计 |
|---|---|---|
| 客户入口 | Frontline Runtime Room 由 admin 模拟客户 | 独立 Chatbot 网页和客户可见 Conversation Store |
| 编排 | 单次 P1 Project Room；P2、P3 独立运行 | 同一 Case、同一 Project Room 串联两轮供应异常 |
| 核验 | P1 已完成一次独立核验 | 每次订单写入后各运行一次独立核验 |
| 权限 | 三个角色化 MCP Surface 已实现 | 保留；新增客户消息发布白名单 |
| 人工审批 | Operations Review 已记录 APPROVE / REJECT，但批准后禁止执行 | `APPROVE` 与客户确认组成双重授权后允许受控 Mock 执行 |
| 业务执行 | Python Mock API 支持一次改订 | 支持同一履约链路的第二次候补改订和幂等记录 |
| 身份 | 同一个 admin | 继续作为 Demo 模拟账号，不声称生产 IAM |

## 9. Project Structure

```text
specs/001-autonomous-customer-service-loop/
├── spec.md
├── research.md
├── plan.md
├── data-model.md
├── contracts/mcp-tools.md
└── quickstart.md

workspace/
├── agentteams/              # Worker 与 MCP 配置（后续实施）
├── customer-chat/           # 客户 Chatbot 静态界面（待实现）
├── skills/                  # 3 个 Skill（现有）
├── mock-services/           # Mock API、合成数据与测试（现有）
└── runs/                    # AgentTeams 与 Golden Case 证据
```

## 10. Requirements Traceability

| Spec | 设计落点 | 计划证据 |
|---|---|---|
| FR-001～FR-004 | Frontline Surface、Customer Identity、Order Reference | 订单匹配与跨客户拒绝测试 |
| FR-005～FR-008 | Resolution Skill、Risk Decision、Operations Review、双重授权 | 180 元与 800 元连续分支 Trace |
| FR-009～FR-012 | 幂等执行、Verification Package、只读核验、通知闸门 | 重放、假成功和 Golden Case 测试 |
| FR-013～FR-014 | Case 状态机、reply deadline、供应异常复发与 reopen 规则 | 超时关闭与同一 Case/Room 恢复测试 |
| FR-015～FR-016 | Audit Event、Case Card | Trace 完整性与摘要失败测试 |
| FR-017～FR-018 | Customer Conversation 隔离、Room 隔离、角色化 MCP Surface、合成数据 | 客户输出白名单、成员与 Tool 可见性证据、数据检查 |
| SC-001～SC-005 | Linked Golden Journey | 客户对话、Project Room 消息、两次订单状态与核验结果 |
| SC-006～SC-008 | 安全与状态分支 | 假成功、800 元、24 小时分支测试 |
| SC-009～SC-010 | Trace 与 Case Card | 七类事件完整率、Case Card Schema |

## 11. Complexity Tracking

| 复杂度 | 保留理由 | 不采用的更复杂方案 |
|---|---|---|
| 4 个产品 Agent | 区分客户入口、处置、控制面和独立核验 | 不继续增加专用 Agent |
| 客户应用层 + 3 类内部 Room | 满足对客、协作、审批和核验隔离；Frontline Runtime Room 不再冒充客户产品 | 不建设完整 IAM 或消息总线 |
| 3 个 MCP Surface | 在 Gateway 层落实最小权限 | 不为每个 Surface 建独立后端 |

## 12. Implementation Gate

客户隔离层、同一 Case/Project Room 的连续旅程、800 元双重授权执行、两次 Verification 与 Demo 埋点属于本次待确认变更。用户确认本 Plan 后，后续执行以更新后的 [`tasks.md`](./tasks.md) 为唯一任务清单；任何改变上述设计或 Spec 验收口径的事项必须先回到 Planning Agent。
