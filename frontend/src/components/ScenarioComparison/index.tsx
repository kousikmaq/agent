import { useEffect, useMemo, useState } from "react";
import type { ScenarioComparison as Comparison } from "../../types/api";
import { fmtCurrency, fmtMinutes, fmtPercent } from "../../utils/format";

interface Props {
  comparison: Comparison;
  onApply?: (scenarioType: string, name: string) => void;
  applying?: string | null;
  /** The scenario currently committed as the plan — highlighted and shown
   * first when the planner returns to this tab. */
  committedType?: string | null;
  /** Notifies the parent which scenario is selected (for the email report). */
  onSelect?: (scenarioType: string) => void;
}

const fmtCount = (v: number) => String(Math.round(v));

// Headline KPIs shown on each scenario selector card.
const KPI_COLUMNS: { key: string; label: string; fmt: (v: number) => string }[] = [
  { key: "makespan_minutes", label: "Makespan", fmt: fmtMinutes },
  { key: "on_time_delivery_rate", label: "OTD", fmt: fmtPercent },
  { key: "cost_total", label: "Est. cost", fmt: fmtCurrency },
];

// Full KPI breakdown shown on a scenario's page. `lowerBetter` controls whether
// a downward change counts as an improvement.
const KPI_DETAILS: {
  key: string;
  label: string;
  fmt: (v: number) => string;
  lowerBetter: boolean;
}[] = [
  { key: "makespan_minutes", label: "Makespan", fmt: fmtMinutes, lowerBetter: true },
  {
    key: "total_tardiness_minutes",
    label: "Total tardiness",
    fmt: fmtMinutes,
    lowerBetter: true,
  },
  {
    key: "on_time_delivery_rate",
    label: "On-time delivery",
    fmt: fmtPercent,
    lowerBetter: false,
  },
  {
    key: "average_machine_utilization",
    label: "Machine utilization",
    fmt: fmtPercent,
    lowerBetter: false,
  },
  { key: "scheduled_orders", label: "Scheduled orders", fmt: fmtCount, lowerBetter: false },
  { key: "work_in_progress", label: "Work in progress", fmt: fmtCount, lowerBetter: true },
];

// Cost breakdown (money) shown on a scenario's page. Lower is always cheaper,
// so every line treats a downward change as an improvement.
const COST_DETAILS: { key: string; label: string }[] = [
  { key: "cost_total", label: "Total estimated cost" },
  { key: "cost_labor_regular", label: "Labor (regular)" },
  { key: "cost_labor_overtime", label: "Labor (overtime)" },
  { key: "cost_machine", label: "Machine running" },
  { key: "cost_tardiness_penalty", label: "Late-delivery penalty" },
];

// Plain-language explanation of what each scenario changes (its "approach").
const APPROACH: Record<string, string> = {
  CURRENT_PLAN:
    "The baseline schedule with no changes applied — every other scenario is measured against this plan.",
  OVERTIME_ENABLED:
    "Extends the working window earlier and enables worker overtime so production can start sooner.",
  ALTERNATE_MACHINES:
    "Returns down machines to service as backups and clears breakdown maintenance to widen the usable machine pool.",
  ADDITIONAL_SHIFT:
    "Adds a parallel night-shift machine for each machine to increase capacity and parallelism.",
};

function delta(comparison: Comparison, name: string, key: string): number | null {
  const d = comparison.kpi_deltas[name];
  if (!d || d[key] === undefined) return null;
  return d[key];
}

/** A single delta chip rendered under a KPI value. */
function DeltaChip({
  value,
  fmt,
  better,
  betterLabel,
  worseLabel,
}: {
  value: number;
  fmt: (v: number) => string;
  better: boolean | null;
  betterLabel: string;
  worseLabel: string;
}) {
  if (value === 0) return null;
  return (
    <span className={`k-delta ${better ? "kpi-better" : "kpi-worse"}`}>
      {value < 0 ? "▼" : "▲"} {fmt(Math.abs(value))}{" "}
      {better ? betterLabel : worseLabel} vs baseline
    </span>
  );
}

