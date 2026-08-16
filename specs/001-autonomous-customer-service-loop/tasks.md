# 酒店供应异常自主改订最小闭环：Implementation Tasks

> **For agentic workers:** 按任务依赖逐项实施；每项完成后提交指定产物、验证结果和证据路径给 Planning Agent 验收。不得跳过失败测试直接修改验收口径。

**Goal:** 在已完成的 Project Room 基线上实现一条可录制的连续旅程：同一客户会话、同一 Case 和同一 Project Room 串联两轮供应异常、双重授权、高风险 Mock 改订、两次独立核验与 24 小时超时恢复。

**Architecture:** 独立 Customer Chat Facade 只展示 Customer Conversation 投影；Frontline 与 Resolution 在同一 AgentTeams Case Project Room 直接协作；Manager 只维护 Case、SLA、任务和阶段闸门；Verification 对每次写入分别接收冻结 Package 并只读回查。三个角色化 MCP Surface 共用本地 Python Mock 后端。

**Tech Stack:** AgentTeams 1.2.2、CoPaw、Kimi K2.6、Matrix/Element、Higress MCP、Python 3.13、JSON、`unittest`、Docker Desktop。

## Global Constraints

- 事实源：[`spec.md`](./spec.md) 与 [`plan.md`](./plan.md) 当前为 Linked Journey Draft；本轮 Tasks 只有在用户确认上述文档后才可执行。契约见 [`contracts/mcp-tools.md`](./contracts/mcp-tools.md)。
- 只使用合成数据；禁止使用真实客户、订单、邮件、内部代码或未公开规则。
- 保留现有独立 Worker 基线，迁移验收通过前不得删除旧配置或旧证据。
- Manager 不挂载订单业务 MCP；Verification 只能发现只读 Tool。
- 800 元样例必须同时取得运营 `APPROVE` 与当前客户确认，随后允许执行一次高风险 Mock 改订并独立核验。
- 客户只能访问 Customer Chat Facade；Frontline Runtime Room、Project Room、Operations Review 和 Verification 内容不得投影到客户侧。
- 同一连续旅程固定复用 `conversation_id`、`case_id`、`project_id` 与 `project_room_id`，以 `incident_sequence` 区分两轮异常。
- API Key、Token、Cookie 和 Bearer 凭据不得进入仓库、Trace、截图或演示材料。
- 不报名、不提交作品、不加入外部群聊、不向外发送消息。
- 本仓库存在未提交内容；每项任务只修改列出的文件，不执行破坏性 Git 操作，不提交无关改动。

## Task Format

- `[P]`：与同阶段其他标记任务不存在文件写入冲突，可并行。
- `[US1]`、`[US2]`、`[US3]`：对应 Spec 的三个 User Story。
- 每项任务必须先写失败测试或失败验收，再做最小实现，最后运行列出的验证命令。
- “完成”同时要求：产物存在、命令通过、真实性标签正确、证据已保存。

## Revision Baseline

- T001～T009 是 2026-08-14 完成的改造前基线，已冻结在 Git 检查点 `edef185`。
- 检查点时全部 49 个测试通过；T001 中的 26 个测试只是当时的早期计数。
- T007/T008 的“高风险永不执行”和 T009 的独立恢复样例已经被 Linked Journey 需求取代，但其原始证据仍保留用于回滚和对比。
- 以下新任务从 T010 开始，不篡改已完成任务的历史状态。

---

## Phase 1：基线与公共基础

### - [x] T001 冻结当前基线与回滚参照

**Depends on:** 无  
**Owner:** 执行 Agent  
**Files:**

- Create: `workspace/runs/2026-08-14-pre-migration-baseline/README.md`
- Create: `workspace/runs/2026-08-14-pre-migration-baseline/test-output.txt`
- Read only: `workspace/agentteams/*.yaml`
- Read only: `workspace/mock-services/`

**Steps:**

1. 运行现有 26 个测试，将完整输出保存到 `test-output.txt`。
2. 在 `README.md` 记录 3 个 Worker 名称、3 个 Skill、8 个 Tool、现有编排方式和旧证据入口。
3. 记录迁移前文件哈希，不复制或记录任何凭据。

**Verify:**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s workspace/mock-services/tests -v 2>&1 | tee \
  workspace/runs/2026-08-14-pre-migration-baseline/test-output.txt
