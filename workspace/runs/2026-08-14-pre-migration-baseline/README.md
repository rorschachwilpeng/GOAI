# GOAI T001：迁移前基线与回滚参照

- 任务：`GOAI-EXEC-001 / T001`
- 取证日期：2026-08-14（Asia/Shanghai）
- 测试结论：26 个现有单元测试通过，完整原始输出见 [`test-output.txt`](./test-output.txt)。

## 当前能力口径

| 口径 | 迁移前事实 |
| --- | --- |
| 已实现 | 3 个 Worker、3 个本项目 Skill、单一 MCP Server 的 8 个 Tool，以及 Manager 分配 Worker Task 的运行资产。 |
| 模拟执行 | 酒店订单识别、风险判断、客户确认、改订和独立核验均通过本地 Python Mock 服务与合成数据完成。 |
| 方案设计 | 一 Case 一 Project Room、Frontline 与 Resolution 直接协作、角色级 MCP Surface、冻结 Verification Package 与 Operations Review Room。 |
| 后续规划 | 生产订单系统、真实客户/供应商接入和生产化治理。 |

## 当前独立 Worker 基线

本基线为**独立 Worker Task，非 Project Room**。Manager 依次向 Worker 分配订单定位、调查与受控执行、独立核验任务；现有证据不证明共享 Case Project Room 或角色级 MCP 权限已经实现。

| 类型 | 当前资产 |
| --- | --- |
| Worker（3） | `order-matcher`、`investigation-resolution`、`verification` |
| Skill（3） | `identify-hotel-order`、`investigate-hotel-supply-exception`、`verify-hotel-rebooking` |
| MCP Tool（8） | `resolve_order_reference`、`get_authorized_order`、`evaluate_rebooking`、`record_customer_confirmation`、`validate_execution_authorization`、`execute_rebooking`、`get_order_state`、`verify_rebooking` |
| MCP 配置 | `workspace/agentteams/mcp-goai-order.yaml`，迁移前单一 Tool Surface |

## 旧证据入口

- [Golden Case 运行说明](../2026-08-12-golden-case/README.md)
- [订单定位阶段](../2026-08-12-golden-case/phase-1-order-matching.json)
- [调查与执行阶段](../2026-08-12-golden-case/phase-2-resolution.json)
- [独立核验阶段](../2026-08-12-golden-case/phase-3-verification.json)
- [Case Card](../2026-08-12-golden-case/case-card.json)
- [单 Worker Smoke 运行说明](../2026-08-12-order-matcher-smoke.md)

## SHA-256 回滚参照

以下为迁移前相关源文件、测试与既有 Golden Case 证据的 SHA-256。仅纳入项目资产；不包含缓存、临时输出或任何凭据。

| 文件 | SHA-256 |
| --- | --- |
| `workspace/agentteams/order-matcher-smoke-worker.yaml` | `1e228c89557c1c24ebde83deca96f9db954e635910a6299fc279168d66b3a856` |
| `workspace/agentteams/investigation-resolution-worker.yaml` | `b498c688dd0acb8083a297a79a61eb28fc160ec859bc7e1c63683f5ee32c4d14` |
| `workspace/agentteams/verification-worker.yaml` | `dbfa6a9097c1cd8ebc65e3e9872ceafbb7e89835f173a0b35948352715ac4d3d` |
| `workspace/agentteams/mcp-goai-order.yaml` | `b4a4f10218d510898324896fc4ec4462a75bd507a2fb40b8e647a604a8221e94` |
| `workspace/skills/identify-hotel-order/SKILL.md` | `12d2d1b052a5af49477fd11b2be13011c6d9d4638118c512fc372958be5058e6` |
| `workspace/skills/investigate-hotel-supply-exception/SKILL.md` | `4a90d0f4a20c14bc4bf18b04cbf9ce344829a5eeb65402f27f15ceca45539ea7` |
| `workspace/skills/verify-hotel-rebooking/SKILL.md` | `ce960bb6ad4c2efd8b2f8a78ce0547b0ac4e25c14ba2c566b1e43df5679d37c4` |
| `workspace/mock-services/golden_path.py` | `d5e7fa73de97a7b1274db6ad3a7990e04d9f1cc6f32e9f392dbfeeb490fff506` |
| `workspace/mock-services/run_golden_path.py` | `8d15c835ac0af4c0331896e6938046d34b6eec84e4b029f73500fc659d33c93e` |
| `workspace/mock-services/serve_http.py` | `3bfe291d552805f9bd8bd8654843639071c3eddc05dc8bf55da9287e08d38c27` |
| `workspace/mock-services/tests/test_golden_path.py` | `410054aa752b9d60f47ccbf0a0dc2699f2588c4f3bfba06789b8bf3bb06431b7` |
| `workspace/mock-services/tests/test_http_api.py` | `9dc28434bf7d01a7ba1affbce5ca1af8496dc8cc3573094ecd31dfcd494595b4` |
| `workspace/runs/2026-08-12-golden-case/README.md` | `a0de97902baa5fcc3b5bfe14ac28d5f6137aaf6b9e9314b81c4290b6d2ee7935` |
| `workspace/runs/2026-08-12-golden-case/phase-1-order-matching.json` | `9077872a8076aebf0f19c8daeb31e975eec7297fd7edd76a2c856f0febc0441c` |
| `workspace/runs/2026-08-12-golden-case/phase-2-resolution.json` | `2fbf637f297f41827f27fc1bb8b2fa904507af1238910945b51e1f9b33b864dd` |
| `workspace/runs/2026-08-12-golden-case/phase-3-verification.json` | `70849e50a276ea354541d55c3c5597096ff84ad01085ca28876a60b9c6cc6a2e` |
| `workspace/runs/2026-08-12-golden-case/case-card.json` | `bb3f6a2ef175e35d231317c9bc047a23cc498a7c047d7b2347c678ca94e2e369` |
