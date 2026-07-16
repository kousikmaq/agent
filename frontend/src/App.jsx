import { useEffect, useRef, useState } from "react";
import { getStatus, sendChat, executeAction, getPlan, regeneratePlan } from "./api";
import {
  Dashboard, PlanView, ScheduleGantt, MachinesView, OrdersView, DemandView, WorkforceView,
} from "./views";

const EXAMPLES = [
  "Which orders are at risk of delay, and by how many days?",
  "Generate an optimised production schedule",
  "Which machines might break down soon?",
  "Compare the three planning scenarios (max throughput, min risk and min cost)",
  "Where is the bottleneck on the line right now?",
  "Is our capacity enough to handle this week's load?",
  "Forecast demand for the next week",
  "Which orders should we prioritise today?",
  "How should we allocate the workforce this week?",
];

const AGENT_COLORS = {
  "Capacity & Scheduling": "#5B8DD6",
  "Risk & Reliability": "#CC6677",
  "Demand & Inventory": "#3FA99B",
  Orchestrator: "#8C6FC0",
};

const EMAIL_ACTIONS = new Set(["send_email", "email_chart"]);

function AgentBadge({ agent }) {
  const color = AGENT_COLORS[agent] || "#5A6675";
  return <span className="badge" style={{ background: color }}>{agent}</span>;
}

/* ---------- safe, tiny Markdown renderer (no dangerouslySetInnerHTML) ---------- */
function renderInline(text) {
  const parts = String(text).split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) =>
    p.startsWith("**") && p.endsWith("**")
      ? <strong key={i}>{p.slice(2, -2)}</strong>
      : <span key={i}>{p}</span>
  );
}

function Markdown({ text }) {
  if (!text) return null;
  const lines = String(text).split(/\r?\n/);
  const blocks = [];
  let list = null;
  const flush = () => { if (list) { blocks.push(list); list = null; } };
  for (const raw of lines) {
    const line = raw.trimEnd();
    const heading = line.match(/^\s*(#{1,4})\s+(.*)/);
    const bullet = line.match(/^\s*[-*]\s+(.*)/);
    const num = line.match(/^\s*\d+\.\s+(.*)/);
    if (heading) {
      flush();
      blocks.push({ type: "h", text: heading[2] });
    } else if (bullet) {
      if (!list || list.type !== "ul") { flush(); list = { type: "ul", items: [] }; }
      list.items.push(bullet[1]);
    } else if (num) {
      if (!list || list.type !== "ol") { flush(); list = { type: "ol", items: [] }; }
      list.items.push(num[1]);
    } else if (line.trim() === "") {
      flush();
    } else {
      flush();
      blocks.push({ type: "p", text: line });
    }
  }
  flush();
  return (
    <div className="md">
      {blocks.map((b, i) => {
        if (b.type === "p") return <p key={i}>{renderInline(b.text)}</p>;
        if (b.type === "h") return <p key={i} className="md-h">{renderInline(b.text)}</p>;
        const Tag = b.type;
        return <Tag key={i}>{b.items.map((it, j) => <li key={j}>{renderInline(it)}</li>)}</Tag>;
      })}
    </div>
  );
}

function downloadChart(r) {
  const a = document.createElement("a");
  a.href = `data:image/png;base64,${r.image_base64}`;
  a.download = r.filename || "chart.png";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

export default function App() {
  const [status, setStatus] = useState(null);
  const [view, setView] = useState("dashboard");
  const [scenario, setScenario] = useState("min_risk");
  const [plan, setPlan] = useState(null);
  const [planLoading, setPlanLoading] = useState(true);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(true);
  const [modal, setModal] = useState(null); // { kind:'email'|'reorder', action, email }
  const endRef = useRef(null);

  useEffect(() => { getStatus().then(setStatus).catch(() => {}); }, []);
  useEffect(() => {
    setPlanLoading(true);
    getPlan(scenario).then(setPlan).catch(() => setPlan(null)).finally(() => setPlanLoading(false));
  }, [scenario]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading]);

  async function ask(q) {
    const query = (q ?? input).trim();
    if (!query || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: query }]);
    setLoading(true);
    try {
      const res = await sendChat(query);
      setMessages((m) => [...m, { role: "assistant", data: res }]);
    } catch {
      setMessages((m) => [...m, { role: "system", text: "Backend unreachable. Is the API running on :8000?" }]);
    } finally {
      setLoading(false);
    }
  }

  function askFromTile(q) { setAssistantOpen(true); ask(q); }

  // Decide whether an action needs a modal (ask email / confirm order) or runs directly.
  function requestAction(action) {
    if (EMAIL_ACTIONS.has(action.id)) setModal({ kind: "email", action, email: "" });
    else if (action.id === "place_reorder") setModal({ kind: "reorder", action });
    else runAction(action);
  }

  async function runAction(action, extra = {}) {
    setModal(null);
    setAssistantOpen(true);
    const label = action.label || action.id;
    const params = { ...(action.params || {}), ...extra };
    setMessages((m) => [...m, { role: "running", label }]);
    try {
      const res = await executeAction(action.id, params);
      setMessages((m) => [...m.filter((x) => x.role !== "running"),
        { role: "action", actionId: action.id, label, result: res }]);
      getStatus().then(setStatus).catch(() => {});
    } catch {
      setMessages((m) => [...m.filter((x) => x.role !== "running"),
        { role: "system", text: `Action failed: ${label}` }]);
    }
  }

  async function regen() {
    setPlanLoading(true);
    try { setPlan(await regeneratePlan(scenario)); } catch { /* keep old */ } finally { setPlanLoading(false); }
  }

  return (
    <div className="app-shell">
      <TopBar status={status} plan={plan} scenario={scenario} onScenario={setScenario}
        onRefresh={regen} refreshing={planLoading}
        onExport={() => requestAction({ id: "export_plan", label: "Export weekly plan (CSV)", params: { scenario } })} />
      <div className="shell-body">
        <LeftNav view={view} onNav={setView} assistantOpen={assistantOpen}
          onToggleAssistant={() => setAssistantOpen((o) => !o)} />
        <main className="main-col">
          {planLoading && (view === "dashboard" || view === "plan")
            ? <Skeleton />
            : <MainView view={view} plan={plan} scenario={scenario}
                onNav={setView} onAsk={askFromTile} onAction={requestAction} />}
        </main>
        {assistantOpen && (
          <Assistant messages={messages} input={input} loading={loading} endRef={endRef}
            onInput={setInput} onAsk={ask} onAction={requestAction}
            onClose={() => setAssistantOpen(false)} />
        )}
      </div>

      {modal && (
        <ActionModal
          modal={modal}
          onCancel={() => setModal(null)}
          onEmailChange={(email) => setModal((s) => ({ ...s, email }))}
          onConfirm={(extra) => runAction(modal.action, extra)}
        />
      )}
    </div>
  );
}