```

**Expected:** `Ran 26 tests` 且 `OK`；基线说明明确写出“独立 Worker Task，非 Project Room”。

---

### - [x] T002 [P] 建立三个角色化 MCP Surface

**Depends on:** T001  
**Owner:** 执行 Agent  
**Files:**

- Create: `workspace/agentteams/mcp-goai-frontline.yaml`
- Create: `workspace/agentteams/mcp-goai-resolution.yaml`
- Create: `workspace/agentteams/mcp-goai-verification.yaml`
- Create: `workspace/mock-services/tests/test_agentteams_contracts.py`
- Preserve: `workspace/agentteams/mcp-goai-order.yaml`

**Interfaces produced:**

- Frontline：`resolve_order_reference`、`record_customer_confirmation`
- Resolution：`get_authorized_order`、`evaluate_rebooking`、`validate_execution_authorization`、`execute_rebooking`
- Verification：`get_order_state`、`verify_rebooking`

**Steps:**

1. 先写契约测试，使用 Python 标准库读取三个 YAML，断言每个 Surface 的 Tool 集合完全等于上表，并断言 Manager 配置不存在业务 MCP。
2. 运行单文件测试，确认因为三个 YAML 尚不存在而失败。
3. 从现有 8 Tool 配置拆出三个最小 Surface；Gateway 地址与 Mock HTTP 路由保持不变。
4. 运行契约测试和现有全部测试。

**Verify:**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s workspace/mock-services/tests -p 'test_agentteams_contracts.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s workspace/mock-services/tests -v
```

**Expected:** Surface 集合精确匹配；现有 26 个测试无回归。此时只证明配置文件隔离，未证明已在 Higress 注册。

---

### - [x] T003 [P] 实现 Case 状态控制与 Verification Package 冻结

**Depends on:** T001  
**Owner:** 执行 Agent  
**Files:**

- Create: `workspace/mock-services/case_control.py`
- Create: `workspace/mock-services/verification_package.py`
- Create: `workspace/mock-services/tests/test_case_control.py`
- Create: `workspace/mock-services/tests/test_verification_package.py`

**Interfaces produced:**

```python
CaseStore(path).create_case(case_id, customer_id, project_id, project_room_id, occurred_at)
CaseStore(path).apply_event(case_id, event_type, occurred_at, **payload)
CaseStore(path).get_case(case_id)
freeze_verification_package(payload, frozen_at) -> dict
verify_package_hash(package) -> bool
```

**Required behavior:**

- `CaseStore` 原子持久化 Case JSON，并拒绝 [`data-model.md`](./data-model.md) 未允许的状态转换。
- Case 与 `project_id`、`project_room_id` 一对一；重开不改变 Room。
- Package 对规范化 JSON 计算 SHA-256；不得包含 `hidden_reasoning`、`project_room_transcript` 或 `execution_response`。
- 修改冻结 Package 的任一业务字段后，`verify_package_hash` 必须返回 `false`。

**Verify:**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s workspace/mock-services/tests \
  -p 'test_case_control.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s workspace/mock-services/tests \
  -p 'test_verification_package.py' -v
```

**Expected:** 合法转换、非法转换、Room 一致性、禁用字段、哈希篡改五类断言全部通过。

---

## Phase 2：User Story 1 — 客户自主解决酒店供应异常（P1）

### - [x] T004 [US1] 迁移 Agent Identity、Skill 与最小权限配置

**Depends on:** T002  
**Owner:** 执行 Agent  
**Files:**

- Create: `workspace/agentteams/frontline-worker.yaml`
- Create: `workspace/agentteams/resolution-worker.yaml`
- Modify: `workspace/agentteams/verification-worker.yaml`
- Modify: `workspace/skills/identify-hotel-order/SKILL.md`
- Modify: `workspace/skills/investigate-hotel-supply-exception/SKILL.md`
- Modify: `workspace/skills/verify-hotel-rebooking/SKILL.md`
- Modify: `workspace/mock-services/tests/test_agentteams_contracts.py`

**Required behavior:**

- Frontline 只连接 `mcp-goai-frontline`，负责安全定位订单、主动追问和记录客户确认。
- Resolution 只连接 `mcp-goai-resolution`，接收不透明 `order_ref`，完成调查、方案、风险与受控执行。
- Verification 只连接 `mcp-goai-verification`，输入必须为有效冻结 Package，不能加入处置讨论或执行写入。
- Skill 的交接对象改为 Case Project Room；Manager 不再逐条转发业务 Agent 消息。

**Verify:**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s workspace/mock-services/tests -p 'test_agentteams_contracts.py' -v
rg -n 'mcp-goai-(frontline|resolution|verification)' \
  workspace/agentteams/*-worker.yaml
```

