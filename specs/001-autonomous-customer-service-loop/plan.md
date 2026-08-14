# Implementation Plan：酒店供应异常自主改订最小闭环

## Plan Metadata

| 字段 | 内容 |
|---|---|
| Feature | `001-autonomous-customer-service-loop` |
| 状态 | Approved |
| 日期 | 2026-08-14 |
| 确认日期 | 2026-08-14 |
| Spec | [`spec.md`](./spec.md)（Approved） |
| 目标架构 | [`GOAI-Multi-Agent-MCP-Architecture-V7.pdf`](../../07-参赛材料/架构图/GOAI-Multi-Agent-MCP-Architecture-V7.pdf) |

## 1. Summary

将现有“Manager 向三个独立 Worker 顺序派单”的 Golden Case，迁移为 AgentTeams 原生 Room 协作：Frontline 与 Resolution 在同一个 Case Project Room 直接交接；Manager 只维护 Case、SLA、任务和阶段闸门；Verification 接收冻结后的输入并独立回查。业务 Tool 继续通过一个 Higress Gateway 暴露，但按 Agent Identity 拆成三个角色化 MCP Surface。

本 Plan 是目标设计。当前可运行基线与目标差距见 [`research.md`](./research.md)。

## 2. Technical Context

| 项目 | 选择 | 状态 |
|---|---|---|
| 多 Agent 框架 | AgentTeams 1.2.2 | 已实现基线 |
| Agent Runtime | CoPaw | 已实现基线 |
| 模型 | Kimi K2.6 | 已实现基线 |
| 消息与 UI | Matrix / Element | 已实现基线 |
| MCP Gateway | Higress MCP | 已实现基线；角色化 Surface 待实现 |
| Mock 后端 | Python 3.13 HTTP 服务 | 模拟执行 |
| 数据 | JSON 合成订单、供应异常、替代酒店与规则 | 模拟执行 |
| 测试 | Python `unittest` | 已实现 |
| 运行环境 | Docker Desktop + 本地 Mock 服务 | 已实现基线 |

## 3. Constitution Check

- 只使用合成数据，不接入真实客户、订单、邮件或内部规则。
- Spec 已于 2026-08-14 确认；本轮只生成下游设计文档，不改运行资产。
- Project Room、角色级 MCP 隔离、内部决定记录均标记为待实现，不伪装成现状。
- Manager 不获得订单写权限；Verification 只读并独立核验。
- 本 Plan 已通过用户评审；实施必须按派生的 `tasks.md` 执行并逐项留证。

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
| Customer Service Room | Frontline Worker 专属 Room | 接收客户消息与对客回复 | Demo 中模拟 `C001` |
| Case Project Room | Frontline、Resolution、Manager；AgentTeams 强制包含 admin | 一个 Case 的共享上下文、任务状态、结构化交接与风险告警 | 只观察，不计业务人工介入 |
| Operations Review Room | Resolution Worker 专属 Room | 风险触发后向 Hotel Operations 请求 `APPROVE / REJECT` | P2 中模拟运营人员 |
| Independent Verification Room | Verification Worker 专属 Room；Manager 与 admin 按框架存在 | 传入冻结 Package，返回独立核验结果 | 只观察，不计业务人工介入 |

约束：一个 `Case` 对应一个 AgentTeams `Project` 和一个 `Case Project Room`。Verification 不加入 Case Project Room。

### 4.3 协作流程

1. Frontline 在 Customer Service Room 接收客户问题，Manager 创建 Case 与 Project。
2. Frontline 与 Resolution 加入 Case Project Room；前者提供已授权订单引用与客户上下文，后者直接接续调查。
3. Resolution 生成冻结方案并调用风险 Tool；低风险进入客户确认，高风险路由至 Operations Review Room。
4. 获得有效确认或审批后，Resolution 通过受控 Tool 执行一次 Mock 改订。
5. Manager 冻结 Verification Package，交给独立 Verification Worker。
6. Verification 只读回查并返回 `PASS | FAIL` 与证据；Manager 据此打开通知闸门或转人工。
7. Frontline 通知客户；通知成功后 Manager 关闭 Case。

Manager 不逐条转发 Frontline 与 Resolution 的协作消息，只在状态、SLA、任务所有权和阶段闸门上介入。

## 5. MCP 与业务服务

保留一个 Higress Gateway，计划注册三个独立 MCP Server 配置；三个 Surface 可以共用同一个 Mock HTTP 后端。