const NAV = [
  { key: "dashboard", icon: "▣", label: "Dashboard" },
  { key: "plan", icon: "▤", label: "Plan" },
  { key: "schedule", icon: "▦", label: "Schedule" },
  { key: "machines", icon: "⚙", label: "Machines" },
  { key: "orders", icon: "▧", label: "Orders" },
  { key: "demand", icon: "◔", label: "Demand" },
  { key: "workforce", icon: "☺", label: "Workforce" },
];

function LeftNav({ view, onNav, assistantOpen, onToggleAssistant }) {
  return (
    <nav className="leftnav">
      {NAV.map((n) => (
        <button key={n.key} className={`nav-item ${view === n.key ? "active" : ""}`} onClick={() => onNav(n.key)}>
          <span className="nav-icon">{n.icon}</span><span className="nav-label">{n.label}</span>
        </button>
      ))}
      <div className="nav-spacer" />
      <button className={`nav-item ${assistantOpen ? "active" : ""}`} onClick={onToggleAssistant}>
        <span className="nav-icon">✉</span><span className="nav-label">Assistant</span>
      </button>
    </nav>
  );
}

const SCENARIOS = [
  { key: "min_risk", label: "Min risk" },
  { key: "max_throughput", label: "Throughput" },
  { key: "min_cost", label: "Min cost" },
];