/** Plain-language reasons the selected plan looks the way it does, derived
 * from its KPI deltas versus the baseline (including the main cost driver). */
function buildExplanation(comparison: Comparison, r: Comparison["results"][number]): string[] {
  if (r.is_baseline) {
    return [
      "This is the baseline schedule built from today's existing machines, workforce and shifts — every other plan is measured against it.",
    ];
  }
  const d = (key: string) => delta(comparison, r.name, key) ?? 0;
  const lines: string[] = [];

  const otd = d("on_time_delivery_rate");
  if (Math.abs(otd) >= 0.005) {
    lines.push(
      otd > 0
        ? `Delivers ${fmtPercent(otd)} more orders on time — the added capacity lets at-risk orders be scheduled before their due dates.`
        : `Delivers ${fmtPercent(Math.abs(otd))} fewer orders on time than the baseline.`
    );
  } else {
    lines.push("On-time delivery is about the same as the baseline (capacity was not the limiting factor for the late orders).");
  }

  const tard = d("total_tardiness_minutes");
  if (Math.abs(tard) >= 60) {
    lines.push(
      tard < 0
        ? `Total lateness across all orders drops by ${fmtMinutes(Math.abs(tard))}.`
        : `Total lateness rises by ${fmtMinutes(tard)} (a few orders finish later so more finish on time).`
    );
  }

  const ms = d("makespan_minutes");
  if (Math.abs(ms) >= 60) {
    lines.push(
      ms < 0
        ? `The whole plan finishes ${fmtMinutes(Math.abs(ms))} sooner because more work runs in parallel.`
        : `The whole plan finishes ${fmtMinutes(ms)} later.`
    );
  }

  const ct = d("cost_total");
  if (Math.abs(ct) >= 1) {
    const drivers = [
      { label: "overtime labour", key: "cost_labor_overtime" },
      { label: "regular labour", key: "cost_labor_regular" },
      { label: "machine running", key: "cost_machine" },
      { label: "late-delivery penalties", key: "cost_tardiness_penalty" },
    ]
      .map((x) => ({ ...x, v: d(x.key) }))
      .sort((a, b) => Math.abs(b.v) - Math.abs(a.v));
    const top = drivers[0];
    const dir = ct < 0 ? "lower" : "higher";
    let why = ".";
    if (top && Math.abs(top.v) >= 1) {
      why = ` — mostly ${fmtCurrency(Math.abs(top.v))} ${top.v < 0 ? "less" : "more"} on ${top.label}.`;
    }
    lines.push(
      `Estimated cost is ${fmtCurrency(Math.abs(ct))} ${dir}${why}` +
        (ct < 0
          ? " Fewer late orders means smaller late-delivery penalties, which can outweigh the extra labour."
          : "")
    );
  }

  return lines;
}

/**
 * Scenario workspace: a card selector across the top opens a dedicated page for
 * each what-if plan, where the planner can review full details and choose the
 * plan that best fits.
 */
