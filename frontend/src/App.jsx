import { useEffect, useRef, useState, lazy, Suspense } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { getPlan, regeneratePlan, sendChat, executeAction, getInsights } from "./api";
import { useAuth } from "./auth/authContext";
import {
  Dashboard, PlanView, ScheduleGantt, MachinesView, OrdersView, DemandView, WorkforceView,
} from "./views";

const InsightsReport = lazy(() => import("./insights"));

const INSIGHTS_QUERY = "✨ Give me insights (charts & report)";

// Context-aware copilot suggestions — high-level questions relevant to the active view.
const SUGGESTIONS = {
  dashboard: [
    "Give me a summary of this week's production plan",
    "What are the biggest risks to this week's plan?",
    "Which orders are at risk of delay, and by how many days?",
    "Where is the bottleneck on the line right now?",
    "Which machines might break down soon?",
    "Is our capacity enough to handle this week's load?",
    "Forecast demand for the next week",
    "Which materials should we re-order?",
    "How should we allocate the workforce this week?",
  ],
  plan: [
    "Summarise this week's master plan",
    "Compare the three scenarios: max throughput, min risk and min cost",
    "Which scenario best protects our due dates?",
    "How many orders are on time in the current plan?",
    "What is driving the tardiness in this plan?",
  ],
  schedule: [
    "Generate an optimised production schedule",
    "What is the makespan of the current schedule?",
    "Which machine is the busiest in the schedule?",
    "How can we reduce total tardiness?",
    "Explain the operation sequence for the top order",
  ],
  machines: [
    "Is our capacity enough to handle this week's load?",
    "Where is the bottleneck on the line right now?",
    "Which machines might break down soon?",
    "What is the health status of machine M03?",
    "Which machine needs maintenance first?",
  ],
  orders: [
    "Which orders should we prioritise today?",
    "Which orders are at risk of delay, and by how many days?",
    "Which orders will miss their due date?",
    "What is the most urgent order right now?",
    "Why is the top order at risk?",
  ],
  demand: [
    "Forecast demand for the next week",
    "Which products are at risk of stockout?",
    "Which materials should we re-order?",
    "What is the demand split by region?",
    "Which SKU has the highest forecast demand?",
  ],
  workforce: [
    "How should we allocate the workforce this week?",
    "Do we have enough skilled workers for this week?",
    "Which skill has the tightest coverage?",
    "How many workers are available for Filling?",
    "Are there any workforce skill gaps?",
  ],
};

const VIEW_TITLES = {
  dashboard: "Dashboard", plan: "Plan", schedule: "Schedule", machines: "Machines",
  orders: "Orders", demand: "Demand", workforce: "Workforce",
};

