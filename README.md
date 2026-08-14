# GOAI｜酒店供应异常智能客服自主闭环

## 项目目标

面向酒店供应异常，使用 AgentTeams 构建一条可验证的多 Agent 客服闭环：Agent 主动向已登录客户补充索取必要信息，在客户数据范围内安全定位订单，调查供应异常并生成改订方案，经客户确认后自动执行，最后独立核验结果、通知客户并关闭 Case。

当前阶段只使用合成数据、公开资料和重新抽象的行业流程，不接入真实订单系统，不使用 PKFARE 内部代码、客户数据、工单或未公开规则。

## 目录结构

| 目录 | 作用 |
|---|---|
| `specs/` | 按 GitHub Spec Kit 规则管理的正式功能 Spec，是行为与验收的事实源 |
| `01-项目背景/` | 问题背景、项目定位、目标用户与行业价值 |
| `02-赛事调研/` | 官方规则、赛道要求、技术选型与竞品参考 |
| `03-需求定义/` | 最小闭环范围、用户故事、流程与验收边界 |
| `04-方案设计/` | 业务闭环、Agent/Skill、技术架构与安全治理方案 |
| `05-数据资产/` | 合成案例、输入输出 Schema、案例知识资产 |
| `06-评估验证/` | 评估口径、测试集、运行结果与问题记录 |
| `07-参赛材料/` | PPT、架构图、截图、Trace 和演示视频素材 |
| `08-交付输出/` | 最终 PDF、作品简介、演示包与提交 ZIP |
| `workspace/` | AgentTeams 配置、Skills、模拟服务、运行脚本和 runs |

Spec 从 `spec.md` 开始，经用户确认后再生成 Plan；只有 Spec 与 Plan 都确认后才生成 Tasks。当前 `spec.md` 与 `plan.md` 均已确认，实施任务见 [`tasks.md`](./specs/001-autonomous-customer-service-loop/tasks.md)。详细规则见 [`AGENTS.md`](./AGENTS.md) 与 [`specs/README.md`](./specs/README.md)。

## 当前已实现基线

- AgentTeams Manager 依次向 Frontline、Resolution、Verification 对应的三个独立 Worker Task 派单；现有运行资产仍保留旧 Worker 名称。
- 3 个 Skill、8 个 MCP Tool、Python Mock API、合成订单数据和单元测试已经存在。
- 2026-08-12 Golden Case 已完成 180 元价差的 Mock 改订、独立回读核验、Trace 和 Case Card。
- 跨客户访问、缺少确认、800 元内部审批阻断、工具假成功和幂等冲突已有测试。

以上属于“已实现 + 模拟执行”，不代表 Project Room 和角色级 Tool 权限已经完成。

## 目标架构（Plan Approved，Tasks Ready）

1. Frontline Agent 负责客户沟通、安全定位订单与记录客户确认；
2. Resolution Agent 负责异常调查、方案、风险判断和受控执行；
3. 两个业务 Agent 在一个 Case 对应的 Project Room 直接协作，Manager 只维护 Case、SLA、任务和阶段闸门；
4. Verification Agent 不加入 Project Room，只接收冻结后的输入并只读回查；
5. Customer Service、Case Project、Operations Review、Independent Verification 四类 Room 分离信息边界；
6. 一个 Higress Gateway 注册 Frontline、Resolution、Verification 三个角色化 MCP Surface，Manager 不挂载业务 Tool；
7. 800 元高风险分支只实现运营人员的 `APPROVE / REJECT` 记录与授权判断，不执行高风险改订。

详细设计见 [`plan.md`](./specs/001-autonomous-customer-service-loop/plan.md)，实施按 [`tasks.md`](./specs/001-autonomous-customer-service-loop/tasks.md) 分阶段推进；能力在验收前仍保持“方案设计”口径。

## 边界

- 初赛优先交付高质量方案与一条最小可验证链路，不建设完整客服平台。
- 所有“执行”均针对合成订单数据库或 Mock API。
- MVP 不实现供应商邮件解析、多渠道聚合、RAG、向量库或历史 Case 召回。
- 高风险动作保留内部审批边界；Golden Test 主路径只验证客户确认后的自主改订。
- 已实现能力、模拟能力与未来规划必须在材料中明确区分。
- 对外报名、提交作品、加入群聊或发送消息，必须由用户逐次授权。