**Expected:** 三个 Worker 每个只出现一个与角色同名的 MCP Server；旧 Worker 文件仍保留作回滚参照。

---

### - [x] T005 [US1] 创建“一 Case 一 Project Room”协作实例

**Depends on:** T003、T004  
**Owner:** 执行 Agent  
**Files:**

- Create: `workspace/agentteams/project-room-brief.md`
- Modify: `workspace/agentteams/README.md`
- Create: `workspace/runs/2026-08-14-project-room-migration/README.md`
- Create: `workspace/runs/2026-08-14-project-room-migration/project-meta.json`
- Create: `workspace/runs/2026-08-14-project-room-migration/room-members.json`

**Runtime action:**

在 AgentTeams Manager 环境中使用官方 `project-management` 脚本创建 `proj-goai-case-golden-001`，参与 Worker 只允许 `frontline,resolution`：

```bash
bash /opt/agentteams/agent/skills/project-management/scripts/create-project.sh \
  --id 'proj-goai-case-golden-001' \
  --title 'GOAI Golden Case 001' \
  --workers 'frontline,resolution'
```

执行前先读取是否已存在同 ID Project；若已存在且成员正确则复用，不删除或覆盖。

**Acceptance:**

- Project Room 包含 admin、Manager、Frontline、Resolution。
- Verification 不在 Project Room。
- Frontline 与 Resolution 可在 Project Room 互相 @mention。
- admin 在该 Room 仅观察，不计业务人工介入。

**Verify:** `project-meta.json` 与 `room-members.json` 中 `project_id`、`room_id`、成员列表满足上述集合；README 记录取证时间和 Matrix Room 链接，不包含访问凭据。

---

### - [x] T006 [US1] 跑通 Project Room Golden Journey 与独立核验

**Depends on:** T003、T005  
**Owner:** 执行 Agent  
**Files:**

- Create: `workspace/agentteams/runbooks/p1-golden-case.md`
- Modify: `workspace/mock-services/run_golden_path.py`
- Modify: `workspace/mock-services/tests/test_golden_path.py`
- Create: `workspace/runs/2026-08-14-p1-golden-case-v2/README.md`
- Create: `workspace/runs/2026-08-14-p1-golden-case-v2/project-room-events.jsonl`
- Create: `workspace/runs/2026-08-14-p1-golden-case-v2/verification-package.json`
- Create: `workspace/runs/2026-08-14-p1-golden-case-v2/verification-result.json`
- Create: `workspace/runs/2026-08-14-p1-golden-case-v2/final-result.json`

**Flow:**

1. Frontline 在专属 Room 接收 `C001` 的初始消息，主动追问并安全定位订单。
2. Frontline 在 Project Room 发布结构化 `ORDER_LINKED` 交接；Resolution 直接接续调查。
3. Resolution 发布 180 元方案；Frontline 在客户 Room 取得确认并记录。
4. Resolution 受控执行一次 Mock 改订。
5. Manager 冻结 Package，在 Verification 专属 Room 创建独立任务。
6. Verification 只读回查并返回 `PASSED`；Frontline 通知客户；Manager 关闭 Case。

**Verify:**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s workspace/mock-services/tests -v
jq -e '.case_state == "RESOLVED" and
       .resolution_mode == "AUTONOMOUS" and
       .verification_status == "PASSED" and
       .internal_human_interventions == 0' \
  workspace/runs/2026-08-14-p1-golden-case-v2/final-result.json
