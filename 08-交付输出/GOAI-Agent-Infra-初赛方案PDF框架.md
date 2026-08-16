# GOAI Agent Infra 初赛方案 PDF 框架

定位：初赛方案提交，面向评委；建议 9 页，不按复赛标准堆叠代码、Trace 或部署细节。

## 1. 封面｜受约束的供应链异常自主处置

- 项目名：GOAI｜旅行供应链异常多 Agent 自主闭环
- 一句话：让供应链异常在授权、确认、核验与审计边界内完成处置。
- 副标题：以酒店订单履约异常为首个验证场景。

## 2. 场景与价值｜供应链异常为什么难以自动化

- 先抽象问题：分销商、平台、供应商和服务方都会遇到“履约状态异常，但处置需要跨角色协同”的情况。
- 共性约束：信息不完整、数据权限受限、方案需确认、高风险动作需审批、执行后仍需核验。
- 再落到酒店：客户反馈酒店查不到预订；系统必须先安全定位订单，再处理供应异常。
- 价值：减少人工转派与重复查询；把每次处置沉淀为可复核、可复用的闭环能力。

## 3. 最小闭环｜一次酒店供应异常如何被解决

用一条 Case Journey 展示：

1. 客户报障；
2. 补充最小必要信息；
3. 在客户授权范围内定位订单；
4. 调查异常并生成改订方案；
5. 获得客户确认后受控执行；
6. 独立回读核验，再通知客户并关闭 Case。

页脚口径：该场景使用合成订单与本地 Mock 服务验证；不接入真实客户或订单数据。

## 4. 设计原则｜为什么需要多 Agent，而非万能客服 Agent

- 客户沟通、订单处置、执行核验不能由同一个角色既操作又自证。
- Case 的上下文可以共享，但权限和可见信息必须隔离。
- 执行必须受确认、审批、幂等和状态闸门约束。
- 结果以业务系统独立回读为准，不以执行接口的“成功”返回为准。

## 5. 方案设计｜Room 协作、身份边界与受控执行

- 主图：`GOAI 多 Agent 协作与 MCP Tool 架构 · V7`。
- 讲图顺序：
  1. Customer Service、Case Project、Operations Review、Independent Verification 四类 Room；
  2. Frontline、Resolution、Manager、Verification 的职责及不可做事项；
  3. Manager 管理 Case State、Task、SLA 和阶段闸门，不读写业务订单；
  4. Verification 不加入处置讨论，只接收冻结输入并输出 PASS / FAIL。

## 6. Agent Identity｜身份如何决定协作边界与权限

| Agent | 在闭环中的职责 | 不可做事项 |
| --- | --- | --- |
| Frontline | 客户沟通、安全定位订单、记录确认 | 调查异常、改订单 |
| Resolution | 调查异常、生成方案、受控执行 | 识别客户身份、自证成功 |
| Manager | Case、任务、SLA、阶段闸门 | 查询或修改订单 |
| Verification | 独立回读与核验 | 加入处置讨论、修改订单 |

结论：身份不是 Prompt 中的角色描述，而是 Room 成员关系、上下文范围与 Tool 可发现范围的共同约束。

## 7. Skill 与工具集成｜从身份到角色化 MCP Surface

说明路径：**Agent Identity → 角色权限 → Skill → 可调用 MCP Tool → 业务动作与审计记录**。

| Skill | 调用者 | 关键 MCP Tool | 产出 / 失败处理 |
| --- | --- | --- | --- |
| `identify-hotel-order` | Frontline | `resolve_order_reference`、`record_customer_confirmation` | 订单引用或补充信息请求；多候选时不返回订单详情 |
| `investigate-hotel-supply-exception` | Resolution | `get_authorized_order`、`evaluate_rebooking`、`validate_execution_authorization`、`execute_rebooking` | 方案、风险结论、受控执行记录；未确认或未授权时拒绝执行 |
| `verify-hotel-rebooking` | Verification | `get_order_state`、`verify_rebooking` | PASS / FAIL 与核验依据；不采信执行 Agent 自报结果 |

## 8. 可信闭环｜确认、审批、核验与审计

- 订单定位：信息不足时追问，不猜测，不泄露候选订单。
- 执行授权：客户未确认不执行；高风险方案进入运营审批。
- 幂等保护：重复确认或执行请求最多产生一次订单变更。
- 独立核验：冻结 Verification Package；以实际订单状态核对方案、日期、状态和确认号。
- 审计：记录定位、方案、风险、确认、执行、核验和 Case 状态变化。

## 9. 可行性、开放复用与后续计划

### 当前基础

- 已实现：3 个核心 Skill、角色化 MCP Surface、合成订单 Mock API、订单安全定位和核验相关测试。
- 模拟执行：改订等业务动作只作用于本地合成数据。
- 方案设计 / 待完成：完整 Project Room Golden Journey、高风险运营审批链路、24 小时恢复等后续任务，按实际证据更新表述。

### 可复用边界

- 可复用的是“受约束处置闭环”：最小授权定位、受控执行、独立核验、审计关闭。
- 可迁移到退款换货、账户变更、理赔、运维修复等场景；需要替换行业数据、业务规则和工具契约。

### 初赛后计划

- 以同一套身份、Skill 和 MCP 契约扩展更多供应链异常类型；
- 补齐可运行 Demo、Trace、评测集和开源交付材料，为复赛准备。