function TopBar({ status, plan, scenario, onScenario, onRefresh, refreshing, onExport }) {
  const dot = (ok) => (ok ? "dot ok" : "dot off");
  return (
    <header className="topbar2">
      <div className="tb-brand">
        <span className="tb-logo">⬢</span>
        <div>
          <div className="tb-title">Plant Control Tower</div>
          <div className="tb-sub">
            {plan?.planning_week ? `Week ${plan.planning_week.start} – ${plan.planning_week.end}` : "Production Planning Agent"}
          </div>
        </div>
      </div>

      <div className="tb-scenario">
        {SCENARIOS.map((s) => (
          <button key={s.key} className={`scn-btn ${scenario === s.key ? "active" : ""}`}
            onClick={() => onScenario(s.key)}>{s.label}</button>
        ))}
      </div>

      <div className="tb-right">
        {status && (
          <div className="tb-dots">
            <span className={dot(status.models_trained)} title="Models">● Models</span>
            <span className={dot(status.llm_configured)} title="LLM">● LLM</span>
            <span className="dot ok" title="Cache">● Cache {status.cache?.entries ?? 0}</span>
          </div>
        )}
        <button className="tb-btn" onClick={onExport}>⬇ Export</button>
        <button className="tb-btn" onClick={onRefresh} disabled={refreshing}>{refreshing ? "…" : "⟳ Refresh"}</button>
      </div>
    </header>
  );
}

function MainView({ view, plan, scenario, onNav, onAsk, onAction }) {
  switch (view) {
    case "plan": return <PlanView plan={plan} scenario={scenario} />;
    case "schedule": return <ScheduleGantt scenario={scenario} />;
    case "machines": return <MachinesView onAsk={onAsk} />;
    case "orders": return <OrdersView />;
    case "demand": return <DemandView onAction={onAction} />;
    case "workforce": return <WorkforceView />;
    default: return <Dashboard plan={plan} onNav={onNav} onAsk={onAsk} onAction={onAction} />;
  }
}

function Skeleton() {
  return (
    <div className="view">
      <div className="skel skel-hero" />
      <div className="skel-row">
        {Array.from({ length: 6 }).map((_, i) => <div key={i} className="skel skel-kpi" />)}
      </div>
      <div className="skel-row">
        {Array.from({ length: 4 }).map((_, i) => <div key={i} className="skel skel-tile" />)}
      </div>
      <div className="skel-note"><span className="spinner" /> Building this week's plan (OR-Tools is solving)…</div>
    </div>
  );
}

