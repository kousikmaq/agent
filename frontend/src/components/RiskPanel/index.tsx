import { useEffect, useMemo, useState } from "react";
import type {
  Recommendation,
  RecommendationSet,
  Risk,
  RiskReport,
  RiskSeverity,
} from "../../types/api";
import { api, ApiError } from "../../api/client";
import { ActionButton } from "../ActionButton";
import { toast } from "../Toast";

interface Props {
  report: RiskReport;
  recommendations?: RecommendationSet | null;
  /** Business date the report applies to; enables the email/order actions. */
  businessDate?: string;
  /** Raise the priority of the given orders and re-plan. `token` marks which
   * control triggered it (a risk_id, or "__bulk__" for a bulk action). */
  onMitigate?: (orderIds: string[], token: string) => void;
  /** Apply a recommended fix action and re-plan the day. */
  onApplyFix?: (
    action: string,
    label: string,
    targets: Record<string, string[]>,
    token: string
  ) => void;
  /** Apply every selected fix (priority + actions) in a single re-plan. */
  onApplyAll?: (
    orderIds: string[],
    actions: { action: string; targets: Record<string, string[]> }[],
    token: string
  ) => void;
  /** Token currently being re-planned, if any. */
  mitigating?: string | null;
  /** Orders to pre-select (delayed-order risks), e.g. from the Deliveries tab. */
  preselectOrderIds?: string[];
  /** Changes each time a pre-selection hand-off happens, to re-trigger it. */
  preselectNonce?: number;
  /** Called once the hand-off has been consumed (so it isn't re-applied). */
  onPreselectConsumed?: () => void;
}

const BULK = "__bulk__";

// Recommended-fix actions the backend can apply and re-solve, with the label
// shown on the action button.
const ACTION_LABEL: Record<string, string> = {
  ASSIGN_ALTERNATE_MACHINE: "Use alternate machines",
  ADD_SHIFT: "Add a shift",
  APPROVE_OVERTIME: "Enable overtime",
  RESCHEDULE_MAINTENANCE: "Reschedule maintenance",
  ASSIGN_ALTERNATE_WORKER: "Reassign workers",
  EXPEDITE_PURCHASE_ORDER: "Expedite purchase order",
  REPLENISH_ALTERNATE_SUPPLIER: "Replenish material",
  SPLIT_BATCH: "Split batches",
};

