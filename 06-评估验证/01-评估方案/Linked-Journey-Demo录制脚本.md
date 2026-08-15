# Linked Journey Demo 录制脚本

**文档状态：** Draft，待 T013 真实运行验证  
**录制目标：** 用一次连续录屏证明同一个客户、同一个 Case 和同一个 Project Room 可以完成两轮酒店供应异常处理。  
**演示口径：** 订单写入调用本地 Mock Order System；Agent 协作在 AgentTeams 中真实发生；客户与运营人员由用户扮演。

## 1. 观众需要看懂什么

1. 客户只和 Frontline Agent 对话，不接触后台推理、Tool 参数或内部运营信息。
2. Frontline Agent 与 Resolution Agent 在同一个 Project Room 直接交接业务事件。
3. 第一轮 180 元方案经客户确认后自动改订，并由 Verification Agent 独立核验。
4. 替代酒店再次取消后，系统复用原 Case 和 Project Room，不重新开 Case。
5. 第二轮 800 元方案必须同时取得运营批准和客户确认。
6. 客户超过 24 小时未回复时 Case 暂时关闭；迟到回复恢复原 Case。
7. 两次执行分别经过独立核验，最终 Case 才进入 `RESOLVED`。

## 2. 录屏布局

- **左侧主窗口：** Customer Chat，展示 Customer 与 Frontline Agent 的对话。
- **右侧主窗口：** AgentTeams Case Project Room，展示结构化业务事件和 Agent 交接。
- **运营审批阶段：** 左侧临时增加或切换 Operations Review 窗口，由用户发送一次 `APPROVE`。
- **Verification Agent：** 不进入 Project Room；Manager 只把核验摘要转发到 Project Room。

正式录制必须通过本地 HTTP 服务打开 Customer Chat，不能直接使用 `file://` 页面。目标地址形式如下：

```text
http://127.0.0.1:19090/?conversation_id=linked-demo-conversation&customer_id=C001
```

## 3. 固定演示身份与数据

| 项目 | 固定值 |
|---|---|
| Customer | `C001` |
| Case | `CASE-GOLDEN-001` |
| Project | `proj-goai-case-golden-001` |
| Conversation | `linked-demo-conversation` |
| 第一轮替代酒店 | 上海虹桥海湾臻选酒店 |
| 第一轮价差 | 180 元 |
| 第二轮替代酒店 | 上海虹桥江景酒店 |
| 第二轮价差 | 800 元 |
| 第一轮确认号 | `RBK-GOLDEN-001-1` |
| 第二轮确认号 | `RBK-GOLDEN-001-2` |

## 4. 正式录制脚本

表格中的“目标响应”是演示时应表达的业务含义。可以有轻微措辞变化，但不得改变订单、金额、酒店、审批或状态事实。

