# T005 Project Room Migration Evidence

取证日期：2026-08-14。

已实现（本地 AgentTeams 运行时）：创建 Project `proj-goai-case-golden-001`，Room 为 `!tARkhuXsazrkPWbLfV:matrix-local.agentteams.io:18080`；成员为 admin、Manager、Frontline、Resolution，Verification 不在 Room 内。

本地 Matrix Room：[在 Element 中打开 Project Room](http://127.0.0.1:18088/#/room/!tARkhuXsazrkPWbLfV:matrix-local.agentteams.io:18080)。

已实现：Frontline 与 Resolution 使用真实 Matrix `m.mentions` 在该 Room 完成一次结构化交接和一次非循环回执（HTTP 200）。

已实现：两名 Worker 的 group allow policy 各自保留 admin、Manager 与对方；DM allowlist 未改变。

模拟执行：业务 MCP 连接的是本地合成 Mock 服务。未声明 Higress 运行时权限隔离以外的生产能力。

未实现：Golden Journey V2（T006）尚未执行。

安全修复：Resolution 的 Higress consumer key 已轮换；旧 key 授权请求返回 HTTP 401。独立验收发现 `resolution_plan` 参数的 `required` 同时被定义为布尔值与字段数组，Higress 因类型冲突未加载 MCP 插件并返回 HTTP 503。仓库 YAML 已改为仅保留参数级 `required: true`，重新注册后 Resolution Worker 可发现且仅发现 4 个 Tool。

工具边界：Resolution 仅配置 `mcp-goai-resolution`（4 个契约 Tool：`get_authorized_order`、`evaluate_rebooking`、`validate_execution_authorization`、`execute_rebooking`）；Frontline 保持其 2 个契约 Tool。Manager 未新增角色 Surface，旧 Worker 未保留 Resolution Surface。Higress 的允许消费者已收敛为 Frontline → `worker-frontline`、Resolution → `worker-resolution`、Verification → `worker-verification`；Resolution 凭据访问另外两个 Surface 均返回 HTTP 403。

链路复验：先由 Frontline Surface 返回 `UNIQUE` 与不透明 `order_ref`，再由 Resolution Surface 调用只读 `get_authorized_order`，成功读取 C001 的合成订单、供应异常与 180 元替代方案；未执行订单写入。现有 Python 测试共 39 项，全部通过。

迁移策略：新 `frontline` 与 `resolution` Worker 为 `Running`；旧 `order-matcher`、`investigation-resolution` 与 `verification` Worker 保持 `Sleeping`，暂不删除，作为回滚参照。