function Assistant({ messages, input, loading, endRef, onInput, onAsk, onAction, onClose }) {
  return (
    <aside className="assistant-dock">
      <div className="ad-head">
        <div className="ad-title">🤖 AI Copilot</div>
        <button className="ad-close" onClick={onClose} title="Collapse">✕</button>
      </div>
      <div className="ad-messages">
        {messages.length === 0 && (
          <div className="ad-empty">
            <p>Ask me about capacity, delay risk, downtime, demand, scheduling or re-orders — or tap a question.</p>
            <div className="ad-examples">
              {EXAMPLES.map((e) => (
                <button key={e} className="example" onClick={() => onAsk(e)}>{e}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => <Message key={i} m={m} onAction={onAction} />)}
        {loading && (
          <div className="msg assistant fade-in"><div className="bubble thinking"><span className="spinner" /> Analysing…</div></div>
        )}
        <div ref={endRef} />
      </div>
      <div className="composer">
        <input value={input} placeholder="Ask the copilot…"
          onChange={(e) => onInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onAsk()} />
        <button onClick={() => onAsk()} disabled={loading}>Send</button>
      </div>
    </aside>
  );
}


function ActionModal({ modal, onCancel, onEmailChange, onConfirm }) {
  const isEmail = modal.kind === "email";
  const emailOk = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(modal.email || "");
  const p = modal.action.params || {};
  return (
    <div className="modal-overlay fade-in" onClick={onCancel}>
      <div className="modal pop-in" onClick={(e) => e.stopPropagation()}>
        {isEmail ? (
          <>
            <h3>✉️ Send email</h3>
            <p className="modal-sub">Enter the recipient's email address and the agent will send it.</p>
            <input
              className="modal-input"
              type="email"
              autoFocus
              placeholder="name@company.com"
              value={modal.email}
              onChange={(e) => onEmailChange(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && emailOk && onConfirm({ to: modal.email })}
            />
            <div className="modal-btns">
              <button className="ghost" onClick={onCancel}>Cancel</button>
              <button disabled={!emailOk} onClick={() => onConfirm({ to: modal.email })}>Send email</button>
            </div>
          </>
        ) : (
          <>
            <h3>🧾 Place purchase order</h3>
            <p className="modal-sub">
              Re-order <b>{p.material_id}</b> × <b>{p.quantity}</b>. A confirmation email will be
              sent to the default recipient automatically.
            </p>
            <div className="modal-btns">
              <button className="ghost" onClick={onCancel}>Cancel</button>
              <button onClick={() => onConfirm({})}>Place order</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function ChartResult({ r, onAction }) {
  return (
    <div className="chart-result">
      {r.title && <div className="chart-title">{r.title}</div>}
      <img className="chart" alt={r.title || "chart"} src={`data:image/png;base64,${r.image_base64}`} />
      {r.insight && <div className="chart-insight">💡 {r.insight}</div>}
      <div className="chart-actions">
        <button className="chip" onClick={() => downloadChart(r)}>⬇ Download</button>
        <button className="chip" onClick={() => onAction({
          id: "email_chart", label: "Email this chart",
          params: { filename: r.filename, subject: r.title || "Production insight chart" },
        })}>✉️ Email chart</button>
      </div>
    </div>
  );
}

function OrderResult({ r }) {
  const mailed = r.email_status === "sent" || r.email_status === "simulated";
  return (
    <div className="order-success pop-in">
      <div className="order-check">
        <span className="check-badge">✓</span>
        <div>
          <div className="order-line1">Order placed</div>
          <div className="order-line2">PO {r.po_id}</div>
        </div>
      </div>
      <ul className="order-detail">
        <li><span>Material</span><b>{r.material_name} ({r.material_id})</b></li>
        <li><span>Quantity</span><b>{r.quantity?.toLocaleString?.() ?? r.quantity}</b></li>
        <li><span>Est. cost</span><b>₹{r.estimated_cost_inr?.toLocaleString?.() ?? r.estimated_cost_inr}</b></li>
        <li><span>Supplier</span><b>{r.supplier_id} · {r.lead_time_days}d lead</b></li>
      </ul>
      <div className={`mail-line ${mailed ? "ok" : "muted"}`}>
        {mailed ? <><span className="check-badge sm">✓</span> Confirmation mail sent{r.email_to ? ` to ${r.email_to}` : ""}</> : "Mail not sent"}
      </div>
    </div>
  );
}

function Message({ m, onAction }) {
  if (m.role === "user") return <div className="msg user fade-in"><div className="bubble">{m.text}</div></div>;
  if (m.role === "system") return <div className="msg system fade-in">{m.text}</div>;
  if (m.role === "running")
    return <div className="msg system fade-in"><span className="spinner" /> Running: {m.label}…</div>;

  if (m.role === "action") {
    const r = m.result || {};
    const isChart = m.actionId === "generate_chart" && r.image_base64;
    const isOrder = m.actionId === "place_reorder" && r.po_id;
    return (
      <div className="msg assistant fade-in">
        <div className="bubble action-result">
          {!isOrder && <div className="action-title">{m.label}</div>}
          {!isChart && !isOrder && (
            <div className={`action-status ${r.status === "error" ? "err" : "good"}`}>
              {r.status || "done"}{r.error ? `: ${r.error}` : ""}
            </div>
          )}
          {isChart && <ChartResult r={r} onAction={onAction} />}
          {isOrder && <OrderResult r={r} />}
          {!isChart && !isOrder && r.filename && <div className="mini">Saved: {r.filename}{r.rows != null ? ` (${r.rows} rows)` : ""}</div>}
          {!isChart && !isOrder && r.subject && (
            <div className="mini">✉️ “{r.subject}” → {r.to}{r.attachment ? ` (with ${r.attachment})` : ""}</div>
          )}
        </div>
      </div>
    );
  }

  // assistant answer
  const d = m.data || {};
  return (
    <div className="msg assistant fade-in">
      <div className="bubble">
        <div className="answer-head">
          {d.agent && <AgentBadge agent={d.agent} />}
          {d.cached && <span className="cached">cached</span>}
        </div>
        <div className="answer-msg"><Markdown text={d.message} /></div>
        {d.details?.length > 0 && (
          <ul className="details">
            {d.details.slice(0, 10).map((x, i) => <li key={i}>{x}</li>)}
          </ul>
        )}
        {d.suggested_actions?.length > 0 && (
          <div className="actions">
            {d.suggested_actions.map((a, i) => (
              <button key={i} className="action-btn" onClick={() => onAction(a)}>{a.label}</button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