| Cue | 用户操作 | 左侧 Customer Chat 目标响应 | 右侧 Project Room 预期事件 | 埋点 |
|---|---|---|---|---|
| 1 | Customer 发送：“酒店说查不到我的预订，我今天就要入住，麻烦尽快帮我处理。” | Frontline 主动索取酒店名称和入住日期，不展示候选订单。 | 创建并接管 Case；记录信息缺口。 | `DEMO_START` |
| 2 | Customer 发送：“上海虹桥海湾花园酒店，8 月 15 日入住，8 月 17 日退房。” | “已定位您的订单，正在调查酒店无法确认预订的原因。” | `ORDER_LINKED`：Frontline 将安全订单引用交给 Resolution。 | — |
| 3 | 等待后台处理。 | “原酒店因超售无法履约。可以改订至上海虹桥海湾臻选酒店，日期和房型不变，价差 180 元。是否确认？” | `RESOLUTION_PROPOSED`：第一轮方案等待客户确认。 | — |
| 4 | Customer 发送：“我确认接受改订到上海虹桥海湾臻选酒店，价差 180 元。” | 先显示处理中；核验通过后回复：“改订成功，新确认号为 RBK-GOLDEN-001-1。” | `CUSTOMER_CONFIRMATION_RECORDED` → `EXECUTION_RECORDED` → Verification #1 → `VERIFICATION_SUMMARY`。 | `SCENE_1_END` |
| 5 | 不发送消息，由系统注入第二次供应异常。 | Frontline 主动通知：“刚收到新的酒店通知，首次改订的酒店也无法继续履约，我们正在为您寻找替代方案。” | `SUPPLIER_EXCEPTION_RECURRED`；`incident_sequence=2`，Case 和 Project Room 保持不变。 | — |
| 6 | 等待后台处理。 | “目前可以改订至上海虹桥江景酒店，价差 800 元。该方案需要运营人员审核。” | `RESOLUTION_PROPOSED` → 请求 Operations Review。 | — |
| 7 | 切换到 Operations Review，以运营人员身份发送：`APPROVE`。 | Customer Chat 暂时不新增内部审批细节。 | 记录运营批准；Project Room 出现 `OPERATIONS_DECISION_SUMMARY`。 | — |
| 8 | 等待 Frontline 通知。 | “运营审核已通过。是否确认改订至上海虹桥江景酒店，价差 800 元？” | `CUSTOMER_CONFIRMATION_REQUESTED`。 | `SCENE_2_END` |
| 9 | Customer 暂不回复，由系统确定性模拟超过 24 小时。 | “由于暂未收到您的确认，本次处理已暂时关闭。您回复后我们会继续原 Case。” | Case 进入 `CLOSED_INCOMPLETE`，不创建新 Case。 | `TIMEOUT_SIMULATED` |
| 10 | Customer 发送：“刚看到消息，我确认接受改订到上海虹桥江景酒店，价差 800 元。” | “已恢复原处理进度，正在重新校验方案与订单状态。” | 原 Case 恢复；重新校验运营批准、客户确认、订单前置状态和幂等键。 | — |
| 11 | 等待后台执行和核验。 | 核验通过后回复：“改订成功，新确认号为 RBK-GOLDEN-001-2。” | 第二次 `EXECUTION_RECORDED` → Verification #2 → `VERIFICATION_SUMMARY`。 | — |
| 12 | 等待最终通知。 | “您的订单已经处理完成。如需帮助，可以继续在这里回复。” | Case 进入 `RESOLVED`；两轮执行和两次核验均有独立证据。 | `DEMO_END` |

## 5. Project Room 展示要求

右侧只展示短结构化业务事件。每条消息应让观众快速看出：谁完成了什么、交给谁、下一步是什么。

```json
{
  "event_type": "ORDER_LINKED",
  "business_event_id": "<business_event_id>",
  "case_id": "CASE-GOLDEN-001",
  "incident_sequence": 1,
  "state": "RESOLVING",
  "sender_agent": "FRONTLINE",
  "receiver": "RESOLUTION",
  "conclusion": "Customer-owned order was uniquely linked.",
  "next_action": "Investigate the current supplier exception.",
  "evidence_ref": "order-ref://<opaque_order_ref>",
  "occurred_at": "<RFC3339 timestamp>"
}
```

Project Room 不得出现：

- Agent 隐藏推理；
- 原始 MCP 或 Tool Payload；
- API Key、Token 或其他凭据；
- 候选订单和跨客户订单详情；
- 风险规则内部表达式；
- Operations Review 或 Verification Room 的完整对话。

## 6. 开录前检查

- [ ] Docker、AgentTeams、Mock API 和 Customer Chat 均已启动。
- [ ] Customer Chat 使用 `http://` 地址，发送和轮询均正常。
- [ ] 合成数据已重置，初始订单状态为 `CONFIRMED`。
- [ ] 只有一个 `CASE-GOLDEN-001` 和一个对应 Project Room。
- [ ] Customer Chat 左侧与 Project Room 右侧已按录屏尺寸排好。
- [ ] Operations Review 窗口已登录并能发送 `APPROVE`。
- [ ] 五个埋点尚未被旧运行占用。
- [ ] 本轮录制从 `DEMO_START` 前开始，到 `DEMO_END` 后结束。

## 7. 中止并重跑的条件

出现以下任一情况时停止录制，重置数据后从头运行：

- 创建了第二个 Case 或第二个 Project Room；
- Customer Chat 出现内部推理、Tool 参数、运营身份或敏感订单信息；
- 只有运营批准或只有客户确认时发生订单写入；
- 第二次异常没有命中首次改订后的酒店；
- 任一次执行没有独立 Verification Result；
- 核验失败后仍向客户宣告成功；
- 五个埋点缺失、顺序错误或无法对应具体消息。

## 8. 录制完成后的验收结果

录制成功时，Run Manifest 必须满足：

```text
incident_count = 2
execution_count = 2
verification_count = 2
final_case_state = RESOLVED
case_id = CASE-GOLDEN-001
Project Room 数量 = 1
```

本脚本只定义录制口径。只有 T013 真实运行完成并生成 Run Manifest 后，才能将本轮 Demo 标记为“已实现并有运行证据”。
