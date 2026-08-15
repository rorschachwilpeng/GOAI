# Customer Chat Facade

本地 Chatbot 由 Mock HTTP 服务同源托管，只调用 Conversation API，并只渲染 `CUSTOMER | FRONTLINE` 白名单消息。它不读取 Matrix、Project Room、MCP 或内部风险数据。

## 边界

- 公开客户路径只能追加 `CUSTOMER` 消息，且必须匹配已绑定的 `customer_id`。
- Frontline 通过独立的内部投影路径写入；该路径需要进程启动时生成或注入的 capability token，不会出现在浏览器 JavaScript 中。
- 这是 MVP 的客户投影隔离，不声称已实现生产 IAM。
- DOM 仅用 `textContent` 写入消息文本，不使用 `innerHTML`。

## 本地查看

1. 启动 `workspace/mock-services/serve_http.py`。
2. 由同一本地 Demo 编排进程建立 Conversation，并保管内部 capability token。
3. 打开 `http://127.0.0.1:19090/?conversation_id=linked-demo-conversation&customer_id=C001`。

T011 只实现页面、独立投影与安全契约；T013 才会用真实运行的 `conversation_id` 启动统一旅程。

## T013-PREP 统一彩排控制器

`workspace/mock-services/rehearsal_controller.py` 是彩排时唯一需要启动的后台进程。
它轮询同一个 Conversation，只把 `CUSTOMER` 消息发给真实
Frontline Worker，并且只有通过 `CUSTOMER_SAFE_REPLY` 契约的返回才会
经受保护的内部端点投影回页面。它还会在同一 Case 中路由
Project Room 交接、Operations 审批和 Verification 核验。

预演适配器使用本地临时 capability token，不得打印或写入仓库：

```bash
GOAI_INTERNAL_TOKEN="$(</tmp/goai-internal-token)" \
PYTHONPATH=workspace/mock-services \
python3 workspace/mock-services/rehearsal_controller.py \
  --customer-id C001 \
  --case-id CASE-SMOKE-REHEARSAL-001 \
  --conversation-id conversation-smoke-rehearsal-001
```

启动后控制器只建立本地 Case/Conversation 并等待第一条客户
消息；不会主动发送录制台词。用户彩排时只需在 Customer Chat
发送客户消息，并在 Operations 镜头中发送一次 `APPROVE`
或 `REJECT`。默认 PREP 模式不生成正式 Run Manifest，不占用
T013 五个录制 Marker。
