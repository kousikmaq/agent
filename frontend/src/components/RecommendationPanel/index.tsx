import { useMemo, useState } from "react";
import type { Recommendation, RecommendationSet } from "../../types/api";

interface Props {
  set: RecommendationSet;
}

type Decision = "approved" | "dismissed";

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

/** Human-readable summary of a recommendation's target entities. */
function summarizeTargets(targets: Record<string, string[]>): string {
  const parts: string[] = [];
  for (const [key, values] of Object.entries(targets)) {
    if (!values || values.length === 0) continue;
    const label = key.replace(/_/g, " ").replace(/s$/, "");
    parts.push(
      values.length <= 2
        ? values.join(", ")
        : `${values.length} ${label}${values.length > 1 ? "s" : ""}`
    );
  }
  return parts.join(" · ") || "—";
}

interface Group {
  key: string;
  title: string;
  action: string;
  priority: number;
  feasibility: string;
  description: string;
  items: Recommendation[];
  riskIds: Set<string>;
}

/**
 * Actionable, feasibility-checked recommendations (proposals only).
 *
 * Identical proposals (same title) are grouped into a single collapsible card
 * to remove redundancy, and the planner can approve or dismiss each proposal.
 * Approval is a planner decision marker — recommendations never change the
 * committed schedule.
 */
export function RecommendationPanel({ set }: Props) {
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [hideDismissed, setHideDismissed] = useState(false);

  const groups = useMemo<Group[]>(() => {
    const map = new Map<string, Group>();
    for (const rec of set.recommendations) {
      const key = `${rec.action}::${rec.title}`;
      let group = map.get(key);
      if (!group) {
        group = {
          key,
          title: rec.title,
          action: rec.action,
          priority: rec.priority,
          feasibility: rec.feasibility,
          description: rec.description,
          items: [],
          riskIds: new Set<string>(),
        };
        map.set(key, group);
      }
      group.items.push(rec);
      group.priority = Math.max(group.priority, rec.priority);
      rec.addresses_risk_ids.forEach((id) => group!.riskIds.add(id));
    }
    return Array.from(map.values()).sort(
      (a, b) => b.priority - a.priority || a.action.localeCompare(b.action)
    );
  }, [set.recommendations]);

  if (set.recommendations.length === 0) {
    return <p className="empty">No recommendations.</p>;
  }

  const approvedCount = Object.values(decisions).filter(
    (d) => d === "approved"
  ).length;
  const visibleGroups = hideDismissed
    ? groups.filter((g) => decisions[g.key] !== "dismissed")
    : groups;

  const setDecision = (key: string, decision: Decision) =>
    setDecisions((prev) => {
      const next = { ...prev };
      if (next[key] === decision) delete next[key];
      else next[key] = decision;
      return next;
    });

  return (
    <div className="panel-list">
      <div className="rec-toolbar">
        <p className="panel-note">
          Recommendations are proposals requiring planner approval — they do not
          change the schedule. Identical proposals are grouped to avoid
          redundancy.
        </p>
        <div className="rec-summary">
          <span>
            {groups.length} proposal{groups.length > 1 ? "s" : ""} ·{" "}
            {set.recommendations.length} raw · {approvedCount} approved
          </span>
          <label className="rec-hide">
            <input
              type="checkbox"
              checked={hideDismissed}
              onChange={(e) => setHideDismissed(e.target.checked)}
            />
            Hide dismissed
          </label>
        </div>
      </div>

      {visibleGroups.map((group) => {
        const decision = decisions[group.key];
        const isExpanded = expanded[group.key];
        const count = group.items.length;
        return (
          <div
            key={group.key}
            className={`list-item rec-item ${decision ? `rec-${decision}` : ""}`}
          >
            <div className="list-item-head">
              <span className="badge prio">P{group.priority}</span>
              <span className="list-item-title">{group.title}</span>
              {count > 1 && (
                <span className="badge rec-count">{count} proposals</span>
              )}
              <span className={`badge ${feasibilityClass(group.feasibility)}`}>
                {group.feasibility.replace("_", " ")}
              </span>
              {decision === "approved" && (
                <span className="badge rec-approved-tag">✓ Approved</span>
              )}
              {decision === "dismissed" && (
                <span className="badge rec-dismissed-tag">Dismissed</span>
              )}
            </div>
            <div className="list-item-desc">{group.description}</div>
            <div className="list-item-meta">
              <span className="list-item-tag">{group.action}</span>
              {group.riskIds.size > 0 && (
                <span className="muted">
                  addresses {group.riskIds.size} risk
                  {group.riskIds.size > 1 ? "s" : ""}
                </span>
              )}
              {count === 1 && (
                <span className="muted">
                  targets {summarizeTargets(group.items[0].target_entities)}
                </span>
              )}
            </div>

            {count > 1 && (
              <button
                type="button"
                className="rec-expand"
                onClick={() =>
                  setExpanded((prev) => ({
                    ...prev,
                    [group.key]: !prev[group.key],
                  }))
                }
              >
                {isExpanded ? "Hide" : "Show"} {count} individual targets
              </button>
            )}
            {count > 1 && isExpanded && (
              <ul className="rec-sublist">
                {group.items.map((rec) => (
                  <li key={rec.recommendation_id}>
                    <span className="muted">{rec.recommendation_id}</span> —{" "}
                    {summarizeTargets(rec.target_entities)}
                  </li>
                ))}
              </ul>
            )}

            <div className="rec-actions">
              <button
                type="button"
                className={decision === "approved" ? "primary" : ""}
                onClick={() => setDecision(group.key, "approved")}
              >
                {decision === "approved" ? "Approved ✓" : "Approve"}
              </button>
              <button
                type="button"
                className="rec-dismiss"
                onClick={() => setDecision(group.key, "dismissed")}
              >
                {decision === "dismissed" ? "Dismissed" : "Dismiss"}
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
