# AgentTeams Golden Path 接入

## T005 Project Room（本地运行时证据）

`proj-goai-case-golden-001` 仅包含 `frontline,resolution` 两名业务 Worker；Verification 不加入 Case Project Room。运行证据见 `../runs/2026-08-14-project-room-migration/`。该能力使用本地 AgentTeams 与合成 Mock 服务，不代表生产环境部署。

## T013-PREP 客户投影与统一旅程

- `../mock-services/rehearsal_controller.py`：默认以 PREP 模式等待
  Customer Chat 的第一条客户消息，再把同一 Case 的客户投影、
  Project Room、Operations 和 Verification 路由串起来。
- `../mock-services/run_customer_bridge.py`：仅保留为单条客户消息的底层
  Frontline 联动适配器，录屏彩排不单独运行它。
- `../mock-services/linked_journey_bridge.py`：验证客户投影、Project Room
  结构化事件、Operations 路由和独立 Verification Package。
- `../mock-services/agentteams_transport.py`：每次发送前 `ensure-ready`，通过
  Matrix mention 触发对应 Worker，密钥仍留在现有 Manager 容器内。
- Verification 不是只收到 Package：Transport 必须在 Verification
  专属 Room 等待该 Worker 的严格 `VERIFICATION_RESULT`，验证真实
  sender、Case、事故序号、状态与 evidence 后，Manager 才能发布摘要。
  在真实 Result 通过前 Case 保持 `VERIFYING`；失败、超时或不一致使
  Case 进入 `MANUAL_REQUIRED`。
- `../mock-services/journey_orchestrator.py`：只自动推进第二次供应异常和
  24 小时客户确认超时；不代替客户确认或运营审批。

T013-PREP 已在唯一正式 Project Room 上使用 `CASE-SMOKE-*` 完成真实
Frontline `ORDER_LINKED` → Resolution `RESOLUTION_ACCEPTED` 结构化交接。
另一条 `CASE-SMOKE-*` 已验证 Verification 专属 Room 中真实
Worker 回复被消费，且同 Case 在 Project Room 中的消息数为 0。
该 Smoke 不是正式 T013 运行证据。

本目录保存 GOAI Mock API 接入 AgentTeams 所需的 Higress MCP 配置、3 个 Worker manifest 与重跑说明。`mcp-goai-order` 当前暴露 8 个受控 Tool，覆盖安全定位订单、风险评估、客户确认、执行与独立核验。

> 以下注册命令会修改本机 AgentTeams/Higress 配置。当前本机环境已完成注册；重装或重建环境时再执行。

## 资产

- `mcp-goai-order.yaml`：AgentTeams v1.2.2 Higress REST-to-MCP 配置。
- `order-matcher-smoke-worker.yaml`：订单安全定位 Worker。
- `investigation-resolution-worker.yaml`：调查、风险判断与受控执行 Worker。
- `verification-worker.yaml`：独立回读与结果核验 Worker。
- 后端 API：`http://host.docker.internal:19090` 下的 8 个业务端点与 `/reset`。
- MCP Server 名：`mcp-goai-order`（安装脚本自动为 `goai-order` 加上 `mcp-` 前缀）。

YAML 格式已对齐本机 AgentTeams v1.2.2 的：

- `/Users/pengyoutian/agentteams-manager/skills/mcp-server-management/scripts/setup-mcp-server.sh`
- `/Users/pengyoutian/agentteams-manager/skills/mcp-server-management/references/mcp-github.yaml`

## 1. 启动宿主机 Mock API

在 GOAI 项目根目录执行：

```bash
PYTHONDONTWRITEBYTECODE=1 \
  python3 workspace/mock-services/serve_http.py --host 0.0.0.0 --port 19090
```

另开一个终端验证宿主机 API：

```bash
curl -fsS http://127.0.0.1:19090/health

curl -fsS \
  -H 'Content-Type: application/json' \
  -d '{"customer_id":"C001","clues":{}}' \
  http://127.0.0.1:19090/resolve-order-reference
```

第二个请求应返回 `status=MULTIPLE`，且不应包含任何候选订单详情。

每次重新演示 Golden Case 前必须重置进程内状态：

```bash
curl -fsS \
  -H 'Content-Type: application/json' \
  -d '{}' \
  http://127.0.0.1:19090/reset
```

