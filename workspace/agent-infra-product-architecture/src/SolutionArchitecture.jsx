const statusMeta = {
  implemented: { label: "当前已实现", short: "CURRENT" },
  mvp: { label: "MVP 计划", short: "MVP" },
  optional: { label: "后续可选", short: "OPTIONAL" },
};

const capabilityCards = [
  { name: "Skills", kind: "Business Capability", copy: "业务 SOP、执行步骤与可复用脚本", status: "mvp" },
  { name: "Prompts & AgentSpec", kind: "Role Contract", copy: "角色、目标、输入输出与能力边界", status: "mvp" },
  { name: "MCP / Tool Contracts", kind: "Tool Integration", copy: "订单、政策、处置与验证工具接口", status: "mvp" },
  { name: "Human Review", kind: "Risk Control", copy: "高风险动作的审批、介入、回滚与确认", status: "mvp" },
];

const orchestrationCards = [
  { name: "Platform Manager", kind: "Coordinator", copy: "接收任务、组建团队并追踪闭环", status: "implemented" },
  { name: "Team Leader", kind: "Task Orchestrator", copy: "拆解任务、派发子任务与汇总决策", status: "mvp" },
  { name: "Worker Agents", kind: "Specialists", copy: "调查、政策、执行与验证等专项角色", status: "mvp" },
];

const serviceCards = [
  { name: "Matrix + Tuwunel", kind: "Collaboration Bus", copy: "Room、Event、实时同步与人机协作消息", status: "implemented" },
  { name: "Higress", kind: "AI Gateway", copy: "模型与工具统一入口、鉴权与凭据隔离", status: "implemented" },
  { name: "Nacos", kind: "AI Asset Registry", copy: "Skill、Prompt、Agent 与 MCP 的注册发现", status: "optional" },
  { name: "RocketMQ", kind: "Reliable Events", copy: "后台异步任务、重试与可靠事件投递", status: "optional" },
  { name: "Execution Evidence", kind: "Log & Trace", copy: "任务轨迹、工具调用、审批与验证证据", status: "mvp" },
];

const runtimeCards = [
  { name: "Agent Runtime", detail: "QwenPaw / OpenClaw / Hermes", status: "implemented" },
  { name: "Container Runtime", detail: "Docker · 按需创建 Worker", status: "implemented" },
  { name: "Model Services", detail: "Kimi · OpenAI-compatible", status: "implemented" },
  { name: "Security & Identity", detail: "Consumer Token · Credential Isolation", status: "mvp" },
];

const foundationCards = [
  { name: "State & Audit", kind: "Operational Data", copy: "Case、任务状态、决策、审批与审计", status: "mvp" },
  { name: "MinIO / OSS", kind: "Object Storage", copy: "原始文件、附件、中间产物与共享证据", status: "implemented" },
  { name: "RAG Pipeline", kind: "Knowledge Service", copy: "文档解析、切块、检索与证据对齐", status: "optional" },
  { name: "PolarDB for PostgreSQL", kind: "Primary Database", copy: "结构化数据、Vector、长记忆与日志", status: "optional" },
  { name: "UnifiedModel", kind: "Semantic Layer", copy: "统一实体、关系、拓扑与业务语义", status: "optional" },
];

function StatusBadge({ status, compact = false }) {
  const meta = statusMeta[status];
  return <span className={`solution-status ${status}`}>{compact ? meta.short : meta.label}</span>;
}

function CapabilityCard({ card }) {
  return (
    <article className={`solution-card status-${card.status}`}>
      <div className="solution-card-meta">
        <span>{card.kind}</span>
        <StatusBadge status={card.status} compact />
      </div>
      <h3>{card.name}</h3>
      <p>{card.copy}</p>
    </article>
  );
}

function LayerLabel({ index, eyebrow, title, subtitle }) {
  return (
    <div className="solution-layer-label">
      <span>{index}</span>
      <div>
        <p>{eyebrow}</p>
        <h2>{title}</h2>
        <small>{subtitle}</small>
      </div>
    </div>
  );
}

