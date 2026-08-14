# Workspace

本目录只承接 GOAI 项目的运行资产：

| 目录 | 作用 |
|---|---|
| `agentteams/` | AgentTeams 角色定义、团队配置与本地部署辅助资产 |
| `skills/` | 本项目自定义 Skills |
| `mock-services/` | 合成订单数据库与受控执行 API |
| `runs/` | 每次端到端运行的结构化日志和结果 |
| `agent-infra-product-architecture/` | 已有技术架构图 HTML 工程 |

`install-agentteams-kimi.sh` 是本机 AgentTeams 安装辅助脚本，不包含明文 API Key。

正式功能规格统一放在项目根目录 `specs/`；实际 JSON Schema 放在 `05-数据资产/schemas/`，代码内的接口约束随对应实现保存。
