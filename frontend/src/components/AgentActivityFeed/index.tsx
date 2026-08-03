import type { AutonomyCapability } from "../../types/api";

interface Props {
  items: AutonomyCapability[];
  /** The business day the feed is for (used in the header). */
  date?: string;
}

/** Visual identity (icon + accent colour) per autonomous capability. */
const KIND_META: Record<
  AutonomyCapability["kind"],
  { icon: string; color: string; label: string }
> = {
  reorder: { icon: "📦", color: "#2563eb", label: "Materials" },
  conflict: { icon: "🔀", color: "#7c3aed", label: "Conflict" },
  optimize: { icon: "🛡️", color: "#059669", label: "Lowest risk" },
  commit: { icon: "✅", color: "#059669", label: "Best plan" },
  overtime: { icon: "⚡", color: "#d97706", label: "Overtime" },
  remediate: { icon: "🎯", color: "#dc2626", label: "Remediate" },
  rebalance: { icon: "⚖️", color: "#0891b2", label: "Rebalance" },
  escalation: { icon: "🚨", color: "#e11d48", label: "Escalation" },
  briefing: { icon: "✉️", color: "#64748b", label: "Briefing" },
};

function timeAgo(iso?: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (secs < 60) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  return `${days}d ago`;
}

/**
 * Creative timeline of the agent's autonomous capabilities for the day. Actions
 * that ran show their detail and impact; the rest are shown standing by, with
 * the condition that would trigger them, so the user sees both what the agent
 * did and what it is watching for. Every entry is a real, logged capability.
 */
export function AgentActivityFeed({ items, date }: Props) {
  const doneCount = items.filter((i) => i.done).length;
  const standbyCount = items.length - doneCount;

  return (
    <section className="agent-activity">
      <div className="agent-activity-head">
        <div className="agent-activity-title">
          <span className="agent-activity-spark" aria-hidden>
            🤖
          </span>
          <div>
            <h3>Agent activity</h3>
            <p className="agent-activity-sub">
              {doneCount > 0
                ? `Took ${doneCount} autonomous action${
                    doneCount === 1 ? "" : "s"
                  }${date ? ` on ${date}` : ""}, ${standbyCount} standing by`
                : `No actions needed${
                    date ? ` on ${date}` : ""
                  }, ${standbyCount} capabilities standing by`}
            </p>
          </div>
        </div>
        {doneCount > 0 && (
          <span className="agent-activity-badge">{doneCount}</span>
        )}
      </div>

      <ol className="agent-timeline">
        {items.map((e, i) => {
          const meta = KIND_META[e.kind] ?? {
            icon: "•",
            color: "#64748b",
            label: e.kind,
          };
          return (
            <li
              className={`agent-timeline-item${e.done ? "" : " standby"}`}
              key={`${e.kind}-${i}`}
            >
              <span
                className="agent-timeline-dot"
                style={{
                  backgroundColor: e.done ? meta.color : "var(--surface-2)",
                  color: e.done ? "#fff" : meta.color,
                }}
                aria-hidden
              >
                {meta.icon}
              </span>
              <div className="agent-timeline-body">
                <div className="agent-timeline-row">
                  <span className="agent-timeline-title">{e.title}</span>
                  <span className="agent-timeline-time">
                    {e.done ? timeAgo(e.at) : "standing by"}
                  </span>
                </div>
                <div className="agent-timeline-detail">
                  {e.done ? e.detail : e.condition}
                </div>
                {e.done && (e.impact || e.trigger) && (
                  <div className="agent-timeline-meta">
                    {e.impact && (
                      <span className="agent-timeline-impact">{e.impact}</span>
                    )}
                    {e.trigger && (
                      <span className="agent-timeline-trigger">
                        Why: {e.trigger}
                      </span>
                    )}
                  </div>
                )}
                <div className="agent-timeline-tags">
                  <span
                    className="agent-chip"
                    style={{ color: meta.color, borderColor: `${meta.color}55` }}
                  >
                    {meta.label}
                  </span>
                  {e.done ? (
                    <span className="agent-chip agent-chip-done">✓ Done</span>
                  ) : (
                    <span className="agent-chip agent-chip-standby">
                      {e.enabled ? "Auto · standing by" : "Standing by"}
                    </span>
                  )}
                  {e.reversible && (
                    <span className="agent-chip agent-chip-revert">
                      ↺ Reversible
                    </span>
                  )}
                  {e.emailed && (
                    <span className="agent-chip agent-chip-mail">✉ Emailed</span>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