export function SolutionArchitecture() {
  return (
    <main className="page-shell">
      <section className="solution-board" aria-label="GOAI 参赛方案产品架构">
        <header className="solution-header">
          <div>
            <p className="solution-kicker">GOAI · AGENT INFRA</p>
            <h1>GOAI 参赛方案产品架构</h1>
            <span>以 AgentTeams 为协同基点，承载复杂业务工单的多 Agent 自主闭环</span>
          </div>
          <div className="solution-header-side">
            <p>PRODUCT CAPABILITY STACK</p>
            <div className="solution-legend">
              {Object.entries(statusMeta).map(([key, meta]) => (
                <StatusBadge status={key} key={key}>{meta.label}</StatusBadge>
              ))}
            </div>
          </div>
        </header>

        <div className="solution-layout">
          <section className="solution-main-stack">
            <article className="solution-layer capability-layer">
              <LayerLabel index="01" eyebrow="AGENT CAPABILITIES" title="Agent 能力层" subtitle="Agent 会什么，如何安全做事" />
              <div className="solution-card-grid four">
                {capabilityCards.map((card) => <CapabilityCard card={card} key={card.name} />)}
              </div>
            </article>

            <article className="solution-layer orchestration-layer">
              <LayerLabel index="02" eyebrow="MULTI-AGENT ORCHESTRATION" title="应用与编排层" subtitle="数字团队如何组织与协作" />
              <div className="solution-orchestration-body">
                <div className="agentteams-ribbon">
                  <div><span>COLLABORATIVE MULTI-AGENT OS</span><strong>AgentTeams</strong></div>
                  <StatusBadge status="implemented" />
                </div>
                <div className="solution-card-grid three role-grid">
                  {orchestrationCards.map((card) => <CapabilityCard card={card} key={card.name} />)}
                </div>
                <div className="workspace-strip">
                  <div><span>COLLABORATION WORKSPACE</span><strong>Matrix Rooms</strong></div>
                  <p>协作空间：任务、进度、中间结论与人工介入共享同一条时间线</p>
                  <span className="workspace-connection">底层由 Matrix Protocol + Tuwunel 实现</span>
                </div>
              </div>
            </article>

            <article className="solution-layer services-layer">
              <LayerLabel index="03" eyebrow="PLATFORM SERVICES" title="平台服务与集成层" subtitle="协作、连接、治理与证据" />
              <div className="solution-card-grid five">
                {serviceCards.map((card) => <CapabilityCard card={card} key={card.name} />)}
              </div>
            </article>

            <article className="solution-runtime">
              <LayerLabel index="04" eyebrow="RUNTIME & INFRA" title="运行与基础设施层" subtitle="Agent 在哪里运行、隔离和调用" />
              <div className="runtime-grid">
                {runtimeCards.map((card) => (
                  <div className={`runtime-item status-${card.status}`} key={card.name}>
                    <div><strong>{card.name}</strong><span>{card.detail}</span></div>
                    <StatusBadge status={card.status} compact />
                  </div>
                ))}
              </div>
            </article>
          </section>

          <aside className="solution-foundation">
            <div className="foundation-heading">
              <p>DATA FOUNDATION</p>
              <h2>数据与知识底座</h2>
              <span>跨层支撑 Agent 理解、记忆、协作和追溯业务</span>
            </div>
            <div className="foundation-stack">
              {foundationCards.map((card) => <CapabilityCard card={card} key={card.name} />)}
            </div>
          </aside>
        </div>

        <footer className="solution-footer">
          <span><i className="current-dot" />当前已实现：AgentTeams 本地协作与运行底座</span>
          <span><i className="mvp-dot" />MVP 计划：业务 Agent、Skill、工具契约、Human Review 与执行证据</span>
          <span><i className="optional-dot" />后续可选：按真实规模和必要性接入，不为堆叠工具</span>
        </footer>
      </section>
    </main>
  );
}
