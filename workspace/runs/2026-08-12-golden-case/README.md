# GOAI Golden Case 运行证据

## 结论

- AgentTeams Project：`proj-20260812-141056`
- Case：`CASE-GOLDEN-001`
- 运行时间：2026-08-12 22:11–23:06（Asia/Shanghai）
- 最终状态：`RESOLVED`
- 处理模式：`AUTONOMOUS`
- 内部客服/运营介入：`0`
- 独立核验：`PASSED`，7/7 项检查通过

这次运行使用合成客户、订单、供应异常和酒店数据，没有向外部发送消息。

## AgentTeams 任务链

| Phase | Worker | Task ID | 结果 |
|---|---|---|---|
| 安全定位订单 | `order-matcher` | `task-20260812-141502` | 先返回 `MULTIPLE`，补充酒店和入住日期后返回唯一授权 `order_ref` |
| 调查与执行 | `investigation-resolution` | `task-20260812-142155` | 识别 `HOTEL_OVERBOOKED`，风险规则要求客户确认，确认绑定并通过执行授权后完成 Mock 改订 |
| 独立核验 | `verification` | `task-20260812-145800` | 独立回读订单并交叉核验，7/7 检查通过 |

## 安全与执行证据

1. 初次匹配只返回候选数量、缺失字段和空 `candidates`，没有泄露候选订单详情。
2. 唯一匹配只发生在已登录客户 `C001` 的订单范围内，返回不透明 `order_ref`。
3. 价差 180 元由确定性规则 `rebooking-v0.1` 判定为 `REQUIRE_CUSTOMER_CONFIRMATION`。
4. 客户确认事件与 Case、Resolution Plan、Risk Decision 绑定后，执行授权才返回 `authorized=true`。
5. 写操作使用稳定幂等键 `CASE-GOLDEN-001-REBOOK`，执行结果为 `SUCCESS`。
6. Verification Worker 独立回读后确认订单为 `REBOOKED`，酒店、日期、确认号和幂等键均匹配。

结构化快照：

- `phase-1-order-matching.json`
- `phase-2-resolution.json`
- `phase-3-verification.json`
- `case-card.json`

## 运行中发现并修正的问题

- AgentTeams `taskflow` 的 ack/submit 会因任务元数据缺少 `task_title` 报错。本次由 Worker 文件同步和 Manager 更新元数据完成生命周期闭环；业务 Tool 结果不受影响。
- Phase 2 初次执行时，MCP 中的 `resolution_plan` Schema 过宽，Worker 组装了错误的嵌套对象。已把 14 个必需扁平字段写入 Skill 和 MCP YAML，并用同一个 Task 重试成功。
- Phase 2 错误 turn 曾越过 MCP 访问配置面。该 turn 已终止，包含运行凭据的 Worker 缓存、MinIO 副本和会话记录已删除；Skill 已增加白名单、禁止端口扫描、禁止配置面访问和禁止直连 HTTP 的规则。
- Verification Worker 同时调用了 `get_order_state` 与只读 `verify_rebooking` 做交叉核验。两者都没有写操作，后续应统一 Skill 文案与实际验证流程。

## 后续安全动作

由于错误 turn 曾读取到运行凭据，即使相关文件已清理，仍建议轮换当时可见的模型 API Key 与 AgentTeams/Higress Bearer 凭据，再录制对外 Demo。
