# Research：酒店供应异常自主改订最小闭环

## 文档状态

| 字段 | 内容 |
|---|---|
| 状态 | Completed for Approved Plan |
| 日期 | 2026-08-14 |
| 上游 | [`spec.md`](./spec.md)（Approved） |
| 用途 | 记录已核验事实、技术取舍与未关闭风险，不替代 Spec 或 Plan |

## 1. 官方约束

依据 [GOAI Agent Infra 赛道详情](https://www.goaihz.com/tracks?track=infra)：

| 约束 | 本项目响应 | 状态 |
|---|---|---|
| 至少 3 个不同职能 Agent | Frontline、Resolution、Verification；Manager 负责控制面 | 方案设计；现有 3 个 Worker 已运行 |
| 以 AgentTeams 为多 Agent 协同基点 | 当前使用 AgentTeams 1.2.2；目标采用原生 Project Room | 已实现基线 / 待迁移 |
| Skill 为必选能力 | 已有订单识别、供应异常调查、改订核验 3 个 Skill | 已实现 |
| 高风险动作需人工确认、审批、回滚与审计设计 | 800 元分支阻断已验证；APPROVE / REJECT 记录接口待实现 | 模拟执行 / 方案设计 |
| 需要结果验证与执行证据 | Golden Case 有 Trace、结果、Case Card 和独立回读核验 | 已实现 + 模拟执行 |

## 2. 当前可核验基线（As-Is）

| 能力 | 核验事实 | 真实性 |
|---|---|---|
| AgentTeams 编排 | Manager 依次向 `order-matcher`、`investigation-resolution`、`verification` 三个独立 Worker Task 派单 | 已实现 |
| Skills | `identify-hotel-order`、`investigate-hotel-supply-exception`、`verify-hotel-rebooking` | 已实现 |
| MCP | 一个 `mcp-goai-order` 配置暴露 8 个 Tool，三个 Worker 均连接完整 Server | 已实现 |
| 业务系统 | Python 3.13 Mock HTTP API + JSON 合成订单、异常、替代酒店与规则 | 模拟执行 |
| Golden Case | 2026-08-12 证据显示 `RESOLVED`、`AUTONOMOUS`、核验 7/7 通过、内部人工介入 0 次 | 已实现 + 模拟执行 |
| 安全护栏 | 跨客户拒绝、缺确认阻断、800 元审批阻断、假成功核验失败、幂等冲突均有测试 | 已实现 + 模拟执行 |

现有证据入口：[`workspace/runs/2026-08-12-golden-case/README.md`](../../workspace/runs/2026-08-12-golden-case/README.md)。

## 3. 目标差距（To-Be）

| 目标 | 当前差距 | 状态 |
|---|---|---|
| 一个 Case 对应一个 AgentTeams Project / Project Room | 当前仍是 Manager 向独立 Worker Task 顺序派单 | 方案设计，待实现 |
| Frontline 与 Resolution 在 Project Room 直接交接 | 当前交接由 Manager 中转 | 方案设计，待实现 |
| Verification 与处置讨论隔离 | 当前有独立 Verification Worker，但未按 V7 Room 拓扑冻结输入 | 部分已实现，待迁移 |
| 角色级 Tool Surface | 当前三个 Worker 可发现完整 8 Tool Server，权限主要依赖 Skill 文案 | 方案设计，待实现 |
| 运营人员记录 APPROVE / REJECT | 当前 800 元分支只会返回 `INTERNAL_APPROVAL_REQUIRED` | 方案设计，待实现 |

## 4. 技术取舍

| 决策 | 选择 | 原因 |
|---|---|---|
| Room 映射 | 使用 AgentTeams 原生 Project Room 与 Worker 专属 Room | 最小改造即可展示共享协作与上下文隔离 |
| MCP 权限 | 一个 Higress Gateway，注册三个角色化 MCP Surface | 保留统一入口，同时限制 Tool 的发现与调用 |
| 风险服务 | 逻辑上独立于订单系统，MVP 可与 Mock 后端同进程部署 | 职责分离，不为部署数量过度工程化 |
| 状态与协作 | Manager 维护 Case、SLA、任务和阶段闸门 | 避免业务 Agent 同时承担控制面 |
| 暂不建设 | Nacos、RocketMQ、RAG、向量库、生产数据库、完整 IAM | 不影响 Golden Journey 验收，且会延迟参赛闭环 |

## 5. 风险记录

- **凭据风险**：历史运行曾让 Worker 访问不应进入业务上下文的配置面。公开 Demo 前必须轮换模型 API Key 与 AgentTeams/Higress Bearer 凭据，并重新检查截图与 Trace。
- **权限真实性**：角色级 Tool Surface 尚未注册完成前，不得声称网关已实现强制最小权限。
- **身份真实性**：MVP 使用同一个 `admin` 在不同专属 Room 中模拟客户和运营人员，只证明 Room 与 Agent 权限隔离，不代表生产 IAM。
- **架构真实性**：V7 是目标设计；2026-08-12 Golden Case 是独立 Worker Task 的现有证据。两者不可混写。

## 6. 结论

当前基线已经证明“多 Agent + Skill + MCP + Mock 写入 + 独立核验”的业务可行性。Plan 的核心不是增加组件，而是把现有闭环迁移为原生 Project Room 协作，并把角色权限从 Skill 文案提升为 MCP Tool 的可发现性约束。