## 2. 验证 AgentTeams 容器访问宿主机

先确认 Docker Engine 和已有 `agentteams-manager` 容器正在运行，再执行：

```bash
docker exec agentteams-manager \
  curl -fsS http://host.docker.internal:19090/health
```

只有该命令成功后才进入 MCP 注册。失败时先修复容器到宿主机的网络访问，不要创建 Worker 或更改 Tool URL。

## 3. 注册 Higress MCP Server

下列命令必须在宿主机执行。`setup-mcp-server.sh` 强制要求第二个位置参数；本 API 无鉴权，因此传入非密钥字面值 `unused`。YAML 不会将它发送给 Mock API。

本机 AgentTeams v1.2.2 使用 Manager 与 Controller 分体容器，但安装脚本把 Higress Console 固定为 Manager 容器内的 `127.0.0.1:8001`。因此需要复制临时脚本并把地址改为 `agentteams-controller:8001`；临时脚本和 Cookie 在命令结束时删除。

```bash
docker exec agentteams-manager bash -lc '
set -euo pipefail
tmp_script=$(mktemp /tmp/goai-register-mcp.XXXXXX)
cookie_file=$(mktemp /tmp/goai-higress-cookie.XXXXXX)
cleanup() { rm -f "$tmp_script" "$cookie_file"; }
trap cleanup EXIT

cp /root/manager-workspace/skills/mcp-server-management/scripts/setup-mcp-server.sh "$tmp_script"
sed -i '\''s|CONSOLE_URL="http://127.0.0.1:8001"|CONSOLE_URL="${AGENTTEAMS_HIGRESS_CONSOLE_URL:-http://agentteams-controller:8001}"|'\'' "$tmp_script"

http_code=$(curl -sS -o /dev/null -w "%{http_code}" -c "$cookie_file" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"${AGENTTEAMS_ADMIN_USER}\",\"password\":\"${AGENTTEAMS_ADMIN_PASSWORD}\"}" \
  http://agentteams-controller:8001/session/login)
test "$http_code" = 200 -o "$http_code" = 201

export HIGRESS_COOKIE_FILE="$cookie_file"
bash "$tmp_script" goai-order unused \
  --yaml-file "/host-share/Desktop/彭祐天的Github/Wiki_of_Tian/projects/GOAI/workspace/agentteams/mcp-goai-order.yaml"
'
```

命令中不得放入 API Key、Token 或密码。不要将 `unused` 替换为真实凭证。

## 4. 用 mcporter 验证

注册脚本提示成功后，等待 Higress 鉴权插件生效，然后依次执行：

```bash
docker exec -w /root/manager-workspace agentteams-manager \
  mcporter list

docker exec -w /root/manager-workspace agentteams-manager \
  mcporter list mcp-goai-order --schema

docker exec -w /root/manager-workspace agentteams-manager \
  mcporter call mcp-goai-order.resolve_order_reference \
  --args '{"customer_id":"C001","clues":{}}'

docker exec -w /root/manager-workspace agentteams-manager \
  mcporter call mcp-goai-order.resolve_order_reference \
  --args '{"customer_id":"C001","clues":{"hotel_name":"上海虹桥海湾花园酒店","check_in_date":"2026-08-15"}}'
```

验收标准：

1. `mcporter list` 包含 `mcp-goai-order`；
2. Schema 包含且仅包含 8 个 Tool：`resolve_order_reference`、`get_authorized_order`、`evaluate_rebooking`、`record_customer_confirmation`、`validate_execution_authorization`、`execute_rebooking`、`get_order_state`、`verify_rebooking`；
3. 空 `clues` 返回 `MULTIPLE`，不暴露候选订单详情；
4. 酒店名和入住日期完整时返回 `UNIQUE`、不透明 `order_ref` 和 `ownership_verified=true`。

## 当前实现边界

- 3 个业务 Skill 位于 `workspace/skills/`，Worker manifest 位于本目录。
- 已完成 Manager → `order-matcher` 单 Worker Smoke；完整 3 Worker Golden Case 的运行证据单独保存在 `workspace/runs/`。
- Mock API 使用进程内持久状态；重复演示前必须调用 `/reset`。
- 不把本机密钥、Higress Cookie 或 AgentTeams 凭证写入项目文件。