function CopilotMark({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 2.5l1.9 4.9 4.9 1.9-4.9 1.9L12 16.1l-1.9-4.9L5.2 9.3l4.9-1.9z" fill="url(#cgrad)" />
      <circle cx="18.2" cy="17.6" r="2.3" fill="url(#cgrad)" />
      <defs>
        <linearGradient id="cgrad" x1="0" y1="0" x2="24" y2="24" gradientUnits="userSpaceOnUse">
          <stop stopColor="#5B8DD6" /><stop offset="1" stopColor="#8C6FC0" />
        </linearGradient>
      </defs>
    </svg>
  );
}

const AGENT_COLORS = {
  "Capacity & Scheduling": "#5B8DD6",
  "Risk & Reliability": "#CC6677",
  "Demand & Inventory": "#3FA99B",
  Orchestrator: "#8C6FC0",
};

const EMAIL_ACTIONS = new Set(["send_email", "email_chart", "email_image"]);

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
  const [view, setView] = useState("dashboard");
  const [scenario, setScenario] = useState("min_risk");
  const [plan, setPlan] = useState(null);
  const [planLoading, setPlanLoading] = useState(true);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(true);
  const [maximized, setMaximized] = useState(false);
  const [modal, setModal] = useState(null); // { kind:'email'|'reorder', action, email }
  const endRef = useRef(null);
  const { user, logout } = useAuth();

  useEffect(() => {
    setPlanLoading(true);
    getPlan(scenario).then(setPlan).catch(() => setPlan(null)).finally(() => setPlanLoading(false));
  }, [scenario]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading]);

  async function ask(q) {
    const query = (q ?? input).trim();
    if (!query || loading) return;
    setInput("");
    setAssistantOpen(true);
    setMessages((m) => [...m, { role: "user", text: query }]);
    setLoading(true);
    // "Give me insights" produces a rich chart report instead of a text answer.
    if (/give me insights|generate insights|insights report/i.test(query)) {
      setMessages((m) => [...m, { role: "running", label: "Building your insights report…" }]);
      try {
        const report = await getInsights();
        setMessages((m) => [...m.filter((x) => x.role !== "running"), { role: "insights", data: report }]);
        setMaximized(true);
      } catch {
        setMessages((m) => [...m.filter((x) => x.role !== "running"),
          { role: "system", text: "Could not build insights. Is the API running?" }]);
      } finally { setLoading(false); }
      return;
    }
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
  function clearChat() { setMessages([]); }
  function newChat() { setMessages([]); setMaximized(false); }

  function emailInsightsImage(dataUrl) {
    requestAction({ id: "email_image", label: "Email insights report",
      params: { subject: "Weekly production insights", image_base64: dataUrl } });
  }

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
      <TopBar plan={plan} scenario={scenario} onScenario={setScenario}
        onRefresh={regen} refreshing={planLoading} user={user} onLogout={logout}
        onExport={() => requestAction({ id: "export_plan", label: "Export weekly plan (CSV)", params: { scenario } })} />
      <div className={`shell-body ${assistantOpen && !maximized ? "" : "no-assistant"}`}>
        <LeftNav view={view} onNav={setView} />
        <main className="main-col">
          <AnimatePresence mode="wait">
            <motion.div
              key={planLoading && (view === "dashboard" || view === "plan") ? "skel" : view}
              initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}>
              {planLoading && (view === "dashboard" || view === "plan")
                ? <Skeleton />
                : <MainView view={view} plan={plan} scenario={scenario}
                    onNav={setView} onAsk={askFromTile} onAction={requestAction} />}
            </motion.div>
          </AnimatePresence>
        </main>
        <AnimatePresence>
          {assistantOpen && !maximized && (
            <Assistant key="dock" view={view} plan={plan} messages={messages} input={input} loading={loading}
              endRef={endRef} maximized={false}
              onInput={setInput} onAsk={ask} onAction={requestAction} onInsightsEmail={emailInsightsImage}
              onClose={() => setAssistantOpen(false)} onToggleMax={() => setMaximized(true)}
              onNewChat={newChat} onClearChat={clearChat} />
          )}
        </AnimatePresence>
      </div>

      <AnimatePresence>
        {assistantOpen && maximized && (
          <div className="dock-overlay" key="ovl">
            <motion.div className="dock-overlay-bg" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              onClick={() => setMaximized(false)} />
            <Assistant key="dockmax" view={view} plan={plan} messages={messages} input={input} loading={loading}
              endRef={endRef} maximized={true}
              onInput={setInput} onAsk={ask} onAction={requestAction} onInsightsEmail={emailInsightsImage}
              onClose={() => { setMaximized(false); setAssistantOpen(false); }} onToggleMax={() => setMaximized(false)}
              onNewChat={newChat} onClearChat={clearChat} />
          </div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {!assistantOpen && (
          <motion.button className="copilot-fab" key="fab" onClick={() => setAssistantOpen(true)} title="Open Assistant"
            initial={{ opacity: 0, scale: 0.7, y: 12 }} animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.7, y: 12 }} whileHover={{ y: -3 }} whileTap={{ scale: 0.95 }}>
            <CopilotMark size={20} /><span>Assistant</span>
          </motion.button>
        )}
      </AnimatePresence>

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

