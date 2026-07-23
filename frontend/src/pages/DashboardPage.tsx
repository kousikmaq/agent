import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api/client";
import type {
  DeliveryDriftReport,
  DeliveryReport,
  KpiSet,
  PlanModifications,
  RecommendationSet,
  RiskReport,
  ScenarioComparison as ScenarioComparisonType,
  ScheduleResult,
  WeeklyPlanReport,
} from "../types/api";
import { KpiDashboard } from "../components/KpiDashboard";
import { OverviewPanel } from "../components/OverviewPanel";
import { WeeklyPlanPanel } from "../components/WeeklyPlanPanel";
import { DailyProgressPanel } from "../components/DailyProgressPanel";
import { GanttChart } from "../components/GanttChart";
import { MachineTimeline } from "../components/MachineTimeline";
import { OrderTable } from "../components/OrderTable";
import { DeliveriesPanel } from "../components/DeliveriesPanel";
import { DeliveryDrift } from "../components/DeliveryDrift";
import { RiskPanel } from "../components/RiskPanel";
import { ScenarioComparison } from "../components/ScenarioComparison";
import { CurrentPlanPanel } from "../components/CurrentPlanPanel";
import { ChatAssistant } from "../components/ChatAssistant";
import { NextWeekPlanModal } from "../components/NextWeekPlanModal";
import { ReportEmailButton } from "../components/EmailButton";
import { DashboardSkeleton, PanelSkeleton } from "../components/Skeleton";
import { datesUpToToday, todayIso } from "../utils/format";

type Tab =
  | "overview"
  | "weekly"
  | "progress"
  | "gantt"
  | "machines"
  | "orders"
  | "deliveries"
  | "drift"
  | "risks"
  | "scenarios"
  | "current";

interface PlanData {
  schedule: ScheduleResult;
  kpis: KpiSet;
  risks: RiskReport;
  recommendations: RecommendationSet;
  scenarios: ScenarioComparisonType;
}

const TABS: { id: Tab; label: string }[] = [  { id: "overview", label: "Overview" },
  { id: "weekly", label: "Weekly Plan" },
  { id: "progress", label: "Daily Progress" },
  { id: "gantt", label: "Gantt(Machines)" },
  { id: "machines", label: "Gantt(Orders)" },
  { id: "orders", label: "Orders" },
  { id: "deliveries", label: "Deliveries" },
  { id: "drift", label: "Drift" },
  { id: "risks", label: "Risks" },
  { id: "scenarios", label: "Scenarios" },
  { id: "current", label: "Current Plan" },
];

// A next-day plan is a forward plan only: risk/assessment views need actuals
// and are hidden until the day is worked.
const NEXT_DAY_HIDDEN: Tab[] = [
  "progress",
  "deliveries",
  "drift",
  "risks",
];

// A snappier solver budget for interactive risk-mitigation re-plans.
const MITIGATE_MAX_SECONDS = 10;

// Which backend report each tab emails.
const REPORT_FOR_TAB: Record<Tab, string> = {
  overview: "overview",
  weekly: "weekly",
  progress: "daily_progress",
  gantt: "gantt_orders",
  machines: "gantt_machines",
  orders: "orders",
  deliveries: "deliveries",
  drift: "drift",
  risks: "risks",
  scenarios: "scenarios",
  current: "current_plan",
};