```

**Expected:** P1 八个 Acceptance Scenarios 全部有消息、Tool、状态或订单证据；`C002` 信息暴露 0 次；订单只写入 1 次。

---

## Phase 3：User Story 2 — 内部运营人员处理高风险方案（P2）

### - [x] T007 [P] [US2] 实现内部决定记录与高风险执行硬阻断

> **历史基线：** 本任务按旧 Spec 完成；“高风险硬阻断”由 T010 的“双重授权后允许 Mock 执行”取代。

**Depends on:** T002  
**Owner:** 执行 Agent  
**Files:**

- Modify: `workspace/mock-services/golden_path.py`
- Modify: `workspace/mock-services/serve_http.py`
- Modify: `workspace/agentteams/mcp-goai-resolution.yaml`
- Modify: `workspace/mock-services/tests/test_golden_path.py`
- Modify: `workspace/mock-services/tests/test_http_api.py`
- Modify after passing: `specs/001-autonomous-customer-service-loop/contracts/mcp-tools.md`

**Interface produced:**

```python
record_internal_decision(
    store,
    case_id,
    resolution_plan_id,
    risk_decision_id,
    decision,
    message_event_id,
    operator_id,
) -> dict
```

**Required behavior:**

- 只接受 `APPROVE | REJECT`，并绑定 Case、方案、风险决定、运营人员、消息事件和服务端时间。
- `REJECT` 使授权校验拒绝。
- `APPROVE` 使授权判断返回 `authorized=true`、`execution_enabled=false`。
- V0.1 对内部审批方案调用 `execute_rebooking` 必须返回 `HIGH_RISK_EXECUTION_NOT_ENABLED`，订单保持 `CONFIRMED`。

**Verify:**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s workspace/mock-services/tests -v
```

**Expected:** 新增 APPROVE、REJECT、错误上下文、重复冲突和高风险不写入测试；全部测试通过。契约文档只有在代码通过后才把该 Tool 标为“已实现，Mock”。

---

### - [x] T008 [US2] 跑通 Operations Review Room 的 APPROVE / REJECT

> **历史基线：** 本任务的决定记录仍复用；“APPROVE 后不执行”由 T010 取代。

**Depends on:** T005、T007  
**Owner:** 执行 Agent  
**Files:**

- Create: `workspace/agentteams/runbooks/p2-operations-review.md`
- Create: `workspace/runs/2026-08-14-p2-internal-approval/README.md`
- Create: `workspace/runs/2026-08-14-p2-internal-approval/approve-decision.json`
- Create: `workspace/runs/2026-08-14-p2-internal-approval/reject-decision.json`
- Create: `workspace/runs/2026-08-14-p2-internal-approval/order-state.json`
- Create: `workspace/runs/2026-08-14-p2-internal-approval/room-events.jsonl`

**Flow:** Resolution 在其专属 Room 向由 admin 模拟的 Hotel Operations 展示 800 元方案、风险原因、SLA 和待决定事项；分别录制一次 APPROVE 和一次重置后的 REJECT。

**Verify:**

```bash
jq -e '.decision == "APPROVE" and .operator_id and .message_event_id' \
  workspace/runs/2026-08-14-p2-internal-approval/approve-decision.json
jq -e '.decision == "REJECT" and .operator_id and .message_event_id' \
  workspace/runs/2026-08-14-p2-internal-approval/reject-decision.json
jq -e '.status == "CONFIRMED"' \
  workspace/runs/2026-08-14-p2-internal-approval/order-state.json
```

**Expected:** 两个决定都可审计；未决定与 REJECT 均拒绝授权；APPROVE 可被授权判断识别但不触发订单写入。

---

## Phase 4：User Story 3 — 补充信息并恢复未完成服务（P3）

### - [x] T009 [P] [US3] 实现 24 小时关闭、原 Case 重开与 Room 复用

> **历史基线：** 原独立恢复样例保留；最终 Demo 改为第二轮高风险方案确认超时，并由 T010、T013 串入同一 Case。

**Depends on:** T003、T005  
**Owner:** 执行 Agent  
**Files:**

- Modify: `workspace/mock-services/case_control.py`
- Modify: `workspace/mock-services/tests/test_case_control.py`
- Create: `workspace/agentteams/runbooks/p3-case-recovery.md`
- Create: `workspace/runs/2026-08-14-p3-case-recovery/README.md`
- Create: `workspace/runs/2026-08-14-p3-case-recovery/case-before-timeout.json`
- Create: `workspace/runs/2026-08-14-p3-case-recovery/case-closed.json`
- Create: `workspace/runs/2026-08-14-p3-case-recovery/case-reopened.json`