function LeftNav({ view, onNav }) {
  return (
    <nav className="leftnav">
      {NAV.map((n) => (
        <button key={n.key} className={`nav-item ${view === n.key ? "active" : ""}`} onClick={() => onNav(n.key)}>
          <span className="nav-icon">{n.icon}</span><span className="nav-label">{n.label}</span>
        </button>
      ))}
    </nav>
  );
}

const VIEW_BLURB = {
  dashboard: "Your weekly control center — plan, live status and the actions worth taking now.",
  plan: "The optimised weekly plan and how the scenarios trade off throughput, risk and cost.",
  schedule: "When each operation runs on each machine for the chosen scenario.",
  machines: "How loaded and how healthy each machine is right now.",
  orders: "Order priority and ML-scored delay risk.",
  demand: "7-day demand forecast, stockout risk and materials to re-order.",
  workforce: "Skill coverage: worker-hours available vs what the plan needs.",
};

const SCENARIOS = [
  { key: "min_risk", label: "Min risk" },
  { key: "max_throughput", label: "Throughput" },
  { key: "min_cost", label: "Min cost" },
];

function UserMenu({ user, onLogout }) {
  const [open, setOpen] = useState(false);
  const name = user?.name || "User";
  const initials = name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  return (
    <div className="user-menu">
      <button className="user-chip" onClick={() => setOpen((o) => !o)}>
        <span className="user-avatar">{initials}</span>
        <span className="user-name">{name}</span>
        <span className="user-caret">▾</span>
      </button>
      {open && (
        <>
          <div className="user-backdrop" onClick={() => setOpen(false)} />
          <motion.div className="user-drop" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}>
            <div className="user-drop-name">{name}</div>
            {user?.username && <div className="user-drop-mail">{user.username}</div>}
            <button className="user-signout" onClick={() => { setOpen(false); onLogout?.(); }}>Sign out</button>
          </motion.div>
        </>
      )}
    </div>
  );
}

