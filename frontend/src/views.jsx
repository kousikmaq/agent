import { useEffect, useState } from "react";
import {
  getScenarios, getSchedule, getMachines, getPrioritize, getOrderRisk,
  getDemandForecast, getStockout, getReorderRecs, getAllocation, getCapacity,
} from "./api";

/* ------------------------------ helpers ------------------------------ */
function parseDT(s) {
  // "DD-MM-YYYY HH:MM:SS"
  const m = /^(\d{2})-(\d{2})-(\d{4})[ T](\d{2}):(\d{2})(?::(\d{2}))?/.exec(s || "");
  if (!m) return null;
  return new Date(+m[3], +m[2] - 1, +m[1], +m[4], +m[5], +(m[6] || 0));
}
const hhmm = (d) => (d ? `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}` : "");
const dayLabel = (d) => (d ? `${String(d.getDate()).padStart(2, "0")}-${String(d.getMonth() + 1).padStart(2, "0")}` : "");

const ORDER_COLORS = ["#5B8DD6", "#3FA99B", "#D9A441", "#8C6FC0", "#CC6677", "#5FA84E", "#E08A5B", "#6FB1C0", "#B07FC0", "#4E9DB8", "#C98A3C", "#7A9E4E"];
function colorFor(key) {
  let h = 0;
  for (const c of String(key)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return ORDER_COLORS[h % ORDER_COLORS.length];
}

function Loading({ label = "Loading…" }) {
  return <div className="view-loading"><span className="spinner" /> {label}</div>;
}
function ViewError({ msg }) {
  return <div className="view-error">Could not load: {msg}</div>;
}

const ABOUT = {
  dashboard: "This is your weekly control center. The plan card shows the optimised production plan; the tiles summarise capacity, bottlenecks, delay and downtime risk, demand and materials; and the alert center lists the actions worth taking now. Tap any tile to dive in, or ask Copilot about it.",
  plan: "The master plan is produced by the OR-Tools optimiser for the selected scenario. Compare scenarios to see the trade-off between throughput, on-time delivery (risk) and energy cost, then export the plan or ask Copilot which scenario best fits your goal.",
  capacity: "Capacity is how much work each machine can do versus how much the plan asks of it. Available hours start from the calendar (days × 24h for up to 3 shifts) and are then de-rated by each machine's predicted downtime, so the number is realistic — not optimistic. Utilisation = required ÷ available; anything over 100% is over capacity. Every figure here shows its own working, so nothing is a black box.",
  schedule: "This Gantt shows exactly when each operation runs on each machine for the chosen scenario. Bars are operations coloured by order — longer bars take longer. Use it to spot machine congestion and see how switching scenario re-sequences the line.",
  machines: "Each card shows how loaded a machine is (utilisation) and how healthy it is (an ML downtime score, 0–100). Red means over-capacity or likely to fail, with the predicted fault type when sensors flag a risk. Prioritise maintenance on machines with low health and high load.",
  orders: "Orders are ranked by priority (urgency, importance and value) and scored for delay risk by the ML model. 'Days over' estimates how late an order may finish and 'Miss due?' flags likely due-date breaches. Start with the highest-priority, highest-risk orders.",
  demand: "The forecast shows expected demand per product for the next 7 days with a P10–P90 confidence band (the likely low-to-high range). Stockout chips flag products likely to run out, and the reorder cards suggest quantities to buy — one click raises a purchase order.",
  workforce: "This compares the worker-hours available for each skill against the hours the plan needs. A coverage ratio above 1.0 means you have enough people; higher is more headroom. Watch any skill trending toward tight coverage before it becomes a bottleneck.",
};

function ViewAbout({ k }) {
  return (
    <div className="view-about">
      <span className="va-icon">ℹ️</span>
      <p>{ABOUT[k]}</p>
    </div>
  );
}

/* ------------------------------ shared viz ------------------------------ */
export function Ring({ value, label, sub, tone = "green", max = 100 }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const r = 26, c = 2 * Math.PI * r, off = c * (1 - pct / 100);
  const stroke = tone === "rose" ? "var(--rose)" : tone === "amber" ? "var(--amber)" : "var(--green)";
  return (
    <div className="ring">
      <svg width="70" height="70" viewBox="0 0 70 70">
        <circle cx="35" cy="35" r={r} fill="none" stroke="#eef2f8" strokeWidth="7" />
        <circle cx="35" cy="35" r={r} fill="none" stroke={stroke} strokeWidth="7"
          strokeDasharray={c} strokeDashoffset={off} strokeLinecap="round"
          transform="rotate(-90 35 35)" style={{ transition: "stroke-dashoffset .6s ease" }} />
        <text x="35" y="39" textAnchor="middle" fontSize="15" fontWeight="700" fill="#1E2733">
          {Math.round(value)}
        </text>
      </svg>
      <div className="ring-meta"><div className="ring-label">{label}</div>{sub && <div className="ring-sub">{sub}</div>}</div>
    </div>
  );
}

/* ------------------------------ Feature tiles ------------------------------ */
function Tile({ title, value, sub, tone, onOpen, onAsk }) {
  return (
    <div className={`tile ${tone}`}>
      <div className="tile-top">
        <span className="tile-title">{title}</span>
        <button className="tile-ask" title="Ask the assistant" onClick={onAsk}>Ask ▸</button>
      </div>
      <div className="tile-value">{value}</div>
      <div className="tile-sub">{sub}</div>
      <button className="tile-open" onClick={onOpen}>Open view →</button>
    </div>
  );
}

export function Dashboard({ plan, onNav, onAsk, onAction }) {
  const [alloc, setAlloc] = useState(null);
  useEffect(() => { getAllocation().then(setAlloc).catch(() => setAlloc(null)); }, []);
  if (!plan || plan.error) return <ViewError msg={plan?.error || "no plan"} />;
  const k = plan.kpis || {};
  const cap = plan.capacity || {};
  const risk = plan.risk || {};
  const dem = plan.demand || {};
  const gaps = alloc?.skill_gaps?.length ?? 0;

  const tiles = [
    { title: "Capacity", value: `${k.capacity_utilization_pct ?? "—"}%`,
      sub: `${(cap.constrained_machines || []).length} machine(s) constrained`,
      tone: (k.capacity_utilization_pct || 0) > 100 ? "rose" : (k.capacity_utilization_pct || 0) > 90 ? "amber" : "green",
      view: "machines", ask: "Is our capacity enough to handle this week's load?" },
    { title: "Bottleneck", value: (cap.constrained_machines || [])[0] || "None",
      sub: cap.expected_shortfall_hours ? `${cap.expected_shortfall_hours}h shortfall` : "line balanced",
      tone: (cap.constrained_machines || []).length ? "rose" : "green",
      view: "machines", ask: "Where is the bottleneck on the line right now?" },
    { title: "Delay risk", value: (risk.at_risk_orders || []).length,
      sub: `${risk.orders_missing_due ?? 0} may miss due date`,
      tone: (risk.at_risk_orders || []).length ? "amber" : "green",
      view: "orders", ask: "Which orders are at risk of delay, and by how many days?" },
    { title: "Downtime", value: (risk.machines_at_risk || []).length,
      sub: (risk.machines_at_risk || []).join(", ") || "all healthy",
      tone: (risk.machines_at_risk || []).length ? "rose" : "green",
      view: "machines", ask: "Which machines might break down soon?" },
    { title: "Demand (7d)", value: (dem.top || [])[0]?.product_id || "—",
      sub: (dem.top || [])[0] ? `~${Math.round((dem.top || [])[0].units)} units top SKU` : "—",
      tone: "green", view: "demand", ask: "Forecast demand for the next week" },
    { title: "Workforce", value: gaps === 0 ? "Covered" : `${gaps} gap(s)`,
      sub: alloc ? "skills vs required hours" : "…",
      tone: gaps ? "rose" : "green", view: "workforce", ask: "How should we allocate the workforce this week?" },
    { title: "Materials", value: (plan.materials_to_reorder || []).length,
      sub: (plan.materials_to_reorder || []).length ? "to re-order" : "stock OK",
      tone: (plan.materials_to_reorder || []).length ? "amber" : "green",
      view: "demand", ask: "Which materials should we re-order?" },
  ];

  return (
    <div className="view">
      <PlanHero plan={plan} />
      <h3 className="section-h">Live status</h3>
      <div className="tiles">
        {tiles.map((t) => (
          <Tile key={t.title} title={t.title} value={t.value} sub={t.sub} tone={t.tone}
            onOpen={() => onNav(t.view)} onAsk={() => onAsk(t.ask)} />
        ))}
      </div>
      <AlertCenter plan={plan} onAction={onAction} onNav={onNav} />
      <ViewAbout k="dashboard" />
    </div>
  );
}

export function PlanHero({ plan }) {
  const k = plan.kpis || {};
  const overCap = (k.capacity_utilization_pct || 0) > 100;
  return (
    <div className="hero">
      <div className="hero-head">
        <div>
          <div className="hero-title">📋 Weekly Master Plan</div>
          <div className="hero-week">{plan.planning_week?.start} → {plan.planning_week?.end} · <b>{plan.scenario}</b></div>
        </div>
      </div>
      <div className="hero-headline">{plan.headline}</div>
      <div className="kpis">
        <Kpi label="Orders" value={k.orders_planned} />
        <Kpi label="On-time" value={k.orders_on_time} tone={k.orders_on_time === 0 ? "rose" : "green"} />
        <Kpi label="Capacity" value={k.capacity_utilization_pct != null ? `${k.capacity_utilization_pct}%` : "—"} tone={overCap ? "rose" : "green"} />
        <Kpi label="Makespan" value={k.makespan_hours != null ? `${k.makespan_hours}h` : "—"} />
        <Kpi label="Tardiness" value={k.total_tardiness_hours != null ? `${k.total_tardiness_hours}h` : "—"} tone={k.total_tardiness_hours ? "amber" : "green"} />
        <Kpi label="Energy" value={k.energy_cost_inr != null ? `₹${k.energy_cost_inr}` : "—"} />
      </div>
    </div>
  );
}

function Kpi({ label, value, tone }) {
  return <div className={`kpi ${tone || ""}`}><div className="kpi-v">{value ?? "—"}</div><div className="kpi-l">{label}</div></div>;
}

/* ------------------------------ Alert center ------------------------------ */
export function AlertCenter({ plan, onAction, onNav }) {
  const risk = plan.risk || {};
  const dem = plan.demand || {};
  const alerts = [];
  for (const mid of risk.machines_at_risk || []) {
    alerts.push({ sev: "rose", icon: "⚠", text: `${mid} shows imminent breakdown risk`,
      action: { id: "send_email", label: "Email maintenance",
        params: { subject: `Maintenance alert: ${mid}`, body: `${mid} shows sensor signatures of imminent downtime. Please inspect before the next run.` } } });
  }
  for (const o of (risk.at_risk_orders || []).slice(0, 4)) {
    alerts.push({ sev: "amber", icon: "⏱", text: `Order ${o.order_id} is ~${o.days_over}d over its due date`,
      action: { id: "send_email", label: "Email alert",
        params: { subject: `At-risk order ${o.order_id}`, body: `Order ${o.order_id} is projected ${o.days_over} days past its due date. Expedite or re-sequence.` } } });
  }
  for (const p of (dem.stockout_risk || []).slice(0, 3)) {
    alerts.push({ sev: "amber", icon: "📦", text: `${p} is at risk of stockout`,
      action: null });
  }
  for (const m of plan.materials_to_reorder || []) {
    alerts.push({ sev: "amber", icon: "🧾", text: `Re-order ${m.material_id} × ${m.suggested_quantity}`,
      action: { id: "place_reorder", label: "Place order",
        params: { material_id: m.material_id, quantity: m.suggested_quantity } } });
  }
  return (
    <div className="alert-center">
      <div className="section-h with-count">Alert center <span className="count-pill">{alerts.length}</span></div>
      {alerts.length === 0 && <div className="all-clear">✓ All clear — no active alerts this week.</div>}
      {alerts.map((a, i) => (
        <div key={i} className={`alert-row ${a.sev}`}>
          <span className="alert-icon">{a.icon}</span>
          <span className="alert-text">{a.text}</span>
          {a.action
            ? <button className="alert-act" onClick={() => onAction(a.action)}>{a.action.label}</button>
            : <button className="alert-act ghost" onClick={() => onNav("demand")}>View</button>}
        </div>
      ))}
    </div>
  );
}

/* ------------------------------ Plan view ------------------------------ */
export function PlanView({ plan, scenario }) {
  const [sc, setSc] = useState(null);
  useEffect(() => { getScenarios().then(setSc).catch(() => setSc(null)); }, []);
  if (!plan || plan.error) return <ViewError msg={plan?.error || "no plan"} />;
  return (
    <div className="view">
      <PlanHero plan={plan} />
      <h3 className="section-h">Scenario comparison</h3>
      {!sc ? <Loading label="Comparing scenarios…" /> : (
        <div className="scen-grid">
          {Object.entries(sc.scenarios || {}).map(([name, v]) => (
            <div key={name} className={`scen-card ${name === scenario ? "active" : ""}`}>
              <div className="scen-name">{name}{name === scenario ? " ●" : ""}</div>
              <div className="scen-row"><span>Makespan</span><b>{v.makespan_hours}h</b></div>
              <div className="scen-row"><span>Tardiness</span><b>{v.total_tardiness_hours}h</b></div>
              <div className="scen-row"><span>Energy</span><b>₹{v.total_energy_cost_inr}</b></div>
              <div className="scen-row"><span>On-time</span><b>{v.orders_on_time}</b></div>
            </div>
          ))}
        </div>
      )}
      <h3 className="section-h">Materials to re-order</h3>
      <div className="simple-list">
        {(plan.materials_to_reorder || []).length === 0 && <div className="all-clear">Stock levels OK.</div>}
        {(plan.materials_to_reorder || []).map((m, i) => (
          <div key={i} className="li-row"><b>{m.material_id}</b><span>× {m.suggested_quantity}</span></div>
        ))}
      </div>
      <ViewAbout k="plan" />
    </div>
  );
}

/* ------------------------------ Schedule / Gantt ------------------------------ */
// Frontend cache so the Gantt for each of the three scenarios is kept and re-shown instantly.
const scheduleCache = new Map();

const SCHED_SCENARIO = {
  min_risk: { label: "Min risk", goal: "protect due dates by minimising total lateness (tardiness)" },
  max_throughput: { label: "Max throughput", goal: "finish everything as early as possible (shortest makespan)" },
  min_cost: { label: "Min cost", goal: "favour the most energy-efficient machines to cut running cost" },
};

const SCHED_KPI_DEFS = [
  ["Makespan", (k, d) => `${k.makespan_hours}h`,
    "The length of the whole plan — from the first operation starting to the last one finishing. Shorter means the line clears sooner."],
  ["Tardiness", (k, d) => `${k.total_tardiness_hours}h`,
    "Total hours by which orders finish after their due dates, added up across all orders. 0 means nothing is late."],
  ["Energy", (k, d) => `₹${k.total_energy_cost_inr}`,
    "Estimated electricity cost of running the machines for this plan (machine kWh × hours × tariff)."],
  ["Operations", (k, d) => `${d.operations_scheduled}`,
    "How many individual operations (steps like Mixing, Filling, Packaging) were placed on the timeline."],
];

export function ScheduleGantt({ scenario }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [cached, setCached] = useState(false);
  useEffect(() => {
    const key = `${scenario}:12`;
    if (scheduleCache.has(key)) {
      setData(scheduleCache.get(key)); setErr(null); setCached(true);
    } else {
      setData(null); setErr(null); setCached(false);
      getSchedule(scenario, 12).then((d) => { scheduleCache.set(key, d); setData(d); }).catch((e) => setErr(String(e)));
    }
    // Warm the other two scenarios in the background so switching is instant.
    for (const sc of ["min_risk", "max_throughput", "min_cost"]) {
      if (sc === scenario) continue;
      const k2 = `${sc}:12`;
      if (!scheduleCache.has(k2)) getSchedule(sc, 12).then((d) => scheduleCache.set(k2, d)).catch(() => {});
    }
  }, [scenario]);
  if (err) return <ViewError msg={err} />;
  if (!data) return <div className="view"><h3 className="section-h">Machine schedule (Gantt)</h3><Loading label="Solving schedule with OR-Tools…" /></div>;

  const asg = data.assignments || [];
  const rowsByMachine = {};
  const orderIds = [];
  let tMin = Infinity, tMax = -Infinity;
  for (const a of asg) {
    const s = parseDT(a.start), e = parseDT(a.end);
    if (!s || !e) continue;
    tMin = Math.min(tMin, s.getTime());
    tMax = Math.max(tMax, e.getTime());
    if (!orderIds.includes(a.order_id)) orderIds.push(a.order_id);
    for (const mid of String(a.machine_id).split(";")) {
      (rowsByMachine[mid] ||= []).push({ ...a, s, e });
    }
  }
  const machines = Object.keys(rowsByMachine).sort();
  const span = Math.max(1, tMax - tMin);
  const k = data.kpis || {};
  const scInfo = SCHED_SCENARIO[data.scenario] || { label: data.scenario, goal: "" };
  const ticks = 6;
  const tickEls = Array.from({ length: ticks + 1 }, (_, i) => {
    const t = new Date(tMin + (span * i) / ticks);
    return { left: (i / ticks) * 100, label: `${dayLabel(t)} ${hhmm(t)}` };
  });

  return (
    <div className="view">
      <div className="gantt-head">
        <h3 className="section-h">Machine schedule (Gantt) · {scInfo.label}{cached && <span className="sched-cached"> ⚡ cached</span>}</h3>
        <div className="gantt-kpis">
          <span>Makespan <b>{k.makespan_hours}h</b></span>
          <span>Tardiness <b>{k.total_tardiness_hours}h</b></span>
          <span>Energy <b>₹{k.total_energy_cost_inr}</b></span>
          <span>Ops <b>{data.operations_scheduled}</b></span>
        </div>
      </div>

      <div className="sched-scenario-note">
        <b>Scenario: {scInfo.label}.</b> This timeline is optimised to {scInfo.goal}. Switch the scenario
        in the top bar to see how the same orders are re-sequenced — each one is cached, so it's instant.
      </div>

      <div className="gantt">
        <div className="gantt-axis">
          <div className="gantt-axis-label" />
          <div className="gantt-axis-track">
            {tickEls.map((t, i) => <span key={i} className="gantt-tick" style={{ left: `${t.left}%` }}>{t.label}</span>)}
          </div>
        </div>
        {machines.map((mid) => (
          <div key={mid} className="gantt-row">
            <div className="gantt-mlabel">{mid}</div>
            <div className="gantt-track">
              {rowsByMachine[mid].map((a, i) => {
                const left = ((a.s.getTime() - tMin) / span) * 100;
                const width = Math.max(0.6, ((a.e.getTime() - a.s.getTime()) / span) * 100);
                return (
                  <div key={i} className="gantt-bar" title={`${a.order_id} · ${a.operation_id}\n${hhmm(a.s)}–${hhmm(a.e)} (${a.duration_min}m)\n${a.workers} workers · ₹${a.energy_cost_inr}`}
                    style={{ left: `${left}%`, width: `${width}%`, background: colorFor(a.order_id) }}>
                    <span className="gantt-bar-label">{a.order_id}·{a.operation_id}</span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {orderIds.length > 0 && (
        <div className="sched-legend">
          {orderIds.map((oid) => (
            <span key={oid} className="sched-chip"><i style={{ background: colorFor(oid) }} />{oid}</span>
          ))}
        </div>
      )}

      <div className="sched-explain">
        <h3 className="section-h">What this schedule shows</h3>
        <p className="sched-intro">
          A Gantt chart is a timeline of the shop floor. Each <b>row is a machine</b> and each <b>coloured bar is one
          operation</b> running on it, positioned left-to-right by <b>when it happens</b> and sized by <b>how long it
          takes</b>. Bars are coloured by order (see the legend), so you can follow one order as it moves through
          Mixing → Blending → Carbonation → Filling → Labeling → Packaging. Hover any bar for its order, exact times,
          workers and energy.
        </p>

        <div className="sched-defs">
          {SCHED_KPI_DEFS.map(([label, val, desc]) => (
            <div key={label} className="sched-def">
              <div className="sched-def-h">{label}</div>
              <div className="sched-def-v">{val(k, data)}</div>
              <div className="sched-def-p">{desc}</div>
            </div>
          ))}
        </div>

        <h3 className="section-h">How to read it</h3>
        <ul className="sched-read">
          <li><b>Gaps</b> on a machine row are idle time; <b>tightly packed</b> rows are your busy (bottleneck) machines.</li>
          <li>The same order's bars appear on several rows in sequence — that's the order flowing through its operations.</li>
          <li>An operation split across two machines (lot-splitting) shows a bar on each of those machine rows.</li>
          <li>Switching scenario re-sequences everything to chase a different goal — watch the KPIs above change with it.</li>
        </ul>
      </div>

      <ViewAbout k="schedule" />
    </div>
  );
}

/* ------------------------------ Capacity ------------------------------ */
function capTone(util) {
  return util > 100 ? "rose" : util > 85 ? "amber" : "green";
}

const CAP_SCALE = 150; // % of capacity the load bar spans to (100% marker sits at 2/3)

// Plain-language meaning of a machine's status, with the exact thresholds spelled out.
function statusMeaning(m) {
  const u = Math.round(m.utilization_pct);
  if (m.utilization_pct > 100) {
    return {
      tag: "Over capacity",
      text: `It needs about ${u}% of a full week's time — that's ${u - 100}% more work than it can fit. `
        + `The extra (~${m.expected_shortfall_hours}h) won't get done unless you add overtime or move some orders to another machine.`,
    };
  }
  if (m.utilization_pct > 85) {
    return {
      tag: "Almost full",
      text: `It's using about ${u}% of the week's time — nearly all of it. The work just fits, but there's `
        + `barely any spare, so even a small delay or breakdown could cause problems.`,
    };
  }
  return {
    tag: "Plenty of room",
    text: `It's using only about ${u}% of the week's time, so there's plenty to spare. `
      + `It can handle the work easily and could take on more.`,
  };
}

const round2 = (n) => Math.round(n * 100) / 100;

// Frontend-only what-if: move the overloaded machines' excess hours onto machines that still
// have spare room (<=85% used), then recompute each machine's numbers. Purely illustrative —
// it never touches the backend or the real plan.
function rebalanceMachines(machines) {
  const ms = machines.map((m) => ({ ...m, _r: m.utilization_pct ? m.p90_utilization_pct / m.utilization_pct : 1 }));
  const over = ms.filter((m) => m.utilization_pct > 100);
  const receivers = ms.filter((m) => m.utilization_pct <= 85);
  const totalExcess = over.reduce((s, m) => s + (m.required_hours - m.available_hours), 0);
  const rooms = receivers.map((m) => Math.max(0, m.available_hours - m.required_hours));
  const totalRoom = rooms.reduce((a, b) => a + b, 0);
  if (!over.length || totalExcess <= 0 || totalRoom <= 0) return null;

  const moved = Math.min(totalExcess, totalRoom);
  over.forEach((m) => {
    const out = moved * ((m.required_hours - m.available_hours) / totalExcess);
    m.required_hours = round2(m.required_hours - out);
  });
  receivers.forEach((m, i) => {
    const inc = moved * (rooms[i] / totalRoom);
    m.required_hours = round2(m.required_hours + inc);
  });
  ms.forEach((m) => {
    m.utilization_pct = m.available_hours ? round2((m.required_hours / m.available_hours) * 100) : 0;
    m.p90_utilization_pct = round2(m.utilization_pct * m._r);
    m.expected_shortfall_hours = round2(Math.max(0, m.required_hours - m.available_hours));
    m.suggested_overtime_hours = m.expected_shortfall_hours;
    m.status = m.utilization_pct > 100 ? "OVER_CAPACITY" : m.utilization_pct > 85 ? "CONSTRAINED" : "OK";
    delete m._r;
  });
  return { machines: ms, movedHours: round2(moved), fromCount: over.length, toCount: receivers.length };
}

function CapacityBar({ util, p90 }) {
  const w = Math.min(util, CAP_SCALE) / CAP_SCALE * 100;
  const wP90 = Math.min(p90, CAP_SCALE) / CAP_SCALE * 100;
  const marker = (100 / CAP_SCALE) * 100; // where the 100% line sits
  return (
    <div className="capbar">
      <div className="capbar-track">
        <div className={`capbar-p90 ${capTone(util)}`} style={{ width: `${wP90}%` }} title={`P90 (busy case): ${p90}%`} />
        <div className={`capbar-fill ${capTone(util)}`} style={{ width: `${w}%` }} />
        <div className="capbar-marker" style={{ left: `${marker}%` }}><span>100%</span></div>
      </div>
    </div>
  );
}

function MachineCapCard({ m, orig, canRebalance, onRebalance }) {
  const [open, setOpen] = useState(false);
  const tone = capTone(m.utilization_pct);
  const derateFrac = (m.downtime_derate_pct / 100).toFixed(2);
  const meaning = statusMeaning(m);
  const changed = orig && Math.round(orig.utilization_pct) !== Math.round(m.utilization_pct);
  return (
    <div className={`capcard ${tone} ${open ? "open" : ""} ${changed ? "shifted" : ""}`} onClick={() => setOpen((o) => !o)}>
      <div className="capcard-head">
        <div>
          <span className="capcard-id">{m.machine_id}</span>
          <span className="capcard-name">{m.machine_name}</span>
        </div>
        <div className="capcard-headright">
          <span className={`capcard-status ${tone}`}>{m.status.replace(/_/g, " ")}</span>
          <span className="capcard-chev">{open ? "▾" : "▸"}</span>
        </div>
      </div>

      <div className="capcard-util">
        <b>{Math.round(m.utilization_pct)}%</b>
        <span>utilised · P90 {Math.round(m.p90_utilization_pct)}%</span>
        {changed && <span className={`capcard-delta ${m.utilization_pct < orig.utilization_pct ? "down" : "up"}`}>
          was {Math.round(orig.utilization_pct)}%
        </span>}
      </div>
      <CapacityBar util={m.utilization_pct} p90={m.p90_utilization_pct} />

      <div className={`capcard-why ${tone}`}>
        <b>{meaning.tag}.</b> {meaning.text}
      </div>

      {!open && (
        <div className="capcard-actions">
          <span className="capcard-more">Click for details ▸</span>
          {canRebalance && m.utilization_pct > 100 && (
            <button className="capcard-rebtn" onClick={(e) => { e.stopPropagation(); onRebalance(); }}
              title="Move the extra work onto machines that have spare room (what-if only)">
              ⚖ Auto-balance load
            </button>
          )}
        </div>
      )}

      {open && (
        <div className="capcard-detail">
          <div className="capcard-stats">
            <div><span>Required</span><b>{m.required_hours}h</b></div>
            <div><span>Available</span><b>{m.available_hours}h</b></div>
            <div><span>Downtime de-rate</span><b>{m.downtime_derate_pct}%</b></div>
            <div><span>Shortfall</span><b className={m.expected_shortfall_hours > 0 ? "danger" : ""}>{m.expected_shortfall_hours}h</b></div>
          </div>

          <div className="capcard-defs">
            <div className="capdef">
              <b>Downtime de-rate ({m.downtime_derate_pct}%)</b>
              <p>How much of the week we expect this machine to be <em>down</em> (breakdowns/maintenance),
                so we don't plan on time it won't really have. This machine is predicted to be down about
                {" "}<b>{m.downtime_derate_pct}%</b> of the time, so we keep only {(1 - m.downtime_derate_pct / 100).toFixed(2)} of
                its hours: {m.raw_available_hours}h × (1 − {derateFrac}) = <b>{m.available_hours}h</b>.</p>
              <p className="capdef-note">Each machine has a different number because each has its own reliability —
                a dependable machine loses only a little, a fault-prone one loses more (up to a 50% cap).</p>
            </div>
            <div className="capdef">
              <b>Shortfall ({m.expected_shortfall_hours}h)</b>
              <p>The hours of work that don't fit — how much the required work is bigger than the available
                time: max(0, {m.required_hours} − {m.available_hours}) = <b>{m.expected_shortfall_hours}h</b>.
                {m.expected_shortfall_hours > 0
                  ? " That's the overtime to add, or the work to move to another machine."
                  : " Zero here means everything fits."}</p>
            </div>
          </div>

          <div className="capcard-math">
            <div className="math-title">How it's computed</div>
            <div className="math-line"><span>Available hours</span>
              <code>{m.raw_available_hours}h × (1 − {derateFrac}) = {m.available_hours}h</code>
              <em>{m.raw_available_hours}h in the week, minus this machine's {m.downtime_derate_pct}% predicted downtime</em>
            </div>
            <div className="math-line"><span>Utilisation</span>
              <code>{m.required_hours}h ÷ {m.available_hours}h = {Math.round(m.utilization_pct)}%</code>
              <em>required work ÷ realistic available hours</em>
            </div>
            <div className="math-line"><span>Busy case (P90)</span>
              <code>{Math.round(m.p90_utilization_pct)}%</code>
              <em>using P90 (worst-case) predicted durations</em>
            </div>
            <div className="math-line"><span>Shortfall</span>
              <code>max(0, {m.required_hours} − {m.available_hours}) = {m.expected_shortfall_hours}h</code>
              <em>suggested overtime to clear the overload</em>
            </div>
            <div className="math-line"><span>Status</span>
              <code>{m.status.replace(/_/g, " ")}</code>
              <em>over 100% = over capacity · over 85% = constrained</em>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CapKpi({ label, value, sub, tone = "", hint, plain }) {
  return (
    <div className={`capkpi ${tone}`} title={hint}>
      <div className="capkpi-label">{label}{hint && <span className="capkpi-i">ⓘ</span>}</div>
      <div className="capkpi-value">{value}</div>
      {sub && <div className="capkpi-sub">{sub}</div>}
      {plain && <div className="capkpi-plain">{plain}</div>}
    </div>
  );
}

export function CapacityView({ onAsk }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [sim, setSim] = useState(null);
  useEffect(() => { getCapacity(7).then(setData).catch((e) => setErr(String(e))); }, []);
  if (err) return <ViewError msg={err} />;
  if (!data) return <div className="view"><h3 className="section-h">Capacity analysis</h3><Loading label="Analysing capacity…" /></div>;

  const baseMachines = [...(data.per_machine || [])].sort((a, b) => b.utilization_pct - a.utilization_pct);
  const origById = {};
  for (const m of baseMachines) origById[m.machine_id] = m;
  const machines = sim ? [...sim.machines].sort((a, b) => b.utilization_pct - a.utilization_pct) : baseMachines;

  const canRebalance = !sim
    && baseMachines.some((m) => m.utilization_pct > 100)
    && baseMachines.some((m) => m.utilization_pct <= 85 && (m.available_hours - m.required_hours) > 0);
  const doRebalance = () => { const r = rebalanceMachines(baseMachines); if (r) setSim(r); };

  // KPIs are recomputed from the active machine set so they reflect the rebalance too.
  const totalReq = machines.reduce((s, m) => s + m.required_hours, 0);
  const totalAvail = machines.reduce((s, m) => s + m.available_hours, 0);
  const overall = totalAvail ? (totalReq / totalAvail) * 100 : 0;
  const totalShortfall = machines.reduce((s, m) => s + m.expected_shortfall_hours, 0);
  const constrained = machines.filter((m) => m.utilization_pct > 85).map((m) => m.machine_id);
  const primary = machines[0];

  return (
    <div className="view">
      <div className="cap-headrow">
        <h3 className="section-h">Capacity analysis · next {data.horizon_days} days</h3>
        <button className="tile-ask" onClick={() => onAsk("Is our capacity enough to handle this week's load?")}>Ask the assistant ▸</button>
      </div>

      {sim && (
        <div className="cap-rebalance-banner">
          <span>⚖ <b>What-if rebalance</b> — moved about <b>{sim.movedHours}h</b> from {sim.fromCount} overloaded
            machine(s) onto {sim.toCount} with spare room. This is an illustrative view only; the real plan is unchanged.</span>
          <button onClick={() => setSim(null)}>↺ Reset to actual</button>
        </div>
      )}

      <div className="capkpis">
        <CapKpi label="Overall utilisation" value={`${Math.round(overall)}%`}
          tone={capTone(overall)} sub={totalShortfall > 0.5 ? "shortfall" : "sufficient"}
          hint="Total required hours ÷ total available hours across all machines"
          plain="How busy the whole plant is. Over 100% means there's more work than machine time available." />
        <CapKpi label="Required" value={`${Math.round(totalReq)}h`}
          sub="predicted work this horizon" hint="Sum of predicted operation durations for pending orders"
          plain="The total machine-hours all the planned orders need this week." />
        <CapKpi label="Available" value={`${Math.round(totalAvail)}h`}
          sub="after downtime de-rate" hint="Calendar hours de-rated by each machine's predicted downtime"
          plain="The machine-hours we actually have — after setting time aside for expected breakdowns." />
        <CapKpi label="Shortfall" value={`${Math.round(totalShortfall)}h`}
          tone={totalShortfall > 0.5 ? "rose" : "green"} sub="suggested overtime"
          hint="Hours by which required load exceeds available capacity"
          plain="Hours of work that don't fit. This is the gap to cover with overtime or by moving orders." />
        <CapKpi label="Constrained" value={constrained.length}
          tone={constrained.length ? "amber" : "green"} sub={constrained.join(", ") || "none"}
          hint="Machines over 85% utilisation"
          plain="How many machines are running hot (above 85%). These are the ones to watch first." />
      </div>

      {primary && (
        <div className={`cap-verdict ${capTone(primary.utilization_pct)}`}>
          <b>{primary.machine_id} {primary.machine_name}</b> is the tightest constraint at{" "}
          <b>{Math.round(primary.utilization_pct)}%</b>
          {primary.expected_shortfall_hours > 0
            ? <> — about <b>{primary.expected_shortfall_hours}h</b> of overtime would clear it.</>
            : <> — still within capacity.</>}
        </div>
      )}

      <h3 className="section-h">Load vs capacity, by machine</h3>
      <div className="capgrid">
        {machines.map((m) => (
          <MachineCapCard key={m.machine_id} m={m} orig={origById[m.machine_id]}
            canRebalance={canRebalance} onRebalance={doRebalance} />
        ))}
      </div>

      <div className="cap-assumptions">
        <div className="cap-ass-title">Assumptions &amp; method <span>({data.method})</span></div>
        <ul>
          <li>Available time = horizon days × 24h (up to three 8-hour shifts).</li>
          <li>Availability is de-rated by each machine's predicted downtime (capped at 50%), so estimates aren't optimistic.</li>
          <li>Required hours use ML-predicted operation durations; P90 is the busy-case estimate.</li>
          <li>Thresholds: over 100% = over capacity, over 85% = constrained.</li>
          <li><b>Auto-balance</b> is a what-if only: it shifts overloaded hours onto machines with spare room to show what a rebalanced plan could look like. It does not change the real schedule.</li>
        </ul>
      </div>

      <ViewAbout k="capacity" />
    </div>
  );
}

/* ------------------------------ Machines ------------------------------ */
export function MachinesView({ onAsk }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { getMachines().then(setData).catch((e) => setErr(String(e))); }, []);
  if (err) return <ViewError msg={err} />;
  if (!data) return <div className="view"><h3 className="section-h">Machine health</h3><Loading /></div>;
  return (
    <div className="view">
      <h3 className="section-h">Machine health &amp; capacity</h3>
      <div className="mach-grid">
        {(data.machines || []).map((m) => {
          const utilTone = m.utilization_pct > 100 ? "rose" : m.utilization_pct > 90 ? "amber" : "green";
          const healthTone = m.health_index < 40 ? "rose" : m.health_index < 75 ? "amber" : "green";
          return (
            <div key={m.machine_id} className={`mach-card ${m.alert ? "rose" : utilTone}`}>
              <div className="mach-head">
                <div>
                  <div className="mach-id">{m.machine_id}</div>
                  <div className="mach-name">{m.machine_name}</div>
                </div>
                <button className="tile-ask" onClick={() => onAsk(`What is the status of machine ${m.machine_id}?`)}>Ask ▸</button>
              </div>
              <div className="mach-rings">
                <Ring value={m.utilization_pct} label="Utilisation" sub={`${m.status.replace("_", " ").toLowerCase()}`} tone={utilTone} max={Math.max(100, m.utilization_pct)} />
                <Ring value={m.health_index} label="Health" sub={m.failure_type !== "None" ? m.failure_type : "nominal"} tone={healthTone} />
              </div>
              <div className="mach-stats">
                <div><span>Downtime risk</span><b className={m.downtime_risk_pct >= 50 ? "danger" : ""}>{m.downtime_risk_pct}%</b></div>
                <div><span>Required</span><b>{m.required_hours}h</b></div>
                <div><span>Available</span><b>{m.available_hours}h</b></div>
                <div><span>Shortfall</span><b>{m.expected_shortfall_hours}h</b></div>
              </div>
            </div>
          );
        })}
      </div>
      <ViewAbout k="machines" />
    </div>
  );
}

/* ------------------------------ Orders ------------------------------ */
export function OrdersView() {
  const [prio, setPrio] = useState(null);
  const [risk, setRisk] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    Promise.all([getPrioritize(20), getOrderRisk(50)])
      .then(([p, r]) => { setPrio(p); setRisk(r); })
      .catch((e) => setErr(String(e)));
  }, []);
  if (err) return <ViewError msg={err} />;
  if (!prio || !risk) return <div className="view"><h3 className="section-h">Orders</h3><Loading /></div>;
  const riskById = {};
  for (const o of risk.at_risk_orders || []) riskById[o.order_id] = o;
  return (
    <div className="view">
      <h3 className="section-h">Order priority &amp; delay risk</h3>
      <div className="table-wrap">
        <table className="data-table">
          <thead><tr><th>#</th><th>Order</th><th>Product</th><th>Due</th><th>Priority</th><th>Order risk</th><th>Days over</th><th>Miss due?</th></tr></thead>
          <tbody>
            {(prio.ranked_orders || []).map((o) => {
              const r = riskById[o.order_id];
              const missTone = r?.will_miss_due ? "danger" : "";
              return (
                <tr key={o.order_id}>
                  <td>{o.rank}</td>
                  <td><b>{o.order_id}</b></td>
                  <td>{o.product}</td>
                  <td>{o.due_date}</td>
                  <td><span className="score-pill">{Math.round(o.priority_score)}</span></td>
                  <td>{r ? `${r.order_risk_pct}%` : "—"}</td>
                  <td>{r ? (r.days_over > 0 ? `+${r.days_over}` : r.days_over) : "—"}</td>
                  <td className={missTone}>{r ? (r.will_miss_due ? "Yes" : "No") : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <ViewAbout k="orders" />
    </div>
  );
}

/* ------------------------------ Demand ------------------------------ */
export function DemandView({ onAction }) {
  const [fc, setFc] = useState(null);
  const [so, setSo] = useState(null);
  const [recs, setRecs] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    Promise.all([getDemandForecast(), getStockout(), getReorderRecs()])
      .then(([a, b, c]) => { setFc(a); setSo(b); setRecs(c); })
      .catch((e) => setErr(String(e)));
  }, []);
  if (err) return <ViewError msg={err} />;
  if (!fc || !so || !recs) return <div className="view"><h3 className="section-h">Demand</h3><Loading /></div>;
  const products = (fc.products || []).slice(0, 8);
  const maxP90 = Math.max(1, ...products.map((p) => p.p90_units_total));
  return (
    <div className="view">
      <h3 className="section-h">7-day demand forecast (P10–P90 band)</h3>
      <div className="band">
        {products.map((p) => {
          const lo = (p.p10_units_total / maxP90) * 100;
          const hi = (p.p90_units_total / maxP90) * 100;
          const mid = (p.forecast_units_total / maxP90) * 100;
          return (
            <div key={p.product_id} className="band-row">
              <div className="band-label">{p.product_id}</div>
              <div className="band-track">
                <div className="band-range" style={{ left: `${lo}%`, width: `${Math.max(1, hi - lo)}%` }} />
                <div className="band-mid" style={{ left: `${mid}%` }} />
              </div>
              <div className="band-val">~{Math.round(p.forecast_units_total)} <span>({Math.round(p.p10_units_total)}–{Math.round(p.p90_units_total)})</span></div>
            </div>
          );
        })}
      </div>

      <h3 className="section-h">Stockout risk</h3>
      <div className="chip-row">
        {(so.products || []).filter((p) => p.alert).map((p) => (
          <span key={p.product_id} className="risk-chip rose">{p.product_id} · {p.stockout_next_prob_pct}%</span>
        ))}
        {(so.products || []).filter((p) => p.alert).length === 0 && <div className="all-clear">No stockout risks.</div>}
      </div>

      <h3 className="section-h">Materials to re-order</h3>
      <div className="reorder-grid">
        {(recs.recommendations || []).map((m) => (
          <div key={m.material_id} className="reorder-card">
            <div className="ro-name"><b>{m.material_id}</b> {m.material_name}</div>
            <div className="ro-stats">
              <span>Stock {m.current_stock}</span><span>Reorder pt {m.reorder_point}</span>
              <span>Suggest <b>{m.suggested_quantity}</b></span><span>₹{Math.round(m.estimated_cost_inr).toLocaleString()}</span>
            </div>
            <button className="action-btn" onClick={() => onAction({ id: "place_reorder",
              label: `Re-order ${m.material_id} ×${m.suggested_quantity}`,
              params: { material_id: m.material_id, quantity: m.suggested_quantity } })}>
              Re-order ×{m.suggested_quantity}
            </button>
          </div>
        ))}
        {(recs.recommendations || []).length === 0 && <div className="all-clear">Stock levels OK.</div>}
      </div>
      <ViewAbout k="demand" />
    </div>
  );
}

/* ------------------------------ Workforce ------------------------------ */
export function WorkforceView() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { getAllocation().then(setData).catch((e) => setErr(String(e))); }, []);
  if (err) return <ViewError msg={err} />;
  if (!data) return <div className="view"><h3 className="section-h">Workforce</h3><Loading /></div>;
  const cov = data.skill_coverage || [];
  const gaps = data.skill_gaps?.length || 0;
  const maxLoad = Math.max(1, ...cov.map((s) => s.required_worker_hours));
  return (
    <div className="view">
      <h3 className="section-h">
        Skill coverage
        <span className={`wf-headline ${gaps ? "rose" : "green"}`}>{gaps ? `${gaps} gap(s)` : "all skills covered"}</span>
      </h3>
      <div className="wf-grid">
        {cov.map((s) => {
          const tone = s.coverage_ratio >= 2 ? "green" : s.coverage_ratio >= 1 ? "amber" : "rose";
          const status = s.coverage_ratio >= 2 ? "Healthy" : s.coverage_ratio >= 1 ? "Tight" : "Short";
          const loadPct = Math.min(100, (s.required_worker_hours / s.available_worker_hours) * 100);
          return (
            <div key={s.skill} className={`wf-card ${tone}`}>
              <div className="wf-top">
                <span className="wf-skill">{s.skill}</span>
                <span className={`wf-badge ${tone}`}>{status}</span>
              </div>
              <div className="wf-ratio">{s.coverage_ratio}× <span>coverage</span></div>
              <div className="wf-bar" title={`${Math.round(loadPct)}% of available hours used`}>
                <div className={`wf-fill ${tone}`} style={{ width: `${loadPct}%` }} />
              </div>
              <div className="wf-meta">
                <span>{s.available_workers} workers</span>
                <span>needs {Math.round(s.required_worker_hours)}h of {Math.round(s.available_worker_hours)}h</span>
              </div>
            </div>
          );
        })}
      </div>
      <ViewAbout k="workforce" />
    </div>
  );
}