/** Turn a risk-type enum into a readable label (e.g. "Delayed order"). */
function prettyType(type: string): string {
  const s = type.replace(/_/g, " ").toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

type RiskStatus = "open" | "acknowledged" | "mitigating" | "resolved";

const SEVERITY_ORDER: RiskSeverity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

const STATUS_LABEL: Record<RiskStatus, string> = {
  open: "Open",
  acknowledged: "Acknowledged",
  mitigating: "Mitigating",
  resolved: "Resolved",
};

function feasibilityClass(feasibility: string): string {
  switch (feasibility) {
    case "FEASIBLE":
      return "feas-ok";
    case "REQUIRES_APPROVAL":
      return "feas-approve";
    default:
      return "feas-no";
  }
}

/** Human-readable summary of affected/target entities. */
function summarizeEntities(entities: Record<string, string[]>): string {
  const parts: string[] = [];
  for (const [key, values] of Object.entries(entities)) {
    if (!values || values.length === 0) continue;
    const label = key.replace(/_/g, " ").replace(/s$/, "");
    parts.push(
      values.length <= 3 ? `${values.join(", ")}` : `${values.length} ${label}s`
    );
  }
  return parts.join(" · ");
}

/** Order ids a delayed-order risk affects (empty for other risk types). */
function delayedOrderIds(risk: Risk): string[] {
  return risk.risk_type === "DELAYED_ORDER"
    ? risk.affected_entities.order_ids ?? []
    : [];
}

/**
 * Detected operational risks, grouped and badged by severity. Risks can be
 * filtered by severity, selected in bulk, and acted on together: raise the
 * priority of the selected delayed orders and re-plan in one pass, or
 * acknowledge / resolve many at once. Status is a planner decision marker;
 * only the priority re-plan changes the committed schedule.
 */
export function RiskPanel({
  report,
  recommendations,
  businessDate,
  onMitigate,
  onApplyFix,
  onApplyAll,
  mitigating,
  preselectOrderIds,
  preselectNonce,
  onPreselectConsumed,
}: Props) {
  const [status, setStatus] = useState<Record<string, RiskStatus>>({});
  const [hideResolved, setHideResolved] = useState(false);
  const [severityFilter, setSeverityFilter] = useState<RiskSeverity | null>(null);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  // Orders handed off from Deliveries (may include at-risk orders that have no
  // risk row yet); we can still raise their priority in one re-plan.
  const [handoff, setHandoff] = useState<string[]>([]);

  // Pre-select the delayed-order risks for orders handed off from Deliveries,
  // and focus the delayed-order filter so the bulk action bar is ready.
  useEffect(() => {
    if (!preselectOrderIds || preselectOrderIds.length === 0) return;
    const wanted = new Set(preselectOrderIds);
    const ids = report.risks
      .filter(
        (r) =>
          r.risk_type === "DELAYED_ORDER" &&
          (r.affected_entities.order_ids ?? []).some((o) => wanted.has(o))
      )
      .map((r) => r.risk_id);
    setHandoff(preselectOrderIds);
    if (ids.length > 0) {
      setSelected(new Set(ids));
      setTypeFilter("DELAYED_ORDER");
      setSeverityFilter(null);
    }
    onPreselectConsumed?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preselectNonce]);

  const counts = useMemo(() => {
    const map: Record<string, number> = {};
    for (const r of report.risks) map[r.severity] = (map[r.severity] ?? 0) + 1;
    return map;
  }, [report]);

  // Risk-type counts, ordered by frequency, for the type filter chips.
  const typeCounts = useMemo(() => {
    const map = new Map<string, number>();
    for (const r of report.risks) map.set(r.risk_type, (map.get(r.risk_type) ?? 0) + 1);
    return Array.from(map.entries()).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  }, [report]);

  // Map each risk id to the recommendations that address it.
  const fixesByRisk = useMemo(() => {
    const map = new Map<string, Recommendation[]>();
    for (const rec of recommendations?.recommendations ?? []) {
      for (const id of rec.addresses_risk_ids) {
        const list = map.get(id) ?? [];
        list.push(rec);
        map.set(id, list);
      }
    }
    return map;
  }, [recommendations]);

  const ranked = useMemo(
    () =>
      [...report.risks].sort(
        (a, b) =>
          SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity) ||
          a.risk_id.localeCompare(b.risk_id)
      ),
    [report]
  );

  if (report.risks.length === 0) {
    return <p className="empty">No risks detected.</p>;
  }

  // The primary recommended fix for a risk (highest-priority recommendation
  // whose action the backend can apply), with the entities it targets.
  const fixFor = (risk: Risk) => {
    const recs = fixesByRisk.get(risk.risk_id) ?? [];
    const rec = recs.find((r) => ACTION_LABEL[r.action]);
    if (!rec) return null;
    const targets =
      Object.keys(rec.target_entities).length > 0
        ? rec.target_entities
        : risk.affected_entities;
    return { action: rec.action, label: ACTION_LABEL[rec.action], targets };
  };

  const setRiskStatus = (riskId: string, next: RiskStatus) =>
    setStatus((prev) => {
      const cur = prev[riskId] ?? "open";
      // Toggling the active status returns the risk to open.
      return { ...prev, [riskId]: cur === next ? "open" : next };
    });

  const resolvedCount = Object.values(status).filter(
    (s) => s === "resolved"
  ).length;
  const openCount = report.risks.length - resolvedCount;

  const visible = ranked.filter((r) => {
    if (severityFilter && r.severity !== severityFilter) return false;
    if (typeFilter && r.risk_type !== typeFilter) return false;
    if (hideResolved && (status[r.risk_id] ?? "open") === "resolved") return false;
    return true;
  });

  const toggleSelect = (riskId: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(riskId)) next.delete(riskId);
      else next.add(riskId);
      return next;
    });

  const visibleIds = visible.map((r) => r.risk_id);
  const allVisibleSelected =
    visibleIds.length > 0 && visibleIds.every((id) => selected.has(id));
  const toggleSelectAll = () =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) visibleIds.forEach((id) => next.delete(id));
      else visibleIds.forEach((id) => next.add(id));
      return next;
    });

  const selectedRisks = ranked.filter((r) => selected.has(r.risk_id));
  const bulkOrderIds = Array.from(
    new Set(selectedRisks.flatMap(delayedOrderIds))
  );
  // Distinct fix actions across the selected non-delayed risks, with their
  // targets merged, so each action applies once for the whole selection.
  const bulkFixes = (() => {
    const map = new Map<
      string,
      { label: string; targets: Record<string, string[]> }
    >();
    for (const r of selectedRisks) {
      if (delayedOrderIds(r).length > 0) continue;
      const f = fixFor(r);
      if (!f) continue;
      const entry = map.get(f.action) ?? { label: f.label, targets: {} };
      for (const [k, v] of Object.entries(f.targets)) {
        entry.targets[k] = Array.from(
          new Set([...(entry.targets[k] ?? []), ...v])
        );
      }
      map.set(f.action, entry);
    }
    return Array.from(map.entries()).map(([action, e]) => ({ action, ...e }));
  })();
  const bulkBusy = mitigating === BULK;

  const bulkStatus = (next: RiskStatus) => {
    setStatus((prev) => {
      const map = { ...prev };
      for (const id of selected) map[id] = next;
      return map;
    });
  };

  const clearSelection = () => setSelected(new Set());

  // Agentic action: email a purchase-order request for a material shortage.
  const placeOrderFor = async (risk: Risk) => {
    const item = risk.affected_entities.material_ids?.[0] ?? "material";
    const orderId = risk.affected_entities.order_ids?.[0] ?? null;
    try {
      const res = await api.placeOrder({
        item,
        order_id: orderId,
        reason: risk.description,
      });
      toast(`Purchase order for ${item} emailed to ${res.recipient}`, "success");
    } catch (e) {
      toast(
        e instanceof ApiError ? e.message : "Failed to place order",
        "error"
      );
      throw e;
    }
  };

  return (
    <div className="panel-list">
      <div className="rec-toolbar">
        <div className="severity-summary">
          {SEVERITY_ORDER.map((s) => (
            <button
              key={s}
              type="button"
              className={`badge sev-${s.toLowerCase()} sev-filter${
                severityFilter === s ? " active" : ""
              }`}
              onClick={() =>
                setSeverityFilter((cur) => (cur === s ? null : s))
              }
              title={`Filter to ${s} risks`}
            >
              {s}: {counts[s] ?? 0}
            </button>
          ))}
          {severityFilter && (
            <button
              type="button"
              className="sev-filter-clear"
              onClick={() => setSeverityFilter(null)}
            >
              Clear filter ✕
            </button>
          )}
        </div>
        <div className="rec-summary">
          <span>
            {openCount} open · {resolvedCount} resolved
          </span>
          <label className="rec-hide">
            <input
              type="checkbox"
              checked={hideResolved}
              onChange={(e) => setHideResolved(e.target.checked)}
            />
            Hide resolved
          </label>
        </div>
      </div>

      <div className="risk-typefilter">
        <span className="risk-typefilter-label">Type:</span>
        <button
          type="button"
          className={`chip${typeFilter === null ? " active" : ""}`}
          onClick={() => setTypeFilter(null)}
        >
          All ({report.risks.length})
        </button>
        {typeCounts.map(([type, count]) => (
          <button
            key={type}
            type="button"
            className={`chip${typeFilter === type ? " active" : ""}`}
            onClick={() => setTypeFilter((cur) => (cur === type ? null : type))}
          >
            {prettyType(type)} ({count})
          </button>
        ))}
      </div>

      {handoff.length > 0 && onMitigate && (
        <div className="risk-handoff">
          <span className="risk-handoff-text">
            <strong>{handoff.length}</strong> order
            {handoff.length > 1 ? "s" : ""} from Deliveries.{" "}
            {selected.size < handoff.length && (
              <span className="muted">
                {selected.size} {selected.size === 1 ? "is" : "are"} already late
                (shown below); the rest are at-risk and have no risk yet — raise
                priority for all to keep them on time.
              </span>
            )}
          </span>
          <div className="risk-handoff-actions">
            <button
              type="button"
              className="primary"
              disabled={mitigating === "handoff"}
              onClick={() => onMitigate(handoff, "handoff")}
            >
              {mitigating === "handoff"
                ? "Re-planning…"
                : `Raise priority & re-plan all ${handoff.length}`}
            </button>
            <button
              type="button"
              className="rec-dismiss"
              onClick={() => setHandoff([])}
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      <div className="risk-selectbar">
        <label className="risk-selectall">
          <input
            type="checkbox"
            checked={allVisibleSelected}
            onChange={toggleSelectAll}
          />
          Select all{severityFilter || typeFilter ? " filtered" : ""} (
          {visibleIds.length})
        </label>
        {selected.size > 0 && (
          <span className="muted">{selected.size} selected</span>
        )}
      </div>

      {selected.size > 0 && (
        <div className="risk-bulkbar">
          <span className="risk-bulkbar-count">
            {selected.size} risk{selected.size > 1 ? "s" : ""} selected
            {bulkOrderIds.length > 0 && (
              <span className="muted">
                {" "}
                · {bulkOrderIds.length} delayed order
                {bulkOrderIds.length > 1 ? "s" : ""}
              </span>
            )}
          </span>
          <div className="risk-bulkbar-actions">
            {onApplyAll && (bulkOrderIds.length > 0 || bulkFixes.length > 0) && (
              <button
                type="button"
                className="primary"
                disabled={bulkBusy}
                onClick={() =>
                  onApplyAll(
                    bulkOrderIds,
                    bulkFixes.map((f) => ({ action: f.action, targets: f.targets })),
                    BULK
                  )
                }
                title={`Applies ${
                  bulkOrderIds.length > 0 ? "priority + " : ""
                }${bulkFixes.map((f) => f.label).join(", ")} in one re-plan`}
              >
                {bulkBusy ? "Re-planning…" : "Apply all fixes & re-plan"}
              </button>
            )}
            <button type="button" onClick={() => bulkStatus("acknowledged")}>
              Acknowledge
            </button>
            <button type="button" onClick={() => bulkStatus("resolved")}>
              Mark resolved
            </button>
            <button type="button" className="rec-dismiss" onClick={clearSelection}>
              Clear
            </button>
          </div>
          {(bulkOrderIds.length > 0 || bulkFixes.length > 0) && (
            <div className="risk-bulkbar-plan muted">
              Will apply in one re-plan:
              {bulkOrderIds.length > 0 &&
                ` raise priority (${bulkOrderIds.length} order${
                  bulkOrderIds.length > 1 ? "s" : ""
                })`}
              {bulkOrderIds.length > 0 && bulkFixes.length > 0 && " ·"}
              {bulkFixes.map((f, i) => (
                <span key={f.action}>
                  {i > 0 || bulkOrderIds.length > 0 ? " " : " "}
                  {f.label}
                  {i < bulkFixes.length - 1 ? " ·" : ""}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {visible.length === 0 && (
        <p className="empty">No risks match the current filters.</p>
      )}

      {visible.map((risk) => {
        const st = status[risk.risk_id] ?? "open";
        const fixes = fixesByRisk.get(risk.risk_id) ?? [];
        const affected = summarizeEntities(risk.affected_entities);
        const orderIds = delayedOrderIds(risk);
        // Delayed-order risks can be actively mitigated by raising priority.
        const canReplan = !!onMitigate && orderIds.length > 0;
        // Other risks apply their recommended fix action.
        const fix = !canReplan && onApplyFix ? fixFor(risk) : null;
        const isReplanning = mitigating === risk.risk_id;
        const isSelected = selected.has(risk.risk_id);
        return (
          <div
            key={risk.risk_id}
            className={`list-item risk-${st}${isSelected ? " risk-selected" : ""}`}
          >
            <div className="list-item-head">
              <input
                type="checkbox"
                className="risk-checkbox"
                checked={isSelected}
                onChange={() => toggleSelect(risk.risk_id)}
                aria-label={`Select ${risk.title}`}
              />
              <span className={`badge sev-${risk.severity.toLowerCase()}`}>
                {risk.severity}
              </span>
              <span className="list-item-title">{risk.title}</span>
              <span className="list-item-tag">{risk.risk_type}</span>
              {st !== "open" && (
                <span className={`badge risk-status-tag risk-status-${st}`}>
                  {STATUS_LABEL[st]}
                </span>
              )}
            </div>
            <div className="list-item-desc">{risk.description}</div>
            {affected && (
              <div className="list-item-meta">
                <span className="muted">Affects: {affected}</span>
              </div>
            )}

            {fixes.length > 0 && (
              <div className="risk-fixes">
                <span className="risk-fixes-label">
                  Recommended action{fixes.length > 1 ? "s" : ""} — what to do
                </span>
                <ul className="risk-fix-list">
                  {fixes.map((f) => (
                    <li key={f.recommendation_id} className="risk-fix">
                      <div className="risk-fix-head">
                        <span className="risk-fix-title">{f.title}</span>
                        <span
                          className={`badge ${feasibilityClass(f.feasibility)}`}
                        >
                          {f.feasibility.replace("_", " ")}
                        </span>
                        <span className="list-item-tag">{f.action}</span>
                      </div>
                      {f.description && (
                        <p className="risk-fix-desc">{f.description}</p>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="risk-actions">
              <button
                type="button"
                className={st === "acknowledged" ? "primary" : ""}
                onClick={() => setRiskStatus(risk.risk_id, "acknowledged")}
              >
                {st === "acknowledged" ? "Acknowledged ✓" : "Acknowledge"}
              </button>
              {canReplan ? (
                <button
                  type="button"
                  className="primary"
                  disabled={isReplanning}
                  onClick={() => onMitigate?.(orderIds, risk.risk_id)}
                >
                  {isReplanning
                    ? "Re-planning…"
                    : `Raise priority & re-plan (${orderIds.length} order${
                        orderIds.length > 1 ? "s" : ""
                      })`}
                </button>
              ) : fix ? (
                <button
                  type="button"
                  className="primary"
                  disabled={isReplanning}
                  onClick={() =>
                    onApplyFix?.(fix.action, fix.label, fix.targets, risk.risk_id)
                  }
                >
                  {isReplanning ? "Re-planning…" : `${fix.label} & re-plan`}
                </button>
              ) : (
                <button
                  type="button"
                  className={st === "mitigating" ? "primary" : ""}
                  onClick={() => setRiskStatus(risk.risk_id, "mitigating")}
                >
                  {st === "mitigating" ? "Mitigating…" : "Start mitigation"}
                </button>
              )}
              <button
                type="button"
                className={st === "resolved" ? "primary" : ""}
                onClick={() => setRiskStatus(risk.risk_id, "resolved")}
              >
                {st === "resolved" ? "Resolved ✓" : "Mark resolved"}
              </button>
              {businessDate && risk.risk_type === "MATERIAL_SHORTAGE" && (
                <ActionButton
                  variant="ghost"
                  icon="📦"
                  label={`Place order${
                    risk.affected_entities.material_ids?.[0]
                      ? ` (${risk.affected_entities.material_ids[0]})`
                      : ""
                  }`}
                  pendingLabel="Ordering…"
                  successLabel="Order sent"
                  onAction={() => placeOrderFor(risk)}
                />
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