function TopBar({ plan, scenario, onScenario, onRefresh, refreshing, onExport, user, onLogout }) {
  return (
    <header className="topbar2">
      <div className="tb-brand">
        <span className="tb-logo">⬢</span>
        <div>
          <div className="tb-title">Production Planning</div>
          <div className="tb-sub">
            {plan?.planning_week ? `Week ${plan.planning_week.start} – ${plan.planning_week.end}` : "Schedule Optimization Agent"}
          </div>
        </div>
      </div>

      <div className="tb-scenario">
        <span className="tb-scn-label">Scenario</span>
        <div className="scn-seg">
          {SCENARIOS.map((s) => (
            <button key={s.key} className={`scn-btn ${scenario === s.key ? "active" : ""}`}
              onClick={() => onScenario(s.key)}>{s.label}</button>
          ))}
        </div>
      </div>

      <div className="tb-right">
        <button className="tb-btn" onClick={onExport}>⬇ Export</button>
        <button className="tb-btn" onClick={onRefresh} disabled={refreshing}>{refreshing ? "…" : "⟳ Refresh"}</button>
        <UserMenu user={user} onLogout={onLogout} />
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

function Assistant({ view, plan, messages, input, loading, endRef, maximized,
  onInput, onAsk, onAction, onInsightsEmail, onClose, onToggleMax, onNewChat, onClearChat }) {
  const [showSug, setShowSug] = useState(true);
  const suggestions = SUGGESTIONS[view] || SUGGESTIONS.dashboard;
  const hasChat = messages.length > 0;

  // Give answers room to breathe: collapse the suggestion list once a conversation starts.
  useEffect(() => { if (messages.length > 0) setShowSug(false); }, [messages.length]);

  return (
    <motion.aside className={`assistant-dock ${maximized ? "maximized" : ""}`} key="dock"
      initial={{ x: maximized ? 0 : 40, opacity: 0, scale: maximized ? 0.98 : 1 }}
      animate={{ x: 0, opacity: 1, scale: 1 }} exit={{ x: maximized ? 0 : 40, opacity: 0 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}>
      <div className="ad-head">
        <div className="ad-title"><CopilotMark size={18} /> Production &amp; Scheduling Assistant</div>
        <div className="ad-head-btns">
          <button className="ad-icon-btn" onClick={onNewChat} title="New chat">✎</button>
          <button className="ad-icon-btn" onClick={onClearChat} title="Clear chat" disabled={!hasChat}>🗑</button>
          <button className="ad-icon-btn" onClick={onToggleMax} title={maximized ? "Restore" : "Maximize"}>
            {maximized ? "🗗" : "🗖"}
          </button>
          <button className="ad-icon-btn" onClick={onClose} title="Close">✕</button>
        </div>
      </div>

      {maximized && (
        <div className="ad-context">
          <div className="ad-context-view">{VIEW_TITLES[view] || "Dashboard"}</div>
          <div className="ad-context-blurb">{VIEW_BLURB[view]}</div>
          {plan?.headline && <div className="ad-context-headline">📋 {plan.headline}</div>}
        </div>
      )}

      <div className="ad-sug">
        <button className="ins-cta" onClick={() => onAsk(INSIGHTS_QUERY)} disabled={loading}>
          <span className="ins-cta-spark">✨</span>
          <span><b>Generate insights report</b><small>charts + narrative you can download or email</small></span>
        </button>
        <button className="ad-sug-head" onClick={() => setShowSug((s) => !s)}>
          <span>Suggested for {VIEW_TITLES[view] || "Dashboard"}</span>
          <span className="ad-sug-caret">{showSug ? "▾" : "▸"}</span>
        </button>
        <AnimatePresence initial={false}>
          {showSug && (
            <motion.div className="ad-sug-list"
              initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.22 }}>
              {suggestions.map((e, i) => (
                <motion.button key={e} className="sug-chip" onClick={() => onAsk(e)} disabled={loading}
                  initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}
                  whileHover={{ x: 3 }} whileTap={{ scale: 0.97 }}>{e}</motion.button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="ad-messages">
        {messages.length === 0 && (
          <div className="ad-empty">
            <CopilotMark size={30} />
            <p>Hi! Ask me anything about this week's plan, tap a suggestion, or generate an insights report.</p>
          </div>
        )}
        {messages.map((m, i) => <Message key={i} m={m} onAction={onAction} onInsightsEmail={onInsightsEmail} />)}
        {loading && (
          <div className="msg assistant fade-in"><div className="bubble thinking"><span className="spinner" /> Analysing…</div></div>
        )}
        <div ref={endRef} />
      </div>
      <div className="composer">
        <input value={input} placeholder={loading ? "Please wait for the response…" : "Ask the assistant…"}
          disabled={loading}
          onChange={(e) => onInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onAsk()} />
        <button onClick={() => onAsk()} disabled={loading || !input.trim()}>Send</button>
      </div>
    </motion.aside>
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

function Message({ m, onAction, onInsightsEmail }) {
  if (m.role === "user") return <div className="msg user fade-in"><div className="bubble">{m.text}</div></div>;
  if (m.role === "system") return <div className="msg system fade-in">{m.text}</div>;
  if (m.role === "running")
    return <div className="msg system fade-in"><span className="spinner" /> Running: {m.label}…</div>;

  if (m.role === "insights") {
    return (
      <div className="msg assistant fade-in insights-msg">
        <Suspense fallback={<div className="bubble thinking"><span className="spinner" /> Rendering charts…</div>}>
          <InsightsReport report={m.data} onEmailImage={onInsightsEmail} />
        </Suspense>
      </div>
    );
  }

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
