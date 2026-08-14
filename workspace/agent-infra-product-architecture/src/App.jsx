import { useState } from "react";
import { SolutionArchitecture } from "./SolutionArchitecture.jsx";

const layers = [
  {
    index: "01",
    eyebrow: "EXPERIENCE",
    title: "交互层",
    subtitle: "人如何进入协作空间",
    tone: "experience",
    components: [
      {
        name: "Element Web",
        kind: "Web Client",
        description: "聊天、历史查看与人工介入",
        connection: "通过 Matrix Client API 读写 Room Event",
        status: "本地运行",
      },
    ],
  },
  {
    index: "02",
    eyebrow: "COMMUNICATION",
    title: "通信层",
    subtitle: "人和 Agent 如何交换事件",
    tone: "communication",
    components: [
      {
        name: "Matrix Protocol",
        kind: "Open Protocol",
        description: "定义用户、Room、Event 与实时同步",
        connection: "连接 Element、Manager 与所有 Worker",
        status: "开放协议",
      },
      {
        name: "Tuwunel",
        kind: "Matrix Homeserver",
        description: "持久化消息、身份与房间状态",
        connection: "向 Agent Runtime 推送新消息事件",
        status: "本地运行",
      },
    ],
  },
  {
    index: "03",
    eyebrow: "AGENT RUNTIME",
    title: "Agent 执行层",
    subtitle: "单个 Agent 如何思考和行动",
    tone: "runtime",
    components: [
      {
        name: "QwenPaw / CoPaw",
        kind: "Manager Runtime",
        description: "Session、Memory、Agent Loop 与 Skills",
        connection: "消费 Matrix Event，经网关调用模型与工具",
        status: "本地运行",
      },
      {
        name: "Worker Runtime",
        kind: "Execution Agent",
        description: "承载专项角色、任务上下文与工具环境",
        connection: "由 Controller 创建，在 Matrix Room 协作",
        status: "按需创建",
      },
    ],
  },
  {
    index: "04",
    eyebrow: "CONTROL & GOVERNANCE",
    title: "编排与治理层",
    subtitle: "多 Agent 如何被管理和约束",
    tone: "governance",
    components: [
      {
        name: "AgentTeams Controller",
        kind: "Control Plane",
        description: "管理 Manager、Worker、Team 生命周期",
        connection: "协调运行时、通信、存储与状态回收",
        status: "本地运行",
      },
      {
        name: "Higress",
        kind: "AI Gateway",
        description: "模型路由、鉴权、限流与凭据隔离",
        connection: "代理 Agent 到 Kimi / 外部 API 的调用",
        status: "本地运行",
      },
      {
        name: "Skills Registry",
        kind: "Nacos / Registry",
        description: "Skill 的注册、版本、发现与分发",
        connection: "向 Manager 和 Worker 提供可复用能力",
        status: "后续可选",
        optional: true,
      },
    ],
  },
  {
    index: "05",
    eyebrow: "DATA & INFRA",
    title: "数据与运行层",
    subtitle: "状态、文件和进程在哪里落地",
    tone: "foundation",
    components: [
      {
        name: "MinIO",
        kind: "Object Storage",
        description: "共享文件、附件与 Agent 产物",
        connection: "为 Manager / Worker 提供统一文件空间",
        status: "本地运行",
      },
      {
        name: "Memory & State",
        kind: "SQLite / Files",
        description: "Session、历史、记忆与任务状态",
        connection: "由 Runtime 持久化并按需召回",
        status: "本地保存",
      },
      {
        name: "Docker",
        kind: "Container Runtime",
        description: "隔离组件依赖、资源与生命周期",
        connection: "承载 Controller、Manager 与 Workers",
        status: "本地运行",
      },
      {
        name: "Log & Audit",
        kind: "Trace Evidence",
        description: "记录模型、工具、审批与执行轨迹",
        connection: "为排障、评估和 Human Review 提供证据",
        status: "本地记录",
      },
    ],
  },
];

const actors = [
  { id: "user", short: "U", name: "用户", role: "Human", scope: "local" },
  { id: "element", short: "E", name: "Element", role: "Web Client", scope: "local" },
  { id: "matrix", short: "M", name: "Matrix", role: "Tuwunel", scope: "local" },
  { id: "manager", short: "A", name: "Manager", role: "QwenPaw", scope: "local" },
  { id: "higress", short: "H", name: "Higress", role: "AI Gateway", scope: "local" },
  { id: "kimi", short: "K", name: "Kimi", role: "Cloud LLM", scope: "cloud" },
  { id: "worker", short: "W", name: "Tool / Worker", role: "Execution", scope: "execution" },
];

const actorIndex = Object.fromEntries(actors.map((actor, index) => [actor.id, index]));

const events = [
  { step: "01", from: "user", to: "element", label: "输入任务", tone: "local" },
  { step: "02", from: "element", to: "matrix", label: "写入 Room Event", tone: "local" },
  { step: "03", from: "matrix", to: "manager", label: "实时同步新消息", tone: "local" },
  { step: "04", from: "manager", to: "manager", label: "恢复 Session · 组装记忆与 Skills", tone: "local" },
  { step: "05", from: "manager", to: "higress", label: "提交模型请求", tone: "local" },
  { step: "06", from: "higress", to: "kimi", label: "发送必要上下文", tone: "cloud" },
  { step: "07", from: "kimi", to: "manager", label: "返回推理 / Tool Call", tone: "cloud" },
  { step: "08", from: "manager", to: "worker", label: "可选：执行 Skill、Tool 或子任务", tone: "execution" },
  { step: "09", from: "manager", to: "user", label: "高风险动作 → Human Review", tone: "review" },
  { step: "10", from: "manager", to: "matrix", label: "回写最终回答与执行状态", tone: "local" },
  { step: "11", from: "matrix", to: "element", label: "同步并展示结果", tone: "local" },
];

