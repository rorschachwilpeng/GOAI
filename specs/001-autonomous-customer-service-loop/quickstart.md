# Quickstart：当前基线与目标验收

## 文档状态

- **当前可复现基线**：已实现 + Mock 执行。
- **目标 Room 验收流程**：方案设计，待 Plan 确认和实现。
- 本文不包含真实凭据；不执行外部消息或提交。

以下命令均在 GOAI 项目根目录运行。

## 1. 当前可复现基线

### 1.1 运行单元测试

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s workspace/mock-services/tests -v
```

该命令验证 Golden Path、跨客户拒绝、缺确认阻断、800 元审批阻断、假成功、幂等和 HTTP 路由。

### 1.2 启动 Mock API

```bash
PYTHONDONTWRITEBYTECODE=1 python3 workspace/mock-services/serve_http.py \
  --host 0.0.0.0 --port 19090
```

另一个终端执行：

```bash
curl -s http://127.0.0.1:19090/health
curl -s -X POST http://127.0.0.1:19090/reset \
  -H 'Content-Type: application/json' -d '{}'
```

预期分别返回 `{"status":"ok"}` 与 `{"status":"reset"}`。

### 1.3 重跑确定性 Golden Path

```bash
PYTHONDONTWRITEBYTECODE=1 python3 workspace/mock-services/run_golden_path.py \
  --output-dir tmp/goai-golden-check
```

预期结果包含：`case_state=RESOLVED`、`resolution_mode=AUTONOMOUS`、`order_state=REBOOKED`、`verification_status=PASSED`、`internal_human_interventions=0`。

### 1.4 验证当前 8 个 MCP Tool

先按 [`workspace/agentteams/README.md`](../../workspace/agentteams/README.md) 完成本地 AgentTeams/Higress 环境和 MCP 注册，再执行该文件中的 `mcporter list` 与 `mcporter call` 检查。当前单个 Server 应暴露：

`resolve_order_reference`、`get_authorized_order`、`evaluate_rebooking`、`record_customer_confirmation`、`validate_execution_authorization`、`execute_rebooking`、`get_order_state`、`verify_rebooking`。

不要把 Token、API Key 或 Cookie 粘贴进本项目文档、命令输出或截图。

### 1.5 查看 2026-08-12 证据

- [运行说明](../../workspace/runs/2026-08-12-golden-case/README.md)
- [订单定位阶段证据](../../workspace/runs/2026-08-12-golden-case/phase-1-order-matching.json)
- [调查与处置阶段证据](../../workspace/runs/2026-08-12-golden-case/phase-2-resolution.json)
- [独立核验阶段证据](../../workspace/runs/2026-08-12-golden-case/phase-3-verification.json)
- [Case Card](../../workspace/runs/2026-08-12-golden-case/case-card.json)

这组证据证明独立 Worker Task 版本，不证明 Project Room 或角色级 MCP 隔离已经完成。

## 2. 目标验收流程（待实现，当前不可声称可运行）

### P1：自主改订

1. 创建只包含 Frontline 与 Resolution Worker 的 AgentTeams Project，使其生成 Case Project Room。
2. 在 Frontline 专属 Room 由 `admin` 模拟 `C001`，发送“酒店查不到我的预订”。
3. 在 Case Project Room 验证 Frontline 直接向 Resolution 交接已授权订单引用，不由 Manager 逐条转发。
4. 客户确认 180 元方案后，由 Resolution 通过角色化 MCP Surface 执行一次 Mock 改订。
5. Manager 冻结 Verification Package，并在 Verification 专属 Room 创建独立核验任务。
6. Verification 只读回查，返回 PASS 后由 Frontline 通知客户并关闭 Case。

### P2：800 元高风险分支

1. 把方案价差设置为 800 元，预期风险决定为 `REQUIRE_INTERNAL_APPROVAL`。
2. Resolution 在专属 Operations Review Room 请求内部决定。
3. `admin` 模拟 Hotel Operations，只发送 `APPROVE` 或 `REJECT`。
4. 验证决定与 Case、方案、风险决定、运营人员和 Matrix 事件绑定。
5. `REJECT` 必须拒绝授权；`APPROVE` 只验证授权结果，V0.1 不继续执行高风险改订。

### 隔离证据

- Case Project Room 成员不包含 Verification Worker。
- Frontline、Resolution、Verification 只能发现各自的 MCP Tool。
- Manager 不挂载业务 MCP。
- Project Room 和 Verification Room 中的 `admin` 只作为平台观察者，不计业务人工介入。

## 3. 公开 Demo 前安全门

1. 轮换模型 API Key 与 AgentTeams/Higress Bearer 凭据。
2. 搜索项目文件、Trace 和截图，确认没有 Token、Cookie、内部路径或真实业务数据。
3. 明确标注哪些能力是“已实现”“模拟执行”“方案设计”“后续规划”。
