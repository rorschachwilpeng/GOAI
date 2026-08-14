# GOAI 参赛方案产品架构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留现有 AgentTeams 当前部署架构的前提下，新增一张 16:9 的「GOAI 参赛方案产品架构」，清楚区分已实现、MVP 计划和后续可选能力。

**Architecture:** 在同一 React 单页中保留「当前部署架构」，新增独立的产品架构视图，并用顶部双按钮切换。产品视图使用水平能力分层与右侧数据底座，Matrix Room 表达为协作空间，不再与 Agent 角色并列。

**Tech Stack:** React 19.2.0, Vite 6.4.2, CSS, Node test runner

## Global Constraints

- 标题使用「GOAI 参赛方案产品架构」，不使用「目标架构」。
- 状态只使用「当前已实现」「MVP 计划」「后续可选」。
- AgentTeams 角色仅包含 Platform Manager、Team Leader 和 Worker Agents；Matrix Room 是协作空间。
- Nacos、RocketMQ、PolarDB、UnifiedModel 与完整可观测标为「后续可选」，不得暗示已安装。
- 不覆盖或删除现有「AgentTeams 当前本地部署架构」。
- 1440×900 与 1280×720 无滚动、无溢出，10 秒内可识别分层和状态。

---

### Task 1: 拆分现有技术架构并增加视图切换

**Files:**
- Create: `src/TechnicalArchitecture.jsx`
- Modify: `src/App.jsx`

**Interfaces:**
- Produces: `TechnicalArchitecture(): JSX.Element`
- Produces: `App(): JSX.Element` 通过内部 `activeView` 在 `solution` 与 `technical` 之间切换。

- [ ] **Step 1: 保留现有技术架构**

将现有 `App.jsx` 的分层数据、时序数据与渲染组件移入 `TechnicalArchitecture.jsx`，根组件命名为 `TechnicalArchitecture`，不修改其业务文案。

- [ ] **Step 2: 增加双视图容器**

`App.jsx` 只负责视图选择：默认显示 `solution`，顶部提供「参赛方案产品架构」与「当前本地部署架构」两个按钮，并给激活按钮设置 `aria-pressed="true"`。

- [ ] **Step 3: 运行构建验证拆分无回归**

Run: `npm run build`

Expected: exit code 0，且生成 `dist/client/index.html` 与 `dist/server/index.js`。

### Task 2: 实现 GOAI 参赛方案产品架构

**Files:**
- Create: `src/SolutionArchitecture.jsx`
- Modify: `src/styles.css`

**Interfaces:**
- Produces: `SolutionArchitecture(): JSX.Element`
- Consumes: `App.jsx` 中的 `solution` 视图分支。

- [ ] **Step 1: 建立产品架构数据模型**

定义三种状态 `implemented`、`mvp`、`optional`，并建立四个主体区域：

1. Agent 能力层：Skills、Prompts & AgentSpec、MCP Tools、Human Review。
2. AgentTeams 应用与编排层：Platform Manager、Team Leader、Worker Agents，以及独立的 Collaboration Workspace / Matrix Rooms。
3. 平台服务与集成层：Matrix + Tuwunel、Higress、Nacos、RocketMQ、Observability。
4. Runtime & Infra：Agent Runtime、Docker、Model Services、Security & Identity。

右侧数据底座包含 State & Audit、MinIO / OSS，并将 RAG Pipeline、PolarDB、UnifiedModel 标为后续可选。

- [ ] **Step 2: 按产品能力分层渲染**

使用水平分层 + 右侧纵向数据底座，不画密集箭头。Matrix Rooms 作为协作空间卡片呈现，并在文案中说明它基于 Matrix Protocol + Tuwunel，而不是第四类 Agent。

- [ ] **Step 3: 实现状态视觉语义**

- `implemented`：绿色实心状态标签。
- `mvp`：蓝色实心状态标签。
- `optional`：橙色标签 + 虚线卡片边框。

- [ ] **Step 4: 实现 16:9 响应式布局**

桌面窗口中保持单屏；`max-width: 900px` 时允许转为单列文档布局。新样式使用 `.solution-*` 命名空间，避免修改现有 `.technical-*` 行为。

- [ ] **Step 5: 运行构建与 Sites 测试**

Run: `npm run build && npm run test:sites`

Expected: 两条命令 exit code 0，Sites tests 报告 4 tests passed。

- [ ] **Step 6: 运行视觉验收**

启动 Vite 开发服务，在 1440×900 和 1280×720 检查：

- 默认打开产品架构视图。
- 标题、四层主体、右侧数据底座和三种状态全部可见。
- 页面 `scrollHeight <= innerHeight` 且 `scrollWidth <= innerWidth`。
- 切换到技术架构后，现有内容正常显示。

## Self-Review

- Spec coverage: 覆盖双视图保留、产品分层、Matrix Rooms 归属、状态语义和视觉验收。
- Placeholder scan: 无 TBD、TODO 或「类似 Task N」。
- Type consistency: `TechnicalArchitecture`、`SolutionArchitecture` 与 `App` 命名和消费关系一致。

