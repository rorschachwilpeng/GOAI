# Research：酒店供应异常自主改订最小闭环

## 文档状态

| 字段 | 内容 |
|---|---|
| 状态 | Updated for Linked Journey Draft |
| 日期 | 2026-08-15 |
| 上游 | [`spec.md`](./spec.md)（Draft — Linked Journey Revision） |
| 用途 | 记录已核验事实、技术取舍与未关闭风险，不替代 Spec 或 Plan |

## 1. 官方约束

依据 [GOAI Agent Infra 赛道详情](https://www.goaihz.com/tracks?track=infra)：

| 约束 | 本项目响应 | 状态 |
|---|---|---|
| 至少 3 个不同职能 Agent | Frontline、Resolution、Verification；Manager 负责控制面 | 方案设计；现有 3 个 Worker 已运行 |
| 以 AgentTeams 为多 Agent 协同基点 | 使用 AgentTeams 1.2.2，已创建原生 Project Room | 已实现 |
| Skill 为必选能力 | 已有订单识别、供应异常调查、改订核验 3 个 Skill | 已实现 |
| 高风险动作需人工确认、审批、回滚与审计设计 | 800 元分支阻断与 APPROVE / REJECT 记录已验证；双重授权执行待实现 | 模拟执行 / 方案设计 |
| 需要结果验证与执行证据 | Golden Case 有 Trace、结果、Case Card 和独立回读核验 | 已实现 + 模拟执行 |

## 2. 当前可核验基线（As-Is）

| 能力 | 核验事实 | 真实性 |
|---|---|---|
| AgentTeams 编排 | 已创建只含 Frontline、Resolution 业务 Worker 的 Case Project Room；Verification 独立运行 | 已实现 |
| Skills | `identify-hotel-order`、`investigate-hotel-supply-exception`、`verify-hotel-rebooking` | 已实现 |
| MCP | 已拆分 Frontline、Resolution、Verification 三个角色化 Surface，共 9 个 Tool | 已实现 |
| 业务系统 | Python 3.13 Mock HTTP API + JSON 合成订单、异常、替代酒店与规则 | 模拟执行 |
| Golden Case | 2026-08-12 证据显示 `RESOLVED`、`AUTONOMOUS`、核验 7/7 通过、内部人工介入 0 次 | 已实现 + 模拟执行 |
| 安全护栏 | 跨客户拒绝、缺确认阻断、800 元审批阻断、假成功核验失败、幂等冲突均有测试；当前共 49 个测试 | 已实现 + 模拟执行 |

现有证据入口：[`workspace/runs/2026-08-12-golden-case/README.md`](../../workspace/runs/2026-08-12-golden-case/README.md)。

## 3. 目标差距（To-Be）

| 目标 | 当前差距 | 状态 |
|---|---|---|
| 客户独立 Chatbot 与消息投影 | 当前仍由 Frontline Runtime Room 直接展示内部过程 | 方案设计，待实现 |
| 同一 Case 串联两轮供应异常 | 当前 P1、P2、P3 分别运行，未形成连续旅程 | 方案设计，待实现 |
| 高风险双重授权执行 | 当前 APPROVE 可记录，但高风险写入仍被硬阻断 | 方案设计，待实现 |
| 每次写入独立核验 | 当前只完成第一轮一次核验 | 部分已实现，待扩展 |
| 可录制结构化事件与起止埋点 | 当前 Room 消息较长且没有统一 Manifest | 方案设计，待实现 |

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
- **客户隔离真实性**：Customer Chat Facade 完成前，不得把 Frontline Runtime Room 截图包装为客户产品界面。
- **身份真实性**：MVP 使用同一个 `admin` 在不同专属 Room 中模拟客户和运营人员，只证明 Room 与 Agent 权限隔离，不代表生产 IAM。
- **架构真实性**：V7 是上一版架构参考；Linked Journey 变更以 2026-08-15 Draft 文档为准。旧独立 Run 只能作为回归证据。

## 6. 结论

当前基线已经证明 Project Room、角色化 MCP Surface、Mock 写入、运营决定和独立核验可行。下一阶段不再增加基础设施，而是把这些能力串成同一 Case 的连续旅程，并补上客户隔离、双重授权、第二次核验和可录制证据。