**Required behavior:**

- 追问成功发送时设置 `reply_deadline_at = sent_at + 24h`。
- 以 Matrix 消息到达时间判断是否在期限内，不以后台处理时间判断。
- 无有效回复进入 `CLOSED_INCOMPLETE` 并停止后台任务。
- 同一客户同一问题的迟到回复进入 `IDENTIFYING_ORDER`，复用 `case_id`、`project_id`、`project_room_id`，`reopened_count + 1`。
- 已解决后的客户异议使用同一重开规则。

**Verify:**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s workspace/mock-services/tests -p 'test_case_control.py' -v
jq -e '.case_state == "CLOSED_INCOMPLETE"' \
  workspace/runs/2026-08-14-p3-case-recovery/case-closed.json
jq -e '.case_state == "IDENTIFYING_ORDER" and .reopened_count == 1' \
  workspace/runs/2026-08-14-p3-case-recovery/case-reopened.json
```

**Expected:** 不等待真实 24 小时；测试通过注入带时区时间确定性验证截止前、截止点、截止后三种情况，重复 Case 数量为 0。

---

## Phase 5：Linked Journey 业务内核

### - [x] T010 [US1] [US2] [US3] 实现连续两轮 Case、双重授权与两次独立核验

**Depends on:** T001～T009；用户确认 Linked Journey Spec 与 Plan

**Owner:** 执行 Agent
**Files:**

- Modify: `workspace/mock-services/golden_path.py`
- Modify: `workspace/mock-services/case_control.py`
- Modify: `workspace/mock-services/verification_package.py`
- Modify: `workspace/mock-services/serve_http.py`
- Modify: `workspace/mock-services/data/*.json`
- Modify: `workspace/mock-services/tests/test_golden_path.py`
- Modify: `workspace/mock-services/tests/test_case_control.py`
- Modify: `workspace/mock-services/tests/test_http_api.py`

**Required behavior:**

1. 第一次 180 元改订完成后独立核验并进入 `RESOLVED`。
2. 新的结构化供应异常命中替代订单时，复用原 `case_id`、`project_id`、`project_room_id`，`incident_sequence=2`。
3. 第二轮只提供 800 元候补方案；风险决定同时要求 `INTERNAL_APPROVAL` 与 `CUSTOMER_CONFIRMATION`。
4. 只有运营 `APPROVE` 时仍拒绝执行；客户确认与运营批准同时有效后允许第二次 Mock 改订。
5. 确认请求 24 小时未回复进入 `CLOSED_INCOMPLETE`；迟到确认恢复原 Case，重新校验授权与订单状态。
6. 两次执行使用不同幂等键，并分别生成冻结 Package 和只读 Verification Result。

**Named tests required:**

- `test_supplier_recurrence_reopens_same_case_and_room`
- `test_high_risk_execution_requires_internal_and_customer_confirmation`
- `test_customer_confirmation_timeout_and_late_resume`
- `test_second_execution_is_idempotent`
- `test_each_execution_requires_independent_verification`

**Verify:**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s workspace/mock-services/tests -v
```

**Expected:** 原 49 个测试无回归；以上新测试全部出现并通过；未经双重授权的订单写入次数为 0。

---

## Phase 6：客户隔离与可录制界面

### - [x] T011 [US1] [US3] 建立 Customer Chat Facade 与独立消息投影

**Depends on:** T010

**Owner:** 执行 Agent
**Files:**

- Create: `workspace/customer-chat/index.html`
- Create: `workspace/customer-chat/styles.css`
- Create: `workspace/customer-chat/app.js`
- Create: `workspace/mock-services/conversation_store.py`
- Modify: `workspace/mock-services/serve_http.py`
- Create: `workspace/mock-services/tests/test_conversation_store.py`
- Modify: `workspace/mock-services/tests/test_http_api.py`
- Create: `workspace/customer-chat/README.md`

**Required behavior:**

- 客户在独立网页中与 Frontline 交互，连续旅程始终使用同一 `conversation_id` 与 `case_id`。
- 客户侧只展示 `CUSTOMER | FRONTLINE` 消息投影，不读取 Matrix Room 全文。
- Project Room 消息、隐藏推理、Tool 名称/参数、MCP 错误、内部规则明细和运营身份不得出现在客户 API 响应或 DOM。
- 页面支持聊天记录、输入、发送状态和 Frontline 回复；不建设完整登录或运营后台。

**Verify:**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s workspace/mock-services/tests -p 'test_conversation_store.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s workspace/mock-services/tests -v
```

**Expected:** 白名单字段测试、跨客户隔离测试和敏感内容不投影测试全部通过；浏览器可完成一轮真实交互。

---

### - [x] T012 [P] 规范 Project Room 展示事件与 Demo 埋点

**Depends on:** T010

**Owner:** 执行 Agent
**Files:**

- Modify: `workspace/skills/identify-hotel-order/SKILL.md`
- Modify: `workspace/skills/investigate-hotel-supply-exception/SKILL.md`
- Modify: `workspace/skills/verify-hotel-rebooking/SKILL.md`
- Create: `workspace/agentteams/runbooks/linked-journey-demo.md`
- Create: `workspace/mock-services/demo_markers.py`
- Create: `workspace/mock-services/tests/test_demo_markers.py`

**Required behavior:**

- Project Room 只发布结构化业务事件：Case/轮次、当前状态、交接对象、业务结论、下一动作、证据引用。
- 不发布长篇推理、原始 Tool Payload、凭据或客户不可见的敏感订单详情。
- 统一 Run 生成 `DEMO_START`、`SCENE_1_END`、`SCENE_2_END`、`TIMEOUT_SIMULATED`、`DEMO_END` 标记，每项包含时间、Matrix 事件 ID 和业务事件 ID。
- Operations Review 和 Independent Verification 的关键事件通过 Project Room 摘要引用，避免录屏反复切换多个 Room。

**Verify:**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s workspace/mock-services/tests -p 'test_demo_markers.py' -v
```

**Expected:** 标记顺序唯一且完整；每个标记可定位到具体消息；敏感字段扫描无命中。

---

## Phase 7：统一运行、治理与录屏证据

### - [ ] T013 重新运行同一 Case / Project Room 的完整连续旅程

**Depends on:** T011、T012

**Owner:** 执行 Agent
**Files:**

- Create: `workspace/runs/2026-08-15-linked-journey-demo/README.md`
- Create: `workspace/runs/2026-08-15-linked-journey-demo/run-manifest.json`
- Create: `workspace/runs/2026-08-15-linked-journey-demo/customer-conversation.jsonl`
- Create: `workspace/runs/2026-08-15-linked-journey-demo/project-room-events.jsonl`
- Create: `workspace/runs/2026-08-15-linked-journey-demo/operations-events.jsonl`
- Create: `workspace/runs/2026-08-15-linked-journey-demo/verification-1.json`
- Create: `workspace/runs/2026-08-15-linked-journey-demo/verification-2.json`
- Create: `workspace/runs/2026-08-15-linked-journey-demo/final-result.json`

**Runtime flow:**

1. 重置合成数据并复用已存在的 `proj-goai-case-golden-001`，不得新建第二个 Project Room。
2. 从 Customer Chat 发起第一轮问题，完成 180 元改订与 Verification #1。
3. 注入替代酒店再次取消事件，在同一 Project Room 继续第二轮。
4. 在 Operations Review 记录 800 元方案 `APPROVE`。
5. 向客户请求确认，确定性模拟 24 小时超时，再由同一客户发送迟到确认。
6. 完成第二次 Mock 改订、Verification #2、客户通知和最终关闭。

**Verify:**

```bash
jq -e '.case_id and .project_room_id and
       .incident_count == 2 and
       .execution_count == 2 and
       .verification_count == 2 and
       .final_case_state == "RESOLVED"' \
  workspace/runs/2026-08-15-linked-journey-demo/run-manifest.json
```

**Expected:** 左侧客户对话与右侧 Project Room 可按 Run Manifest 时间轴同步录制；全程只有一个 Case 和一个 Project Room。

---

### - [ ] T014 完善 Audit Trace、通知闸门与 Case Card 失败语义

**Depends on:** T013

**Owner:** 执行 Agent
**Files:**

- Create: `workspace/mock-services/case_card.py`
- Modify: `workspace/mock-services/run_golden_path.py`
- Modify: `workspace/mock-services/tests/test_golden_path.py`
- Modify: `workspace/mock-services/tests/test_http_api.py`
- Create: `workspace/mock-services/tests/test_case_card.py`

**Required behavior:**

- Trace 覆盖订单定位、异常复发、风险判断、客户确认、运营决定、两次执行、两次核验、通知和 Case 状态。
- 核验失败不得发送成功通知或进入 `RESOLVED`。
- 订单已核验成功但通知失败时保持 `NOTIFYING_CUSTOMER`，不得重复写订单。
- Case Card 写入失败不回滚已核验订单，但 Demo 验收必须失败并留下 `CASE_CARD_WRITE_FAILED`。
- Trace 不得包含凭据、隐藏推理或其他客户订单详情。

**Verify:**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s workspace/mock-services/tests -v
```

**Expected:** Golden、假成功、通知失败、Case Card 失败和审计事件完整性测试全部通过。

---

### - [ ] T015 汇总 Spec 验收矩阵与最终 Demo 证据

**Depends on:** T014

**Owner:** 执行 Agent 提交证据；Planning Agent 验收
**Files:**

- Create: `06-评估验证/GOAI-MVP验收矩阵.md`
- Create: `workspace/runs/2026-08-15-final-acceptance/README.md`
- Create: `workspace/runs/2026-08-15-final-acceptance/test-output.txt`
- Create: `workspace/runs/2026-08-15-final-acceptance/evidence-index.json`
- Modify: `specs/001-autonomous-customer-service-loop/quickstart.md`
- Modify: `README.md`

**Steps:**

1. 将 P1、P2、P3、FR-001～FR-018、SC-001～SC-010 映射到测试和证据。
2. 重跑全部测试与 Linked Journey Runbook，记录真实测试数量。
3. 检查客户隔离、Tool Surface、Project Room、Verification 隔离、两轮订单状态和审计事件。
4. 对运行证据、截图和文档进行凭据扫描。
5. 只有证据齐全的能力才改为“已实现”或“模拟执行”。

**Verify:**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s workspace/mock-services/tests -v 2>&1 | tee \
  workspace/runs/2026-08-15-final-acceptance/test-output.txt
rg -n '(sk-[A-Za-z0-9]{20,}|Bearer[[:space:]]+[A-Za-z0-9._-]{20,}|api[_-]?key[[:space:]]*[:=][[:space:]]*[^[:space:]]{12,})' \
  workspace/runs 06-评估验证 07-参赛材料
```

**Expected:** 测试 `OK`；安全扫描无真实凭据；验收矩阵无空白需求；录屏起止点可由 Manifest 精确定位。

---

## Dependencies

```text
T001 ── … ── T009 ── T010 ──┬── T011 ──┐
                              └── T012 ──┤
                                         └── T013 ── T014 ── T015
```

- T011 与 T012 在 T010 通过后可并行。
- T013 是重新运行门；T010～T012 任一缺失都不得开始录屏运行。
- T014、T015 是最终验收，不得用文档替代真实证据。

## Requirements Coverage

| Requirement | Tasks |
|---|---|
| FR-001～FR-004；SC-002、SC-003 | T002、T004、T006、T010 |
| FR-005～FR-012；SC-001、SC-004～SC-007 | T003、T006～T010、T013、T014 |
| FR-013、FR-014；SC-008 | T009～T013 |
| FR-015、FR-016；SC-009、SC-010 | T012～T015 |
| FR-017、FR-018 | T002、T004、T005、T011～T015 |

## Execution Order

1. 用户先评审 Linked Journey 的 `spec.md`、`plan.md`、`data-model.md` 与 MCP 契约。
2. 确认后由执行 Agent完成 T010；Planning Agent 验收双重授权和连续 Case 内核。
3. T011 与 T012 并行完成客户隔离和可录制事件协议。
4. T013 从头重跑唯一连续旅程；旧的三个独立 Run 保留作回归证据，但不作为最终视频素材。
5. T014、T015 完成最终治理和证据后，用户按 Manifest 录屏。

执行 Agent 每完成一项，必须按 [`04-方案设计/04-安全与治理/多Agent协作表.md`](../../04-方案设计/04-安全与治理/多Agent协作表.md) 提交“请验收”，不得自行改变需求、架构或验收口径。