| Surface | 可发现 Tool | 状态 |
|---|---|---|
| Frontline | `resolve_order_reference`、`record_customer_confirmation` | 方案设计；Tool 已实现 |
| Resolution | `get_authorized_order`、`evaluate_rebooking`、`record_internal_decision`、`validate_execution_authorization`、`execute_rebooking` | 前后四项已实现；内部决定待实现 |
| Verification | `get_order_state`、`verify_rebooking` | 方案设计；Tool 已实现 |
| Manager | 无业务 Tool | 方案设计 |

Tool Schema 与拒绝行为见 [`contracts/mcp-tools.md`](./contracts/mcp-tools.md)。

## 6. 状态与数据所有权

- AgentTeams / Manager 持有 Case 状态、SLA、任务所有权、Room 映射和 Verification Package 引用。
- Mock Order System 持有合成订单、供应异常、替代酒店、执行记录与订单审计。
- Risk & Policy 逻辑确定性返回控制要求和规则版本；MVP 可与 Mock HTTP 后端同进程，但逻辑职责独立。
- Verification Package 冻结后生成 SHA-256，不包含隐藏推理或执行 Tool 的返回值。
- 完整实体与状态约束见 [`data-model.md`](./data-model.md)。

## 7. Skills

| Skill | Agent | 用途 | 状态 |
|---|---|---|---|
| `identify-hotel-order` | Frontline | 提取线索、判断信息缺口、安全追问 | 已实现，需迁移 Worker 命名 |
| `investigate-hotel-supply-exception` | Resolution | 证据查询、异常诊断、方案生成 | 已实现，需迁移协作入口 |
| `verify-hotel-rebooking` | Verification | 预期与实际结果比对 | 已实现，需接入冻结 Package |

## 8. Current-to-Target Migration

| 方面 | 当前实现 | 目标设计 |
|---|---|---|
| 编排 | Manager 顺序创建独立 Worker Task | Frontline 与 Resolution 在 Case Project Room 直接交接 |
| 核验 | 独立 Verification Worker | 保留 Worker，并隔离 Project Room、冻结输入 |
| 权限 | 三个 Worker 连接完整 8 Tool Server | 三个角色化 Surface；Manager 无业务 MCP |
| 人工审批 | 800 元分支阻断 | Operations Review Room 记录 APPROVE / REJECT |
| 业务执行 | Python Mock API | 保留，作为模拟业务系统 |
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
├── skills/                  # 3 个 Skill（现有）
├── mock-services/           # Mock API、合成数据与测试（现有）
└── runs/                    # AgentTeams 与 Golden Case 证据
```

## 10. Requirements Traceability

| Spec | 设计落点 | 计划证据 |
|---|---|---|
| FR-001～FR-004 | Frontline Surface、Customer Identity、Order Reference | 订单匹配与跨客户拒绝测试 |
| FR-005～FR-008 | Resolution Skill、Risk Decision、Operations Review | 180 元与 800 元分支 Trace |
| FR-009～FR-012 | 幂等执行、Verification Package、只读核验、通知闸门 | 重放、假成功和 Golden Case 测试 |
| FR-013～FR-014 | Case 状态机、reply deadline、reopen 规则 | 超时关闭与原 Case 恢复测试 |
| FR-015～FR-016 | Audit Event、Case Card | Trace 完整性与摘要失败测试 |
| FR-017～FR-018 | Room 隔离、角色化 MCP Surface、合成数据 | 成员与 Tool 可见性证据、数据检查 |
| SC-001～SC-005 | P1 Golden Journey | Project Room 消息、订单前后状态、核验结果 |
| SC-006～SC-008 | 安全与状态分支 | 假成功、800 元、24 小时分支测试 |
| SC-009～SC-010 | Trace 与 Case Card | 七类事件完整率、Case Card Schema |

## 11. Complexity Tracking

| 复杂度 | 保留理由 | 不采用的更复杂方案 |
|---|---|---|
| 4 个产品 Agent | 区分客户入口、处置、控制面和独立核验 | 不继续增加专用 Agent |
| 4 类 Room 上下文 | 同时满足对客、协作、审批和核验隔离 | 不建设额外消息总线 |
| 3 个 MCP Surface | 在 Gateway 层落实最小权限 | 不为每个 Surface 建独立后端 |

## 12. Implementation Gate

Room 映射、Agent 边界、三个 MCP Surface、状态机与 P2 只记录不执行的范围已确认。后续执行以 [`tasks.md`](./tasks.md) 为唯一任务清单；任何改变上述设计或 Spec 验收口径的事项必须先回到 Planning Agent。
