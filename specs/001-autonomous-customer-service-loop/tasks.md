# 酒店供应异常自主改订最小闭环：Implementation Tasks

> **For agentic workers:** 按任务依赖逐项实施；每项完成后提交指定产物、验证结果和证据路径给 Planning Agent 验收。不得跳过失败测试直接修改验收口径。

**Goal:** 把当前独立 Worker Task 基线迁移为“一 Case 一 Project Room”的自主改订闭环，并补齐角色级 MCP 权限、独立核验、P2 内部决定和 P3 Case 恢复。

**Architecture:** Frontline 与 Resolution 在 AgentTeams Case Project Room 直接协作；Manager 只维护 Case、SLA、任务和阶段闸门；Verification 接收冻结 Package 后只读回查。一个 Higress Gateway 注册三个角色化 MCP Surface，共用本地 Python Mock 后端。

**Tech Stack:** AgentTeams 1.2.2、CoPaw、Kimi K2.6、Matrix/Element、Higress MCP、Python 3.13、JSON、`unittest`、Docker Desktop。

## Global Constraints

- 事实源：[`spec.md`](./spec.md) 与 [`plan.md`](./plan.md) 均已确认；契约见 [`contracts/mcp-tools.md`](./contracts/mcp-tools.md)。
- 只使用合成数据；禁止使用真实客户、订单、邮件、内部代码或未公开规则。
- 保留现有独立 Worker 基线，迁移验收通过前不得删除旧配置或旧证据。
- Manager 不挂载订单业务 MCP；Verification 只能发现只读 Tool。
- P2 的 800 元样例只验证决定记录和授权判断，不执行高风险改订。
- API Key、Token、Cookie 和 Bearer 凭据不得进入仓库、Trace、截图或演示材料。
- 不报名、不提交作品、不加入外部群聊、不向外发送消息。
- 本仓库存在未提交内容；每项任务只修改列出的文件，不执行破坏性 Git 操作，不提交无关改动。

## Task Format

- `[P]`：与同阶段其他标记任务不存在文件写入冲突，可并行。
- `[US1]`、`[US2]`、`[US3]`：对应 Spec 的三个 User Story。
- 每项任务必须先写失败测试或失败验收，再做最小实现，最后运行列出的验证命令。
- “完成”同时要求：产物存在、命令通过、真实性标签正确、证据已保存。

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

## Phase 5：横切治理与最终验收

### - [ ] T010 完善 Audit Trace、通知闸门与 Case Card 失败语义

**Depends on:** T006、T008、T009  
**Owner:** 执行 Agent  
**Files:**

- Create: `workspace/mock-services/case_card.py`
- Modify: `workspace/mock-services/run_golden_path.py`
- Modify: `workspace/mock-services/tests/test_golden_path.py`
- Modify: `workspace/mock-services/tests/test_http_api.py`
- Create: `workspace/mock-services/tests/test_case_card.py`

**Required behavior:**

- Trace 至少覆盖订单定位、风险判断、确认/决定、执行、核验、通知、Case 状态七类事件。
- 核验失败时不得发送成功通知或进入 `RESOLVED`。
- 订单已核验成功但通知失败时保持 `NOTIFYING_CUSTOMER`，不得重复写订单。
- Case Card 写入失败不回滚已核验订单，但 Demo 验收结果必须为失败并留下 `CASE_CARD_WRITE_FAILED`。
- Trace 中不得包含凭据、隐藏推理或其他客户订单详情。

**Verify:**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s workspace/mock-services/tests -v
```

**Expected:** Golden、假成功、通知失败、Case Card 失败和七类事件完整性测试全部通过。

---

### - [ ] T011 汇总 Spec 验收矩阵与最终 Demo 证据

**Depends on:** T010  
**Owner:** 执行 Agent 提交证据；Planning Agent 验收  
**Files:**

- Create: `06-评估验证/GOAI-MVP验收矩阵.md`
- Create: `workspace/runs/2026-08-14-final-acceptance/README.md`
- Create: `workspace/runs/2026-08-14-final-acceptance/test-output.txt`
- Create: `workspace/runs/2026-08-14-final-acceptance/evidence-index.json`
- Modify: `specs/001-autonomous-customer-service-loop/quickstart.md`
- Modify: `README.md`

**Steps:**

1. 将 P1、P2、P3 的每个 Acceptance Scenario、FR-001～FR-018、SC-001～SC-010 映射到测试和证据路径。
2. 重跑全部单元测试和三个 Runbook；记录真实测试数量，不沿用 T001 的 26 个基线数字。
3. 检查三个 Worker 的 Tool 可发现性、Project Room 成员、Verification 隔离、订单前后状态和审计事件。
4. 对 runs、截图与文档进行凭据扫描；发现命中时先停止公开取证并 `请升级`。
5. 只在证据齐全后把 Quickstart/README 的对应能力从“方案设计”改为“已实现”或“模拟执行”。

**Verify:**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s workspace/mock-services/tests -v 2>&1 | tee \
  workspace/runs/2026-08-14-final-acceptance/test-output.txt
rg -n '(sk-[A-Za-z0-9]{20,}|Bearer[[:space:]]+[A-Za-z0-9._-]{20,}|api[_-]?key[[:space:]]*[:=][[:space:]]*[^[:space:]]{12,})' \
  workspace/runs 06-评估验证 07-参赛材料
```

**Expected:** 测试 `OK`；安全扫描无真实凭据命中；验收矩阵无空白需求；任何未完成项继续标为“方案设计”，不得用文档替代证据。

---

## Dependencies

```text
T001
├── T002 ── T004 ── T005 ── T006 ──┐
│        └──────────── T007 ── T008 ─┤
└── T003 ───────────── T009 ─────────┤
                                     └── T010 ── T011
```

- T002 与 T003 可并行。
- T007 与 P1 的 Room 运行不存在代码写入冲突，但不应抢占 P1 的验收优先级。
- T008 和 T009 只有在 T005 已证明 Room 映射成立后才能开始。
- T010、T011 是统一验收门，不能在任一 User Story 缺证据时提前完成。

## Requirements Coverage

| Requirement | Tasks |
|---|---|
| FR-001、FR-002、FR-003、FR-004；SC-002、SC-003 | T002、T004、T006 |
| FR-005、FR-006、FR-007、FR-009、FR-010、FR-011、FR-012；SC-001、SC-004、SC-005、SC-006 | T003、T006、T010 |
| FR-006、FR-008、FR-009；SC-007 | T007、T008 |
| FR-013、FR-014；SC-008 | T003、T009 |
| FR-015、FR-016；SC-009、SC-010 | T010、T011 |
| FR-017、FR-018 | T002、T004、T005、T011 |

## Execution Order

1. 先完成 T001～T006，证明 P1 Project Room Golden Journey。
2. 再完成 T007～T009；T007 与 T009 可以并行，但分别独立验收 P2、P3。
3. 最后完成 T010～T011，形成可供 Planning Agent 验收的完整证据包。

执行 Agent 每完成一项，必须在 [`04-方案设计/04-安全与治理/多Agent协作表.md`](../../04-方案设计/04-安全与治理/多Agent协作表.md) 规定的格式下提交“请验收”，不得自行把里程碑改为已完成。
