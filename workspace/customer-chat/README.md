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
