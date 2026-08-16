# GOAI Demo 代码包

本代码包包含初赛 Demo 使用的 AgentTeams 配置、自定义 Skills、本地 Mock 业务服务、客户聊天页面和测试。运行资产统一放在 `workspace/` 下，以保持与项目源码一致的相对路径。

## 目录

- `workspace/agentteams/`：Agent 定义、MCP 配置和协作 Runbook
- `workspace/skills/`：订单定位、异常处置和改订核验 Skills
- `workspace/mock-services/`：合成订单数据、受控业务 API、旅程控制器和测试
- `workspace/customer-chat/`：面向客户的隔离聊天页面
- `workspace/runs/`：测试所需的合成 Project Room 映射样例

## 本地验证

```bash
cd workspace/mock-services
python -m unittest discover -s tests -v
```

所有订单、客户、异常与审批数据均为合成数据。运行时凭据不包含在代码包中。