export function DashboardPage() {
  const [dates, setDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [data, setData] = useState<PlanData | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [status, setStatus] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [deliveries, setDeliveries] = useState<DeliveryReport | null>(null);
  const [drift, setDrift] = useState<DeliveryDriftReport | null>(null);
  // order_id -> raw priority (1 low … 10 high) from the day's snapshot.
  const [orderPriorities, setOrderPriorities] = useState<Record<string, number>>(
    {}
  );
  const [weekly, setWeekly] = useState<WeeklyPlanReport | null>(null);
  const [weeklyAsOf, setWeeklyAsOf] = useState<string>("");
  // Loading flags for the async sub-loads, so each tab can show a skeleton.
  const [deliveriesLoading, setDeliveriesLoading] = useState(false);
  const [weeklyLoading, setWeeklyLoading] = useState(false);
  const [modificationsLoading, setModificationsLoading] = useState(false);
  // A generated future day (> today): a forward plan with no actuals yet.
  const [nextDayPlan, setNextDayPlan] = useState<string | null>(null);
  // Side assistant dock visibility.
  const [assistantOpen, setAssistantOpen] = useState(false);
  // A question to auto-ask the assistant (e.g. from a chart's "Ask AI" button).
  const [assistantSeed, setAssistantSeed] = useState<{
    text: string;
    nonce: number;
  } | null>(null);
  // Next-week plan interface preview modal.
  const [nextWeekOpen, setNextWeekOpen] = useState(false);
  // Name of the scenario currently being applied as the committed plan.
  const [applyingScenario, setApplyingScenario] = useState<string | null>(null);
  // risk_id currently being re-planned via priority mitigation.
  const [mitigatingRisk, setMitigatingRisk] = useState<string | null>(null);
  // Applied-modification log for the current plan (before/after KPIs).
  const [modifications, setModifications] = useState<PlanModifications | null>(
    null
  );
  // Orders to pre-select on the Risks tab (from a Deliveries hand-off), plus a
  // nonce so each hand-off re-triggers the selection even for the same orders.
  const [preselectOrders, setPreselectOrders] = useState<string[]>([]);
  const [preselectNonce, setPreselectNonce] = useState(0);

  const goMitigateInRisks = useCallback((orderIds: string[]) => {
    if (orderIds.length === 0) return;
    setPreselectOrders(orderIds);
    setPreselectNonce((n) => n + 1);
    setTab("risks");
  }, []);

  const loadWeekly = useCallback(async (date: string, asOf?: string) => {
    setWeeklyLoading(true);
    try {
      setWeekly(await api.getWeeklyPlan(date, asOf));
    } catch {
      setWeekly(null);
    } finally {
      setWeeklyLoading(false);
    }
  }, []);

  const loadDeliveries = useCallback(async (date: string) => {
    setDeliveriesLoading(true);
    try {
      setDeliveries(await api.getDeliveries(date));
    } catch {
      setDeliveries(null);
    }
    try {
      setDrift(await api.getDeliveryDrift(date));
    } catch {
      setDrift(null);
    } finally {
      setDeliveriesLoading(false);
    }
  }, []);

  const refreshDates = useCallback(async () => {
    const res = await api.listDates();
    // The selector shows operating days up to today; the backend still holds
    // the whole week's data for the weekly plan.
    const dates = datesUpToToday(res.dates);
    setDates(dates);
    if (dates.length > 0 && !selectedDate) {
      const today = todayIso();
      setSelectedDate(dates.includes(today) ? today : dates[dates.length - 1]);
    }
  }, [selectedDate]);

  useEffect(() => {
    refreshDates().catch(() => setStatus("Failed to load dates."));
  }, [refreshDates]);

  const loadResults = useCallback(async (date: string) => {
    setLoading(true);
    setModificationsLoading(true);
    try {
      const [schedule, kpis, risks, recommendations, scenarios] =
        await Promise.all([
          api.getSchedule(date),
          api.getKpis(date),
          api.getRisks(date),
          api.getRecommendations(date),
          api.getScenarios(date),
        ]);
      setData({ schedule, kpis, risks, recommendations, scenarios });
      setStatus("");
      loadDeliveries(date);
      // Load the snapshot to get a priority for every order (not just those in
      // the delivery horizon), so the Orders tab shows no blanks.
      api
        .getSnapshot(date)
        .then((snap) => {
          const map: Record<string, number> = {};
          for (const order of snap.production_orders) {
            map[order.order_id] = order.priority;
          }
          setOrderPriorities(map);
        })
        .catch(() => setOrderPriorities({}));
      api
        .getModifications(date)
        .then(setModifications)
        .catch(() => setModifications(null))
        .finally(() => setModificationsLoading(false));
      // Daily progress only shows actuals up to today, regardless of the
      // selected planning day.
      const asOf = todayIso();
      setWeeklyAsOf(asOf);
      loadWeekly(date, asOf);
    } catch (err) {
      setData(null);
      setDeliveries(null);
      setDrift(null);
      setWeekly(null);
      setOrderPriorities({});
      if (err instanceof ApiError && err.status === 404) {
        setStatus("No results yet for this day. Run the planner.");
      } else {
        setStatus("Failed to load results.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedDate) loadResults(selectedDate);
  }, [selectedDate, loadResults]);

  // On a next-day plan, fall back to the plan overview if an assessment tab
  // (which is hidden) was active.
  useEffect(() => {
    if (selectedDate > todayIso() && NEXT_DAY_HIDDEN.includes(tab)) {
      setTab("overview");
    }
  }, [selectedDate, tab]);
  async function onGenerate() {
    setBusy(true);
    const next = nextDate(dates);
    setStatus(`Generating next day plan for ${next}…`);
    try {
      await api.generateData(next);
      await api.runSchedule(next, 6, true);
      setNextDayPlan(next);
      setSelectedDate(next);
      setStatus(`Next day plan ready for ${next}.`);
    } catch {
      setStatus("Failed to generate the next day plan.");
    } finally {
      setBusy(false);
    }
  }

  async function onRun() {
    if (!selectedDate) return;
    setBusy(true);
    setStatus("Running the optimization pipeline…");
    try {
      await api.runSchedule(selectedDate, undefined, true);
      await loadResults(selectedDate);
      setStatus("Pipeline complete.");
    } catch {
      setStatus("Failed to run the pipeline.");
    } finally {
      setBusy(false);
    }
  }

  async function onRevertPlan() {
    if (!selectedDate || busy) return;
    const ok = window.confirm(
      `Revert to the original plan for ${selectedDate}?\n\n` +
        "This discards all applied modifications and re-solves the day from " +
        "the original data, restoring the baseline plan and scenarios."
    );
    if (!ok) return;
    setBusy(true);
    setStatus(`Reverting ${selectedDate} to the original plan…`);
    try {
      await api.runSchedule(selectedDate, undefined, true);
      await loadResults(selectedDate);
      setStatus(`Reverted ${selectedDate} to the original plan.`);
    } catch {
      setStatus("Failed to revert to the original plan.");
    } finally {
      setBusy(false);
    }
  }

  async function onApplyScenario(scenarioType: string, name: string) {
    if (!selectedDate || applyingScenario) return;
    const ok = window.confirm(
      `Replace the current plan for ${selectedDate} with the "${name}" plan?\n\n` +
        "This re-solves the day and recomputes risks, deliveries and " +
        "recommendations against the new plan."
    );
    if (!ok) return;
    setApplyingScenario(name);
    setStatus(`Applying "${name}" as the plan for ${selectedDate}…`);
    try {
      await api.applyScenario(selectedDate, scenarioType);
      await loadResults(selectedDate);
      setStatus(`"${name}" is now the current plan for ${selectedDate}.`);
    } catch {
      setStatus(`Failed to apply the "${name}" plan.`);
    } finally {
      setApplyingScenario(null);
    }
  }

  async function onMitigateRisk(orderIds: string[], token: string) {
    if (!selectedDate || mitigatingRisk) return;
    const ids = Array.from(new Set(orderIds));
    if (ids.length === 0) return;
    const totalOrders = data
      ? new Set(data.schedule.scheduled_operations.map((o) => o.order_id)).size
      : 0;
    // Prioritising a large share of orders is self-defeating on a capacity-
    // bound day (everyone competes for the same hours), so warn first.
    const tooMany =
      ids.length >= 5 && (totalOrders === 0 || ids.length / totalOrders >= 0.3);
    const warning = tooMany
      ? "\n\n⚠ You are prioritising many orders at once. When capacity is the " +
        "constraint, raising everyone's priority has little effect (they " +
        "compete for the same hours) and can make the overall plan worse. " +
        "Consider prioritising only the few most critical orders, or add " +
        "capacity (overtime / add shift)."
      : "";
    const ok = window.confirm(
      `Raise the priority of ${ids.length} order${ids.length > 1 ? "s" : ""} ` +
        `(${ids.join(", ")}) to highest and re-plan ${selectedDate}?\n\n` +
        "This re-solves the day so these orders are scheduled sooner, and " +
        "recomputes KPIs, risks, deliveries and recommendations." +
        warning
    );
    if (!ok) return;
    setMitigatingRisk(token);
    setStatus(`Raising priority and re-planning ${selectedDate}…`);
    try {
      await api.mitigateOrderPriority(selectedDate, ids, 10, MITIGATE_MAX_SECONDS);
      await loadResults(selectedDate);
      setStatus(
        `Re-planned ${selectedDate} — raised priority for ` +
          `${ids.length} order${ids.length > 1 ? "s" : ""}. See the before/after.`
      );
      setTab("current");
    } catch {
      setStatus("Failed to re-plan with raised priority.");
    } finally {
      setMitigatingRisk(null);
    }
  }

  async function onApplyRiskFix(
    action: string,
    label: string,
    targets: Record<string, string[]>,
    token: string
  ) {
    if (!selectedDate || mitigatingRisk) return;
    const ok = window.confirm(
      `Apply "${label}" and re-plan ${selectedDate}?\n\n` +
        "This re-solves the day with that change and recomputes KPIs, risks, " +
        "deliveries and recommendations."
    );
    if (!ok) return;
    setMitigatingRisk(token);
    setStatus(`Applying "${label}" and re-planning ${selectedDate}…`);
    try {
      await api.applyRiskFix(selectedDate, action, targets, MITIGATE_MAX_SECONDS);
      await loadResults(selectedDate);
      setStatus(`Applied "${label}" — re-planned ${selectedDate}. See the before/after.`);
      setTab("current");
    } catch {
      setStatus(`Failed to apply "${label}".`);
    } finally {
      setMitigatingRisk(null);
    }
  }

  async function onApplyAllRiskFixes(
    orderIds: string[],
    actions: { action: string; targets: Record<string, string[]> }[],
    token: string
  ) {
    if (!selectedDate || mitigatingRisk) return;
    const ids = Array.from(new Set(orderIds));
    if (ids.length === 0 && actions.length === 0) return;
    const parts = [
      ...(ids.length ? [`raise priority (${ids.length})`] : []),
      ...actions.map((a) => a.action),
    ];
    const totalOrders = data
      ? new Set(data.schedule.scheduled_operations.map((o) => o.order_id)).size
      : 0;
    const tooMany =
      ids.length >= 5 && (totalOrders === 0 || ids.length / totalOrders >= 0.3);
    const warning = tooMany
      ? "\n\n⚠ Raising the priority of many orders at once rarely helps when " +
        "capacity is the constraint — prioritise fewer, or rely on the capacity " +
        "fixes (overtime / add shift / alternate machines)."
      : "";
    const ok = window.confirm(
      `Apply all selected fixes and re-plan ${selectedDate} in one pass?\n\n` +
        parts.join(", ") +
        "\n\nThis re-solves the day once and recomputes KPIs, risks, deliveries " +
        "and recommendations." +
        warning
    );
    if (!ok) return;
    setMitigatingRisk(token);
    setStatus(`Applying all selected fixes and re-planning ${selectedDate}…`);
    try {
      await api.applyRiskFixes(selectedDate, {
        order_ids: ids,
        actions,
        max_time_seconds: MITIGATE_MAX_SECONDS,
      });
      await loadResults(selectedDate);
      setStatus(`Applied all selected fixes — re-planned ${selectedDate}. See the before/after.`);
      setTab("current");
    } catch {
      setStatus("Failed to apply the selected fixes.");
    } finally {
      setMitigatingRisk(null);
    }
  }

  // The full committed plan for the day (the solver plans the whole backlog,
  // which can span several days). The Gantt, Machines, Orders and Overview views
  // all show this complete plan so they stay in sync with the KPIs, risks,
  // deliveries and the assistant, which are all computed over the whole plan.
  const ops = useMemo(
    () => data?.schedule.scheduled_operations ?? [],
    [data]
  );

  // Schedule scoped to the selected day for the Overview summary.
  const daySchedule = useMemo(
    () => (data ? { ...data.schedule, scheduled_operations: ops } : null),
    [data, ops]
  );

  const today = todayIso();
  // The selected day is a forward "next day plan" when it is beyond today.
  const isNextDayPlan = selectedDate > today;
  const dateOptions =
    nextDayPlan && !dates.includes(nextDayPlan) ? [...dates, nextDayPlan] : dates;
  const visibleTabs = isNextDayPlan
    ? TABS.filter((t) => !NEXT_DAY_HIDDEN.includes(t.id))
    : TABS;

  // Open the assistant and ask it to explain the current Gantt chart in plain
  // language. "gantt" is the machine-grouped view; "machines" is order-grouped.
  const askAboutChart = () => {
    const text =
      tab === "gantt"
        ? "In 4-6 short, simple sentences, explain what the 'Gantt (Machines)' chart on this screen is and how to read it — as if to someone who has never seen one. In this chart: each row is a production order, each coloured bar is a single operation, the bar's colour shows which machine runs that operation, and the horizontal axis is time across the day (left = earlier, right = later). Longer bars take longer, and you can click a machine in the legend to highlight just its work. Focus only on explaining what the chart shows and how to read it, in plain everyday words. Do NOT list lots of statistics or recommendations — keep it short and easy to understand."
        : "In 4-6 short, simple sentences, explain what the 'Gantt (Orders)' chart on this screen is and how to read it — as if to someone who has never seen one. In this chart: each row is a machine, each coloured bar is a single operation, the bar's colour shows which order it belongs to, and the horizontal axis is time across the day (left = earlier, right = later). Gaps between bars are idle time, and you can click an order in the legend to follow just that order across the machines. Focus only on explaining what the chart shows and how to read it, in plain everyday words. Do NOT list lots of statistics or recommendations — keep it short and easy to understand.";
    setAssistantSeed({ text, nonce: Date.now() });
    setAssistantOpen(true);
  };

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>Production Planning &amp; Schedule Optimization</h1>
        </div>
        <div className="controls">
          <select
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            disabled={dateOptions.length === 0}
          >
            {dateOptions.length === 0 && <option>No days</option>}
            {dateOptions.map((d) => (
              <option key={d} value={d}>
                {d > today ? `${d} — next day plan` : d}
              </option>
            ))}
          </select>
          <button
            onClick={onGenerate}
            disabled={busy}
            title="Generate the next day's plan from this week's data"
          >
            Generate Next Day
          </button>
          <button
            onClick={() => setNextWeekOpen(true)}
            title="Preview the next-week plan (published every Saturday)"
          >
            Generate Next Week
          </button>
          <button className="primary" onClick={onRun} disabled={busy || !selectedDate}>
            Run Planner
          </button>
        </div>
      </header>

      <NextWeekPlanModal
        open={nextWeekOpen}
        onClose={() => setNextWeekOpen(false)}
      />

      {status && <div className="status-bar">{status}</div>}

      {isNextDayPlan && (
        <div className="cadence-banner due">
          <strong>Next day plan</strong> for {selectedDate} — this is a forward
          plan only. Risks, recommendations, deliveries and daily progress need
          the day's actuals, so they appear once the day is worked.
        </div>
      )}

      {loading && <DashboardSkeleton />}

      {!loading && data && (
        <>
          <section className="kpi-section">
            <KpiDashboard kpis={data.kpis} />
          </section>

          <nav className="tabs">
            {visibleTabs.map((t) => (
              <button
                key={t.id}
                className={tab === t.id ? "tab active" : "tab"}
                onClick={() => setTab(t.id)}
              >
                {t.label}
                {t.id === "risks" && data.risks.risks.length > 0 && (
                  <span className="tab-count">{data.risks.risks.length}</span>
                )}
              </button>
            ))}
          </nav>

          <section className="tab-panel">
            {selectedDate && (
              <div className="tab-actionbar">
                {(tab === "gantt" || tab === "machines") && (
                  <button
                    type="button"
                    className="action-btn ab-ghost chart-ask-btn"
                    onClick={askAboutChart}
                    title="Ask the assistant to explain this chart in simple terms"
                  >
                    <span className="ab-icon" aria-hidden>
                      💡
                    </span>
                    Know more / Ask AI
                  </button>
                )}
                <ReportEmailButton
                  date={selectedDate}
                  reportType={REPORT_FOR_TAB[tab]}
                  label="Email this tab"
                />
              </div>
            )}
            {tab === "overview" && (
              <OverviewPanel
                schedule={daySchedule ?? data.schedule}
                kpis={data.kpis}
                risks={data.risks}
                recommendations={data.recommendations}
                scenarios={data.scenarios}
                deliveries={deliveries}
                onNavigate={(t) => setTab(t as Tab)}
                planOnly={isNextDayPlan}
              />
            )}
            {tab === "gantt" && (
              <GanttChart operations={ops} />
            )}
            {tab === "weekly" &&
              (weeklyLoading ? (
                <PanelSkeleton />
              ) : weekly ? (
                <WeeklyPlanPanel report={weekly} />
              ) : (
                <p className="empty">No weekly plan for this day.</p>
              ))}
            {tab === "progress" &&
              (isNextDayPlan ? (
                <p className="empty">
                  Daily progress is blocked for a next-day plan — there are no
                  actuals until the day has been worked. Progress is available
                  only up to today ({today}).
                </p>
              ) : weeklyLoading ? (
                <PanelSkeleton />
              ) : weekly ? (
                <DailyProgressPanel
                  report={weekly}
                  asOf={weeklyAsOf || weekly.as_of_date}
                  onAsOfChange={(d) => {
                    setWeeklyAsOf(d);
                    loadWeekly(selectedDate, d);
                  }}
                />
              ) : (
                <p className="empty">No progress data for this day.</p>
              ))}
            {tab === "machines" && <MachineTimeline operations={ops} />}
            {tab === "orders" && (
              <OrderTable operations={ops} priorities={orderPriorities} />
            )}
            {tab === "deliveries" &&
              (deliveriesLoading ? (
                <PanelSkeleton />
              ) : deliveries ? (
                <DeliveriesPanel
                  report={deliveries}
                  onMitigateInRisks={goMitigateInRisks}
                  onRaisePriority={(ids) => onMitigateRisk(ids, "deliveries")}
                  mitigating={mitigatingRisk}
                />
              ) : (
                <p className="empty">No delivery data for this day.</p>
              ))}
            {tab === "drift" &&
              (deliveriesLoading ? (
                <PanelSkeleton />
              ) : drift ? (
                <DeliveryDrift report={drift} />
              ) : (
                <p className="empty">No drift data for this day.</p>
              ))}
            {tab === "risks" && (
              <RiskPanel
                report={data.risks}
                recommendations={data.recommendations}
                businessDate={selectedDate}
                onMitigate={onMitigateRisk}
                onApplyFix={onApplyRiskFix}
                onApplyAll={onApplyAllRiskFixes}
                mitigating={mitigatingRisk}
                preselectOrderIds={preselectOrders}
                preselectNonce={preselectNonce}
                onPreselectConsumed={() => setPreselectOrders([])}
              />
            )}
            {tab === "scenarios" && (
              <ScenarioComparison
                comparison={data.scenarios}
                onApply={onApplyScenario}
                applying={applyingScenario}
              />
            )}
            {tab === "current" &&
              (modificationsLoading ? (
                <PanelSkeleton />
              ) : modifications ? (
                <CurrentPlanPanel data={modifications} onRevert={onRevertPlan} reverting={busy} />
              ) : (
                <p className="empty">
                  No plan modification log yet. Run the planner to establish a
                  baseline, then apply fixes from the Risks tab.
                </p>
              ))}
          </section>
        </>
      )}

      {!loading && !data && (
        <section className="tab-panel">
          {selectedDate ? (
            <div className="empty">
              <p>No plan has been generated for {selectedDate} yet.</p>
              <div className="empty-actions">
                <button className="primary" onClick={onRun} disabled={busy}>
                  Run Planner for {selectedDate}
                </button>
              </div>
            </div>
          ) : (
            <p className="empty">Select or generate a day to begin.</p>
          )}
        </section>
      )}

      {!assistantOpen && (
        <button
          className="assistant-toggle chat-fab"
          onClick={() => {
            setAssistantSeed(null);
            setAssistantOpen(true);
          }}
          title="Ask the assistant"
        >
          <span className="fab-spark" aria-hidden>
            ✨
          </span>
          Ask the assistant
        </button>
      )}
      <aside className={assistantOpen ? "assistant-dock open" : "assistant-dock"}>
        {assistantOpen && (
          <ChatAssistant
            businessDate={selectedDate}
            seed={assistantSeed}
            onClose={() => setAssistantOpen(false)}
          />
        )}
      </aside>
    </div>
  );
}

/** Compute the next business date (day after the latest, or today). */
function nextDate(dates: string[]): string {
  const base =
    dates.length > 0
      ? new Date(dates[dates.length - 1])
      : new Date();
  if (dates.length > 0) base.setDate(base.getDate() + 1);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${base.getFullYear()}-${pad(base.getMonth() + 1)}-${pad(base.getDate())}`;
}
