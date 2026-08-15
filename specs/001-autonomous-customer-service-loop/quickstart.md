# Quickstart：当前基线与目标验收

## 文档状态

- **当前可复现基线**：已实现 + Mock 执行。
- **目标 Linked Journey 验收流程**：方案设计，待用户确认和实现。
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

### 1.4 验证当前 9 个 MCP Tool 与三个 Surface

先按 [`workspace/agentteams/README.md`](../../workspace/agentteams/README.md) 完成本地 AgentTeams/Higress 环境和 MCP 注册，再执行该文件中的 `mcporter list` 与 `mcporter call` 检查。当前三个角色化 Surface 合计暴露：

`resolve_order_reference`、`get_authorized_order`、`evaluate_rebooking`、`record_customer_confirmation`、`record_internal_decision`、`validate_execution_authorization`、`execute_rebooking`、`get_order_state`、`verify_rebooking`。

不要把 Token、API Key 或 Cookie 粘贴进本项目文档、命令输出或截图。

### 1.5 查看 2026-08-12 证据

- [运行说明](../../workspace/runs/2026-08-12-golden-case/README.md)
- [订单定位阶段证据](../../workspace/runs/2026-08-12-golden-case/phase-1-order-matching.json)
- [调查与处置阶段证据](../../workspace/runs/2026-08-12-golden-case/phase-2-resolution.json)
- [独立核验阶段证据](../../workspace/runs/2026-08-12-golden-case/phase-3-verification.json)
- [Case Card](../../workspace/runs/2026-08-12-golden-case/case-card.json)

这组证据证明独立 Worker Task 版本，不证明 Project Room 或角色级 MCP 隔离已经完成。

## 2. 目标连续旅程（待实现，当前不可声称可运行）

### Scene 1：低风险自主改订

1. 复用只包含 Frontline 与 Resolution Worker 的既有 Case Project Room。
2. 在独立 Customer Chat Facade 由 `C001` 发送“酒店查不到我的预订”。
3. 在 Case Project Room 观察 Frontline 直接向 Resolution 交接，不向客户泄漏内部过程。
4. 客户确认 180 元方案后，由 Resolution 通过角色化 MCP Surface 执行一次 Mock 改订。
5. Manager 冻结 Verification Package，并在 Verification 专属 Room 创建独立核验任务。
6. Verification 只读回查，返回 PASS 后由 Frontline 通知客户并关闭 Case。

### Scene 2：供应异常复发与 800 元高风险分支

1. 第一次核验成功后注入替代酒店再次取消事件，恢复同一 Case 与 Project Room。
2. 只提供 800 元候补方案，预期风险决定同时要求内部批准和客户确认。
3. Resolution 在专属 Operations Review Room 请求内部决定。
4. `admin` 模拟 Hotel Operations 发送 `APPROVE`。
5. 只有内部批准时必须拒绝执行；取得当前客户确认后才允许第二次 Mock 改订。

### Scene 3：确认超时、迟到回复与第二次核验

1. Customer Chat Facade 成功发出第二轮方案确认请求。
2. 确定性模拟 24 小时无回复，Case 进入 `CLOSED_INCOMPLETE`。
3. 同一客户在原对话迟到确认，系统恢复原 Case、Conversation 与 Project Room。
4. 双重授权复核通过后执行第二次改订，并由 Verification 独立回读。
5. 第二次核验通过后通知客户并最终关闭 Case。

### 隔离证据

- Case Project Room 成员不包含 Verification Worker。
- Frontline、Resolution、Verification 只能发现各自的 MCP Tool。
- Manager 不挂载业务 MCP。
- Customer Chat Facade 不返回 Project Room、Tool 或内部风险细节。
- Project Room 和 Verification Room 中的 `admin` 只作为平台观察者，不计业务人工介入。

## 3. 公开 Demo 前安全门

1. 轮换模型 API Key 与 AgentTeams/Higress Bearer 凭据。
2. 搜索项目文件、Trace 和截图，确认没有 Token、Cookie、内部路径或真实业务数据。
3. 明确标注哪些能力是“已实现”“模拟执行”“方案设计”“后续规划”。
