# AgentTeams 分层技术架构图设计

## 目标

在现有 16:9 产品架构画布中，解释 AgentTeams 本地部署的组件分层，以及一条用户消息从本地交互到云端 Kimi 推理再返回的完整链路。

## 画布结构

- 左侧约 57%：五层技术架构，按交互、通信、Agent 执行、编排治理、数据运行从上到下排列。
- 右侧约 43%：单次对话时序图，以用户、Element、Matrix、Manager、Higress、Kimi、Tool/Worker 为参与者。
- 顶部：标题、当前部署标签和本地/云端图例。
- 底部：一句话总结数据边界——状态本地持久化，推理上下文按次发送至云端。

## 左侧分层

1. 交互层：Element Web，承接聊天、人工介入和历史查看。
2. 通信层：Matrix Protocol + Tuwunel，承接身份、Room、Event、同步与消息持久化。
3. Agent 执行层：QwenPaw / CoPaw Manager 与 Worker Runtime，承接 Session、Memory、Skills、Agent Loop 和工具调用。
4. 编排与治理层：AgentTeams Controller、Higress、Skills Registry，承接 Agent 生命周期、模型路由、凭据隔离和能力分发。
5. 数据与运行层：MinIO、Agent Memory、Docker、Log & Audit，承接文件、状态、运行隔离和审计。

Nacos 明确标记为后续可选的 Skills Registry，不画成当前本地必装组件。

## 右侧时序

主路径为：用户输入 → Element 发送 Event → Matrix 持久化并同步 → Manager 恢复 Session、组装上下文 → Higress 代理请求 → Kimi 云端推理 → 可选 Tool/Worker 执行 → Manager 回写 Matrix → Element 实时展示。

颜色语义：蓝色代表本地通信，紫色代表云端模型调用，橙色代表工具或 Worker 执行，红色代表 Human Review 风险关卡。

## 验收标准

- 1440×900 和常见 16:9 窗口中无需滚动即可读完主体。
- 10 秒内能够判断各组件所在层级、本地/云端边界和消息调用顺序。
- 不把 QwenPaw 误写成模型，不把 Matrix 误写成 Agent Runtime，不把 Nacos误写成当前已安装组件。
- `npm run build` 与 `npm run test:sites` 通过。