function LayerCard({ layer }) {
  return (
    <article className={`tech-layer ${layer.tone}`}>
      <div className="layer-identity">
        <span className="layer-index">{layer.index}</span>
        <div>
          <p>{layer.eyebrow}</p>
          <h2>{layer.title}</h2>
          <small>{layer.subtitle}</small>
        </div>
      </div>
      <div className={`component-grid count-${layer.components.length}`}>
        {layer.components.map((component) => (
          <section className={`component-card ${component.optional ? "optional" : ""}`} key={component.name}>
            <div className="component-topline">
              <p>{component.kind}</p>
              <span>{component.status}</span>
            </div>
            <h3>{component.name}</h3>
            <div className="component-copy">
              <span>{component.description}</span>
              <small>{component.connection}</small>
            </div>
          </section>
        ))}
      </div>
    </article>
  );
}

function SequenceEvent({ event }) {
  const from = actorIndex[event.from];
  const to = actorIndex[event.to];
  const start = Math.min(from, to) + 1;
  const end = Math.max(from, to) + 2;
  const direction = from > to ? "reverse" : "forward";
  const self = from === to;

  return (
    <div className="event-row">
      <div
        className={`event-arrow ${event.tone} ${direction} ${self ? "self" : ""}`}
        style={{ gridColumn: `${start} / ${end}` }}
      >
        <span className="event-step">{event.step}</span>
        <span className="event-label">{event.label}</span>
        <i aria-hidden="true" />
      </div>
    </div>
  );
}

function SequencePanel() {
  return (
    <section className="sequence-panel" aria-label="一条消息的调用时序">
      <div className="panel-heading">
        <div>
          <p>MESSAGE EXECUTION SEQUENCE</p>
          <h2>一条消息如何完成闭环</h2>
        </div>
        <span>从本地事件到云端推理，再回到可审计协作</span>
      </div>

      <div className="scope-strip" aria-hidden="true">
        <span className="local-scope">LOCAL · 本机执行与持久化</span>
        <span className="cloud-scope">CLOUD</span>
        <span className="extension-scope">EXT.</span>
      </div>

      <div className="actor-grid">
        {actors.map((actor) => (
          <div className={`actor ${actor.scope}`} key={actor.id}>
            <b>{actor.short}</b>
            <strong>{actor.name}</strong>
            <small>{actor.role}</small>
          </div>
        ))}
      </div>

      <div className="sequence-stage">
        <div className="lifelines" aria-hidden="true">
          {actors.map((actor) => <span className={actor.scope} key={actor.id} />)}
        </div>
        <div className="event-list">
          {events.map((event) => <SequenceEvent event={event} key={event.step} />)}
        </div>
      </div>

      <div className="sequence-notes">
        <div><b>本地保存</b><span>消息、Session、Memory、文件与审计记录</span></div>
        <div><b>按次出云</b><span>只有本轮推理所需上下文发送给 Kimi</span></div>
      </div>
    </section>
  );
}

function TechnicalArchitecture() {
  return (
    <main className="page-shell">
      <section className="technical-board" aria-label="AgentTeams 分层技术架构图">
        <header className="board-header">
          <div>
            <p className="kicker">GOAI · AGENTTEAMS LOCAL DEPLOYMENT</p>
            <h1>AgentTeams 分层技术架构</h1>
          </div>
          <div className="header-meta">
            <div className="deployment-chip"><i />CURRENT DEPLOYMENT · v1.2.2</div>
            <div className="legend">
              <span><i className="legend-local" />本地链路</span>
              <span><i className="legend-cloud" />云端推理</span>
              <span><i className="legend-execution" />工具执行</span>
              <span><i className="legend-review" />人工审批</span>
            </div>
          </div>
        </header>

        <div className="technical-layout">
          <section className="layer-panel" aria-label="五层技术架构">
            <div className="panel-heading compact">
              <div>
                <p>TECHNICAL LAYERS</p>
                <h2>从交互到运行底座</h2>
              </div>
              <span>每层回答：是什么 · 解决什么 · 如何连接</span>
            </div>
            <div className="layer-stack">
              {layers.map((layer) => <LayerCard layer={layer} key={layer.index} />)}
            </div>
          </section>

          <SequencePanel />
        </div>

        <footer className="board-footer">
          <div>
            <b>LOCAL-FIRST AGENT RUNTIME</b>
            <span>Agent 的运行、消息、状态和工具环境在本机；模型推理通过 Higress 调用 Moonshot 云端的 kimi-k2.6。</span>
          </div>
          <span className="footer-mark">ARCHITECTURE VIEW · 2026.08</span>
        </footer>
      </section>
    </main>
  );
}

export function App() {
  const [activeView, setActiveView] = useState("solution");

  return (
    <>
      <nav className="architecture-switcher" aria-label="架构视图切换">
        <button
          type="button"
          aria-pressed={activeView === "solution"}
          onClick={() => setActiveView("solution")}
        >
          参赛方案产品架构
        </button>
        <button
          type="button"
          aria-pressed={activeView === "technical"}
          onClick={() => setActiveView("technical")}
        >
          当前本地部署架构
        </button>
      </nav>
      {activeView === "solution" ? <SolutionArchitecture /> : <TechnicalArchitecture />}
    </>
  );
}
