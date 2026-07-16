import { useEffect, useRef, useState } from "react";
import { getStatus, sendChat, executeAction } from "./api";

const EXAMPLES = [
  "Where is the bottleneck right now?",
  "Which orders are at risk of delay?",
  "Which machines might break down soon?",
  "Forecast demand for the next week",
  "Give me the minimum-cost schedule",
  "Compare the three planning scenarios",
  "What materials should I re-order?",
  "Is our capacity enough this week?",
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
