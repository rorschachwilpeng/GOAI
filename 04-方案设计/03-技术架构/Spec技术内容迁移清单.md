# Spec 技术内容迁移清单

状态：**已迁移，Plan 已确认**  
核对日期：2026-08-14

## 用途

本文件记录 2026-08-13 按 GitHub Spec Kit 精简 `spec.md` 时迁出的有效技术设计，防止当前未提交内容在重构中丢失。

它不是产品需求事实源，也不是正式 `plan.md`。只有用户确认精简后的 Spec 后，才按照本清单创建 Plan 体系；下游文档完成并校验覆盖后，本清单应标记为已迁移。

## 迁移映射

| 原 Spec 内容 | 关键设计结论 | 目标文档 |
|---|---|---|
| 当前实现状态 | 独立 Worker Task 方式已运行；一个 Case 一个 Project Room、业务 Agent 直接协作和 Room 隔离仍待实现；Mock API 为模拟执行 | [`research.md`](../../specs/001-autonomous-customer-service-loop/research.md)、[`plan.md`](../../specs/001-autonomous-customer-service-loop/plan.md) |
| Golden Test 合成数据 | `C001` 两笔订单、`C002` 隔离订单、结构化供应异常、180 元替代方案、300 元规则阈值 | [`data-model.md`](../../specs/001-autonomous-customer-service-loop/data-model.md)、[`quickstart.md`](../../specs/001-autonomous-customer-service-loop/quickstart.md) |
| Golden Test 技术流程 | Customer Service Room 接收客户消息；Manager 创建 Case 和 Project Room；业务 Agent 直接交接；冻结核验输入；只读回查；通知后关闭 | [`plan.md`](../../specs/001-autonomous-customer-service-loop/plan.md) |
| 完整 Case 状态机 | `RECEIVED`、`IDENTIFYING_ORDER`、`AWAITING_CUSTOMER_INFO`、`RESOLVING`、`AWAITING_CUSTOMER_CONFIRMATION`、`AWAITING_INTERNAL_APPROVAL`、`EXECUTING`、`VERIFYING`、`NOTIFYING_CUSTOMER`、`RESOLVED`、`CLOSED_INCOMPLETE`、`MANUAL_REQUIRED` | [`data-model.md`](../../specs/001-autonomous-customer-service-loop/data-model.md) |
| 状态转换和时序 | 信息充分时跳过等待；追问成功后启动 24 小时周期；依据消息到达时间判断截止；关闭后回复恢复原 Case；执行结果未知时先核验，不重复写入 | [`data-model.md`](../../specs/001-autonomous-customer-service-loop/data-model.md) |
| Room 拓扑 | Customer Service、Case Project、Operations Review、Independent Verification 四类 Room；一个 Case 一个 Project Room | [`plan.md`](../../specs/001-autonomous-customer-service-loop/plan.md) |
| Agent Identity | Frontline、Resolution、Manager、Verification 四个 Agent；Manager 不作为每条消息的中转站 | [`plan.md`](../../specs/001-autonomous-customer-service-loop/plan.md) |
| 信息和权限隔离 | 客户只见对客信息；业务 Agent 共享当前 Case 必要上下文；运营 Room 仅风险触发；Verification 不加入 Project Room，也不读取处置讨论或执行自证 | [`plan.md`](../../specs/001-autonomous-customer-service-loop/plan.md) |
| Verification Package | Manager 在核验前冻结 Case 标识、授权订单引用、确认方案、预期结果、BDD 条件和证据引用；不包含隐藏推理或执行返回值 | [`plan.md`](../../specs/001-autonomous-customer-service-loop/plan.md)、[`data-model.md`](../../specs/001-autonomous-customer-service-loop/data-model.md) |
| MVP Skills | `identify-hotel-order`、`investigate-hotel-supply-exception`、`verify-hotel-rebooking` | [`plan.md`](../../specs/001-autonomous-customer-service-loop/plan.md) |
| Order Tools | `resolve_order_reference`、`get_authorized_order`、`execute_rebooking`、`get_order_state`、`verify_rebooking` | [`contracts/mcp-tools.md`](../../specs/001-autonomous-customer-service-loop/contracts/mcp-tools.md) |
| Policy/Risk Tools | `evaluate_rebooking`、`record_customer_confirmation`、`validate_execution_authorization`、计划内 `record_internal_decision` | [`contracts/mcp-tools.md`](../../specs/001-autonomous-customer-service-loop/contracts/mcp-tools.md) |
| Tool 权限 | 每个 Agent 只能发现和调用本角色 Tool Surface；Manager 不调用订单业务工具；Verification 仅只读 | [`plan.md`](../../specs/001-autonomous-customer-service-loop/plan.md)、[`contracts/mcp-tools.md`](../../specs/001-autonomous-customer-service-loop/contracts/mcp-tools.md) |
| 关键数据字段 | Case、Order、Supplier Exception、Resolution Plan、Risk Decision、Confirmation、Execution Record、Verification Result、Verification Package、Case Card 的字段和关系 | [`data-model.md`](../../specs/001-autonomous-customer-service-loop/data-model.md) |
| 技术证据 | Matrix 消息、Room 成员、结构化交接、Skill/MCP 调用、状态 Trace、Package 哈希、幂等记录、订单前后状态 | [`plan.md`](../../specs/001-autonomous-customer-service-loop/plan.md)、[`quickstart.md`](../../specs/001-autonomous-customer-service-loop/quickstart.md)、[`tasks.md`](../../specs/001-autonomous-customer-service-loop/tasks.md) |
| 最小测试集 | Golden Test、缺少确认、800 元高风险、工具假成功、24 小时关闭、关闭后恢复、摘要失败、Room 和 Verification 隔离 | [`plan.md`](../../specs/001-autonomous-customer-service-loop/plan.md)、[`quickstart.md`](../../specs/001-autonomous-customer-service-loop/quickstart.md)；未实现测试待 Tasks 拆解 |
| Agent Infra 赛题映射 | AgentTeams 协同、任务拆解、上下文传递、Skill/MCP、结果验证、审计、审批和经验沉淀 | [`research.md`](../../specs/001-autonomous-customer-service-loop/research.md) |
| 技术取舍 | V0.1 不引入 Nacos、RocketMQ、RAG、向量库、独立数据库或完整 IAM；优先共享状态管理和轨迹可观测 | [`research.md`](../../specs/001-autonomous-customer-service-loop/research.md)、[`plan.md`](../../specs/001-autonomous-customer-service-loop/plan.md) |

## 下游创建顺序

1. ~~用户确认精简后的 `spec.md`。~~ 已完成。
2. ~~创建 `research.md`、`plan.md`、`data-model.md`、`contracts/mcp-tools.md` 和 `quickstart.md`。~~ 已完成。
3. ~~用户评审并确认 `plan.md`。~~ 已完成。
4. ~~从确认后的 Spec 与 Plan 生成 `tasks.md`。~~ 已完成。
5. 按 `tasks.md` 实现、测试并把证据回填到 `06-评估验证/`。
