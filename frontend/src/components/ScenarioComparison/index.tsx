import { useEffect, useMemo, useState } from "react";
import type { ScenarioComparison as Comparison } from "../../types/api";
import { fmtCurrency, fmtMinutes, fmtPercent } from "../../utils/format";

interface Props {
  comparison: Comparison;
  onApply?: (scenarioType: string, name: string) => void;
  applying?: string | null;
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

/**
 * Scenario workspace: a card selector across the top opens a dedicated page for
 * each what-if plan, where the planner can review full details and choose the
 * plan that best fits.
 */
export function ScenarioComparison({ comparison, onApply, applying, onSelect }: Props) {
  const baselineName =
    comparison.results.find((r) => r.is_baseline)?.name ?? null;

  const best = useMemo(
    () =>
      comparison.results.reduce<string | null>((best, r) => {
        if (r.kpis["makespan_minutes"] === undefined) return best;
        if (best === null) return r.name;
        const bestVal = comparison.results.find((x) => x.name === best)!.kpis[
          "makespan_minutes"
        ];
        return r.kpis["makespan_minutes"] < bestVal ? r.name : best;
      }, null),
    [comparison.results]
  );

  const [selectedName, setSelectedName] = useState<string | null>(
    baselineName ?? comparison.results[0]?.name ?? null
  );

  // Reset to the baseline scenario whenever the day changes.
  useEffect(() => {
    setSelectedName(baselineName ?? comparison.results[0]?.name ?? null);
  }, [comparison.business_date, baselineName, comparison.results]);

  const selected =
    comparison.results.find((r) => r.name === selectedName) ??
    comparison.results[0] ??
    null;

  // Tell the parent which scenario is selected (drives the email report).
  useEffect(() => {
    if (selected) onSelect?.(selected.scenario_type);
  }, [selected, onSelect]);

  const applyDisabled = applying !== null && applying !== undefined;

  return (
    <div className="scenario-panel">
      <p className="panel-note">
        Four what-if plans solved against today's data. Pick a scenario to open
        its page, review the full breakdown, and choose the plan that fits.
      </p>

      {/* Scenario selector — one card per scenario. */}
      <div className="scenario-cards" role="tablist" aria-label="Scenarios">
        {comparison.results.map((r) => {
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
              {onApply && !selected.is_baseline && (
                <button
                  type="button"
                  className="primary"
                  disabled={applyDisabled}
                  onClick={() => onApply(selected.scenario_type, selected.name)}
                >
                  {applying === selected.name ? "Applying…" : "Use this plan"}
                </button>
              )}
              {selected.is_baseline ? (
                <span className="muted scenario-action-note">
                  This is the current committed plan.
                </span>
              ) : (
                <span className="muted scenario-action-note">
                  Replaces today's committed plan and recomputes risks,
                  deliveries and recommendations.
                </span>
              )}
            </div>
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
