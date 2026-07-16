import { useEffect, useRef, useState } from "react";
import { getStatus, sendChat, executeAction, getPlan, regeneratePlan } from "./api";

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

function AgentBadge({ agent }) {
  const color = AGENT_COLORS[agent] || "#5A6675";
  return <span className="badge" style={{ background: color }}>{agent}</span>;
}

export default function App() {
  const [status, setStatus] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef(null);

  useEffect(() => { getStatus().then(setStatus).catch(() => {}); }, []);
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

  async function runAction(action) {
    const label = action.label || action.id;
    if (!window.confirm(`Run this action?\n\n${label}`)) return;
    setMessages((m) => [...m, { role: "system", text: `Running: ${label}...` }]);
    try {
      const res = await executeAction(action.id, action.params || {});
      setMessages((m) => [...m, { role: "action", label, result: res }]);
      getStatus().then(setStatus).catch(() => {});
    } catch {
      setMessages((m) => [...m, { role: "system", text: `Action failed: ${label}` }]);
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Production Planning &amp; Schedule Optimization Agent</h1>
          <p className="subtitle">Multi-agent · Microsoft Agent Framework · open source + Azure OpenAI</p>
        </div>
        {status && (
          <div className="status-pills">
            <span className={`pill ${status.models_trained ? "ok" : "warn"}`}>
              Models {status.models_trained ? "ready" : "not trained"}
            </span>
            <span className={`pill ${status.llm_configured ? "ok" : "muted"}`}>
              LLM {status.llm_configured ? "on" : "off (router mode)"}
            </span>
            <span className="pill muted">Cache {status.cache?.entries ?? 0}</span>
          </div>
        )}
      </header>

      <WeeklyPlan onAction={runAction} />

      <div className="layout">
        <main className="chat">
          <div className="messages">
            {messages.length === 0 && (
              <div className="empty">
                <h3>Ask about capacity, bottlenecks, delay risk, downtime, demand, scheduling or re-orders.</h3>
              </div>
            )}
            {messages.map((m, i) => (
              <Message key={i} m={m} onAction={runAction} />
            ))}
            {loading && <div className="msg assistant"><div className="bubble">Analysing…</div></div>}
            <div ref={endRef} />
          </div>

          <div className="composer">
            <input
              value={input}
              placeholder="Ask the production planner…"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && ask()}
            />
            <button onClick={() => ask()} disabled={loading}>Send</button>
          </div>
        </main>

        <aside className="sidebar">
          <h4>Try asking</h4>
          <div className="examples">
            {EXAMPLES.map((e) => (
              <button key={e} className="example" onClick={() => ask(e)}>{e}</button>
            ))}
          </div>
          {status?.model_metrics?.delay_risk && (
            <div className="metrics">
              <h4>Model quality</h4>
              <MetricRow label="Delay risk (F1)" value={status.model_metrics.delay_risk.macro_f1} />
              <MetricRow label="Downtime (F1)" value={status.model_metrics.downtime.f1} />
              <MetricRow label="Demand (MAPE %)" value={status.model_metrics.demand.mape_pct} />
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function MetricRow({ label, value }) {
  return (
    <div className="metric-row"><span>{label}</span><b>{value}</b></div>
  );
}

function WeeklyPlan({ onAction }) {
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => { load(); }, []);
  async function load() {
    setLoading(true);
    try { setPlan(await getPlan()); } catch { setPlan(null); } finally { setLoading(false); }
  }
  async function regen() {
    setBusy(true);
    try { setPlan(await regeneratePlan()); } catch {} finally { setBusy(false); }
  }

  if (loading) return <section className="plan"><div className="plan-head"><span className="plan-title">📋 This Week's Plan</span><span className="plan-week">building the plan…</span></div></section>;
  if (!plan || plan.error) return null;
  const k = plan.kpis || {};

  return (
    <section className="plan">
      <div className="plan-head">
        <div className="plan-heading">
          <span className="plan-title">📋 This Week's Plan</span>
          <span className="plan-week">{plan.planning_week?.start} → {plan.planning_week?.end}</span>
          <span className="plan-scenario">{plan.scenario}</span>
        </div>
        <div className="plan-actions">
          <button className="ghost" onClick={regen} disabled={busy}>{busy ? "…" : "↻ Regenerate"}</button>
          <button className="ghost" onClick={() => onAction({ id: "export_plan", label: "Export weekly plan (CSV)", params: { scenario: plan.scenario } })}>⬇ Export</button>
          <button className="ghost" onClick={() => setOpen(!open)}>{open ? "Hide" : "Show"}</button>
        </div>
      </div>
      <div className="plan-headline">{plan.headline}</div>
      {open && (
        <>
          <div className="kpis">
            <Kpi label="Orders" value={k.orders_planned} />
            <Kpi label="On-time" value={k.orders_on_time} />
            <Kpi label="Capacity" value={k.capacity_utilization_pct != null ? `${k.capacity_utilization_pct}%` : "—"} />
            <Kpi label="Makespan" value={k.makespan_hours != null ? `${k.makespan_hours}h` : "—"} />
            <Kpi label="Tardiness" value={k.total_tardiness_hours != null ? `${k.total_tardiness_hours}h` : "—"} />
            <Kpi label="Energy" value={k.energy_cost_inr != null ? `₹${k.energy_cost_inr}` : "—"} />
          </div>
          <div className="plan-grid">
            <PlanCard title="Constrained machines" tone="amber" items={plan.capacity?.constrained_machines} empty="None"
              extra={plan.capacity?.expected_shortfall_hours ? `${plan.capacity.expected_shortfall_hours}h shortfall` : null} />
            <PlanCard title="Breakdown risk" tone="rose" items={plan.risk?.machines_at_risk} empty="All healthy" />
            <PlanCard title="Top demand (7d)" tone="teal" items={(plan.demand?.top || []).map(d => `${d.product_id} · ${Math.round(d.units)} units`)} empty="—" />
            <PlanCard title="Stockout risk" tone="rose" items={plan.demand?.stockout_risk} empty="None" />
            <PlanCard title="Re-order materials" tone="blue" items={(plan.materials_to_reorder || []).map(m => `${m.material_id} ×${m.suggested_quantity}`)} empty="Stock OK" />
            <PlanCard title="Orders missing due" tone="amber" count={plan.risk?.orders_missing_due}
              items={(plan.risk?.at_risk_orders || []).map(o => `${o.order_id} +${o.days_over}d`)} empty="All on time" />
          </div>
          <details className="plan-sched">
            <summary>Optimized schedule — first {plan.schedule?.length || 0} operations (OR-Tools · {plan.scenario})</summary>
            <table>
              <thead><tr><th>Order</th><th>Op</th><th>Machine</th><th>Workers</th><th>Start</th><th>End</th></tr></thead>
              <tbody>
                {(plan.schedule || []).map((a, i) => (
                  <tr key={i}><td>{a.order_id}</td><td>{a.operation_id}</td><td>{a.machine_id}</td><td>{a.workers}</td><td>{a.start}</td><td>{a.end}</td></tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </section>
  );
}

function Kpi({ label, value }) {
  return <div className="kpi"><div className="kpi-v">{value ?? "—"}</div><div className="kpi-l">{label}</div></div>;
}

function PlanCard({ title, tone, items, empty, extra, count }) {
  const list = (items || []).filter(Boolean);
  return (
    <div className={`plan-mini ${tone}`}>
      <div className="pm-title">{title}{count > 0 ? <span className="pm-count">{count}</span> : null}</div>
      {list.length ? <ul>{list.slice(0, 5).map((x, i) => <li key={i}>{x}</li>)}</ul> : <div className="pm-empty">{empty || "—"}</div>}
      {extra ? <div className="pm-extra">{extra}</div> : null}
    </div>
  );
}


function Message({ m, onAction }) {
  if (m.role === "user") return <div className="msg user"><div className="bubble">{m.text}</div></div>;
  if (m.role === "system") return <div className="msg system">{m.text}</div>;

  if (m.role === "action") {
    const r = m.result || {};
    return (
      <div className="msg assistant">
        <div className="bubble action-result">
          <div className="action-title">{m.label}</div>
          <div className={`action-status ${r.status === "error" ? "err" : "good"}`}>
            {r.status || "done"}{r.error ? `: ${r.error}` : ""}
          </div>
          {r.image_base64 && (
            <img className="chart" alt="chart" src={`data:image/png;base64,${r.image_base64}`} />
          )}
          {r.po_id && <div className="mini">PO {r.po_id} · {r.material_name} × {r.quantity} · ₹{r.estimated_cost_inr}</div>}
          {r.filename && !r.image_base64 && <div className="mini">Saved: {r.filename} ({r.rows} rows)</div>}
          {r.subject && <div className="mini">Email “{r.subject}” → {r.to}</div>}
        </div>
      </div>
    );
  }

  // assistant answer
  const d = m.data || {};
  return (
    <div className="msg assistant">
      <div className="bubble">
        <div className="answer-head">
          {d.agent && <AgentBadge agent={d.agent} />}
          {d.cached && <span className="cached">cached</span>}
        </div>
        <div className="answer-msg">{d.message}</div>
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