export function ScenarioComparison({
  comparison,
  onApply,
  applying,
  committedType,
  onSelect,
}: Props) {
  const baselineName =
    comparison.results.find((r) => r.is_baseline)?.name ?? null;

  // The committed plan's name (if a scenario has been applied), so it can be
  // pre-selected and badged as the one in use.
  const committedName =
    comparison.results.find((r) => r.scenario_type === committedType)?.name ??
    null;

  // The "best" plan is the one that delivers the most orders on time (highest
  // OTD). Ties are broken by the least total lateness, then the shortest
  // makespan — so among equally on-time plans the tighter, faster one wins.
  const best = useMemo(() => {
    const scored = comparison.results.filter(
      (r) => r.kpis["on_time_delivery_rate"] !== undefined
    );
    if (scored.length === 0) return null;
    const winner = scored.reduce((a, b) => {
      const ao = a.kpis["on_time_delivery_rate"];
      const bo = b.kpis["on_time_delivery_rate"];
      if (bo !== ao) return bo > ao ? b : a;
      const at = a.kpis["total_tardiness_minutes"] ?? Infinity;
      const bt = b.kpis["total_tardiness_minutes"] ?? Infinity;
      if (bt !== at) return bt < at ? b : a;
      const am = a.kpis["makespan_minutes"] ?? Infinity;
      const bm = b.kpis["makespan_minutes"] ?? Infinity;
      return bm < am ? b : a;
    });
    return winner.name;
  }, [comparison.results]);

  const [selectedName, setSelectedName] = useState<string | null>(
    committedName ?? baselineName ?? comparison.results[0]?.name ?? null
  );

  // Default to the committed plan if one is applied, else the baseline, and
  // re-apply whenever the day or committed plan changes.
  useEffect(() => {
    setSelectedName(
      committedName ?? baselineName ?? comparison.results[0]?.name ?? null
    );
  }, [comparison.business_date, committedName, baselineName, comparison.results]);

  const selected =
    comparison.results.find((r) => r.name === selectedName) ??
    comparison.results[0] ??
    null;

  // Tell the parent which scenario is selected (drives the email report).
  useEffect(() => {
    if (selected) onSelect?.(selected.scenario_type);
  }, [selected, onSelect]);

  // Show the chosen plan first so it leads the row (and stays highlighted).
  const orderedResults = useMemo(() => {
    if (!selected) return comparison.results;
    return [
      selected,
      ...comparison.results.filter((r) => r.name !== selected.name),
    ];
  }, [comparison.results, selected]);

  const applyDisabled = applying !== null && applying !== undefined;

  return (
    <div className="scenario-panel">
      {committedName && (
        <div className="scenario-inuse-banner">
          <span className="scenario-inuse-dot" aria-hidden>
            ✓
          </span>
          <span>
            Currently using:{" "}
            <strong>{committedName}</strong>
            {committedName === baselineName
              ? " (baseline / original plan)"
              : ""}
          </span>
        </div>
      )}

      <p className="panel-note">
        Four what-if plans solved against today's data. Pick a scenario to open
        its page, review the full breakdown, and choose the plan that fits.
      </p>

      {/* Scenario selector — one card per scenario. */}
      <div className="scenario-cards" role="tablist" aria-label="Scenarios">
        {orderedResults.map((r) => {
          const isSel = selected?.name === r.name;
          return (
            <button
              key={r.name}
              type="button"
              role="tab"
              aria-selected={isSel}
              className={`scenario-card ${isSel ? "active" : ""} ${
                r.name === best ? "is-best" : ""
              }`}
              onClick={() => setSelectedName(r.name)}
            >
              <div className="scenario-card-head">
                <span className="scenario-card-name">{r.name}</span>
                <span className="scenario-card-badges">
                  {r.name === committedName && (
                    <span className="badge feas-ok">✓ in use</span>
                  )}
                  {r.is_baseline && <span className="badge">baseline</span>}
                  {r.name === best && (
                    <span className="badge feas-ok">best</span>
                  )}
                </span>
              </div>
              <div className="scenario-card-kpis">
                {KPI_COLUMNS.map((c) => {
                  const value = r.kpis[c.key];
                  const d = r.is_baseline
                    ? null
                    : delta(comparison, r.name, c.key);
                  return (
                    <div key={c.key} className="scenario-card-kpi">
                      <span className="k-label">{c.label}</span>
                      <span className="k-value">
                        {value === undefined ? "—" : c.fmt(value)}
                      </span>
                      {d !== null && d !== 0 && (
                        <span className={`delta ${d < 0 ? "down" : "up"}`}>
                          {d < 0 ? "▼" : "▲"} {c.fmt(Math.abs(d))}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </button>
          );
        })}
      </div>

      {/* Selected scenario page. */}
      {selected && (
        <div className="scenario-page" role="tabpanel">
          <div className="scenario-page-head">
            <div className="scenario-page-heading">
              <h3 className="scenario-page-title">
                {selected.name}
                {selected.is_baseline && (
                  <span className="muted"> · current plan</span>
                )}
                {selected.name === best && (
                  <span className="badge feas-ok">best</span>
                )}
              </h3>
              <p className="scenario-page-approach">
                {APPROACH[selected.scenario_type] ??
                  "A what-if adjustment to the current plan."}
              </p>
            </div>
            <div className="scenario-page-action">
              {(() => {
                const isCommitted = selected.scenario_type === committedType;
                if (isCommitted) {
                  return (
                    <>
                      <button type="button" className="primary" disabled>
                        ✓ In use
                      </button>
                      <span className="muted scenario-action-note">
                        This is the plan currently in use for the day.
                      </span>
                    </>
                  );
                }
                return (
                  <>
                    {onApply && (
                      <button
                        type="button"
                        className="primary"
                        disabled={applyDisabled}
                        onClick={() =>
                          onApply(selected.scenario_type, selected.name)
                        }
                      >
                        {applying === selected.name
                          ? selected.is_baseline
                            ? "Switching…"
                            : "Applying…"
                          : selected.is_baseline
                          ? "Switch to current plan"
                          : "Use this plan"}
                      </button>
                    )}
                    <span className="muted scenario-action-note">
                      {selected.is_baseline
                        ? "Restores the original baseline plan and recomputes risks, deliveries and recommendations."
                        : "Replaces today's committed plan and recomputes risks, deliveries and recommendations."}
                    </span>
                  </>
                );
              })()}
            </div>
          </div>

          <div className="scenario-section">
            <span className="scenario-approach-label">Why this plan looks like this</span>
            <ul className="scenario-why">
              {buildExplanation(comparison, selected).map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          </div>

          <div className="scenario-section">
            <span className="scenario-approach-label">Performance</span>
            <div className="scenario-kpi-grid">
              {KPI_DETAILS.map((k) => {
                const value = selected.kpis[k.key];
                const d = selected.is_baseline
                  ? null
                  : delta(comparison, selected.name, k.key);
                const better =
                  d === null || d === 0 ? null : k.lowerBetter ? d < 0 : d > 0;
                return (
                  <div key={k.key} className="scenario-kpi">
                    <span className="k-label">{k.label}</span>
                    <span className="k-value">
                      {value === undefined ? "—" : k.fmt(value)}
                    </span>
                    {d !== null && (
                      <DeltaChip
                        value={d}
                        fmt={k.fmt}
                        better={better}
                        betterLabel="better"
                        worseLabel="worse"
                      />
                    )}
                    {selected.is_baseline && (
                      <span className="k-delta muted">baseline</span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="scenario-section scenario-cost">
            <span className="scenario-approach-label">
              Cost breakdown (estimated)
            </span>
            <div className="scenario-kpi-grid">
              {COST_DETAILS.map((c) => {
                const value = selected.kpis[c.key];
                const d = selected.is_baseline
                  ? null
                  : delta(comparison, selected.name, c.key);
                const cheaper = d === null || d === 0 ? null : d < 0;
                return (
                  <div key={c.key} className="scenario-kpi">
                    <span className="k-label">{c.label}</span>
                    <span className="k-value">
                      {value === undefined ? "—" : fmtCurrency(value)}
                    </span>
                    {d !== null && (
                      <DeltaChip
                        value={d}
                        fmt={fmtCurrency}
                        better={cheaper}
                        betterLabel="cheaper"
                        worseLabel="costlier"
                      />
                    )}
                    {selected.is_baseline && (
                      <span className="k-delta muted">baseline</span>
                    )}
                  </div>
                );
              })}
            </div>
            <span className="muted scenario-cost-note">
              Estimated from standard rates — labor $36/h (overtime 1.5×),
              machine $24/h, and a late-delivery penalty of $0.25 per
              order-minute late. Directional, for comparison only.
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
