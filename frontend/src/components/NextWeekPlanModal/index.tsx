import { useMemo, useState } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
}

const pad = (n: number) => String(n).padStart(2, "0");
const iso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** Upcoming Saturday (the day the next-week plan is published). */
function upcomingSaturday(from: Date): Date {
  const d = new Date(from);
  const delta = (6 - d.getDay() + 7) % 7; // Sat = 6
  d.setDate(d.getDate() + delta);
  return d;
}

/** Monday–Saturday of the week that follows the given Saturday. */
function nextWeekDays(saturday: Date): Date[] {
  const monday = new Date(saturday);
  monday.setDate(saturday.getDate() + 2); // Sat + 2 = next Monday
  return WEEKDAYS.map((_, i) => {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    return d;
  });
}

// Representative placeholder workload — replaced by real solver output later.
const MOCK_LOAD = [
  { operations: 46, orders: 8, units: 320, hours: 62 },
  { operations: 52, orders: 9, units: 360, hours: 68 },
  { operations: 44, orders: 7, units: 300, hours: 58 },
  { operations: 50, orders: 10, units: 345, hours: 66 },
  { operations: 48, orders: 8, units: 330, hours: 64 },
  { operations: 22, orders: 4, units: 150, hours: 30 },
];

// Representative recommendations the planner would review before approving.
const MOCK_RECS: {
  title: string;
  detail: string;
  feasibility: "FEASIBLE" | "REQUIRES_APPROVAL";
}[] = [
  {
    title: "Front-load CNC-02 on Monday–Tuesday",
    detail:
      "Two high-priority orders (ORD-2043, ORD-2051) are due Wednesday. Scheduling them early clears 6h of slack.",
    feasibility: "FEASIBLE",
  },
  {
    title: "Add a Thursday overtime block on Line B",
    detail:
      "Projected load exceeds capacity by ~4h Thursday. Overtime keeps 3 orders on time.",
    feasibility: "REQUIRES_APPROVAL",
  },
  {
    title: "Pre-stage raw material for PRD-118",
    detail:
      "Inventory dips below safety stock mid-week. Reorder now to avoid a Friday stockout.",
    feasibility: "FEASIBLE",
  },
];

/**
 * Interface preview for the "Generate Next Week" flow. Frontend-only mockup with
 * placeholder data — shows both the pre-Saturday lock notice and the Saturday
 * review/approval view. A toggle lets you preview either state.
 */
export function NextWeekPlanModal({ open, onClose }: Props) {
  const today = useMemo(() => new Date(), []);
  const actualIsSaturday = today.getDay() === 6;
  const [view, setView] = useState<"locked" | "saturday" | "no-data">(
    actualIsSaturday ? "saturday" : "locked"
  );
  // Early-draft confirmation flow (frontend preview only): idle → confirm → done.
  const [earlyStep, setEarlyStep] = useState<"idle" | "confirm" | "done">("idle");
  // Saturday review flow (frontend preview only).
  const [satStep, setSatStep] = useState<
    "idle" | "confirm" | "published" | "adjust"
  >("idle");

  // Editable per-day workload + per-recommendation decisions (preview state).
  const [load, setLoad] = useState(
    MOCK_LOAD.map((d) => ({ ...d, overtime: false }))
  );
  const [recStatus, setRecStatus] = useState<
    Record<string, "pending" | "accepted" | "dismissed">
  >({});

  const adjusting = satStep === "adjust";
  const OT_HOURS = 8;
  const dayHours = (i: number) => load[i].hours + (load[i].overtime ? OT_HOURS : 0);

  // Edit any numeric workload field for a day directly in the table.
  const setField = (
    i: number,
    key: "operations" | "orders" | "units",
    value: number
  ) =>
    setLoad((prev) =>
      prev.map((d, idx) =>
        idx === i ? { ...d, [key]: Math.max(0, Math.round(value) || 0) } : d
      )
    );
  const toggleOt = (i: number) =>
    setLoad((prev) =>
      prev.map((d, idx) => (idx === i ? { ...d, overtime: !d.overtime } : d))
    );
  const setRec = (
    title: string,
    status: "pending" | "accepted" | "dismissed"
  ) => setRecStatus((prev) => ({ ...prev, [title]: status }));

  const saturday = useMemo(() => upcomingSaturday(today), [today]);
  const days = useMemo(() => nextWeekDays(saturday), [saturday]);
  const weekStart = days[0];
  const weekEnd = days[days.length - 1];

  const totals = load.reduce(
    (acc, d, i) => ({
      operations: acc.operations + d.operations,
      orders: acc.orders + d.orders,
      units: acc.units + d.units,
      hours: acc.hours + dayHours(i),
    }),
    { operations: 0, orders: 0, units: 0, hours: 0 }
  );
  // Original plan totals, so edits show as a delta versus the baseline plan.
  const baseTotals = MOCK_LOAD.reduce(
    (acc, d) => ({
      operations: acc.operations + d.operations,
      orders: acc.orders + d.orders,
      units: acc.units + d.units,
    }),
    { operations: 0, orders: 0, units: 0 }
  );
  const deltaTag = (cur: number, base: number) => {
    const d = cur - base;
    if (d === 0) return null;
    return (
      <span className={`kpi-delta ${d > 0 ? "up" : "down"}`}>
        {d > 0 ? "+" : ""}
        {d} vs plan
      </span>
    );
  };
  const maxOps = Math.max(...load.map((d) => d.operations), 1);

  if (!open) return null;

  const close = () => {
    setEarlyStep("idle");
    setSatStep("idle");
    setLoad(MOCK_LOAD.map((d) => ({ ...d, overtime: false })));
    setRecStatus({});
    onClose();
  };

  return (
    <div className="modal-overlay" onClick={close}>
      <div
        className="modal-card nextweek-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Next week plan"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <div>
            <h2>Next Week Plan</h2>
            <p className="subtitle">
              Week {iso(weekStart)} → {iso(weekEnd)} · published every Saturday
            </p>
          </div>
          <button className="icon-btn" aria-label="Close" onClick={close}>
            ✕
          </button>
        </div>

        {/* Preview toggle — lets you see both states of the interface. */}
        <div className="nextweek-toggle">
          <span className="muted">Preview:</span>
          <button
            className={view === "locked" ? "seg active" : "seg"}
            onClick={() => {
              setEarlyStep("idle");
              setSatStep("idle");
              setView("locked");
            }}
          >
            Before Saturday
          </button>
          <button
            className={view === "saturday" ? "seg active" : "seg"}
            onClick={() => {
              setEarlyStep("idle");
              setSatStep("idle");
              setView("saturday");
            }}
          >
            Saturday update
          </button>
          <button
            className={view === "no-data" ? "seg active" : "seg"}
            onClick={() => {
              setEarlyStep("idle");
              setSatStep("idle");
              setView("no-data");
            }}
          >
            Not enough data
          </button>
        </div>

        {view === "locked" ? (
          <div className="nextweek-body">
            <div className="cadence-banner">
              <strong>Next-week plan refreshes every Saturday.</strong> The plan
              for {iso(weekStart)} → {iso(weekEnd)} will be generated
              automatically on <strong>Sat {iso(saturday)}</strong>.
            </div>
            <p className="muted">
              Generating early uses a partial forecast and may change once the
              week closes on Saturday. You can request an early draft for review,
              or wait for the automatic Saturday update.
            </p>

            <div className="nextweek-section">
              <span className="section-label">
                Early recommendations (preview)
              </span>
              <ul className="rec-list">
                {MOCK_RECS.map((r) => (
                  <li key={r.title} className="rec-item">
                    <div className="rec-item-head">
                      <span className="rec-title">{r.title}</span>
                      <span
                        className={`badge ${
                          r.feasibility === "FEASIBLE" ? "feas-ok" : "feas-approve"
                        }`}
                      >
                        {r.feasibility === "FEASIBLE"
                          ? "feasible"
                          : "needs approval"}
                      </span>
                    </div>
                    <p className="rec-detail">{r.detail}</p>
                  </li>
                ))}
              </ul>
            </div>

            <div className="modal-actions">
              <button
                className="primary"
                onClick={() => setEarlyStep("confirm")}
                disabled={earlyStep !== "idle"}
              >
                Request early draft
              </button>
              <button onClick={close}>Close</button>
            </div>

            {earlyStep === "confirm" && (
              <div className="cadence-banner due">
                <strong>The next-week plan updates automatically every Saturday.</strong>{" "}
                An early draft uses a partial forecast and may change after Sat{" "}
                {iso(saturday)}. Generate an early draft for review anyway?
                <div className="modal-actions">
                  <button
                    className="primary"
                    onClick={() => setEarlyStep("done")}
                  >
                    Approve early draft
                  </button>
                  <button onClick={() => setEarlyStep("idle")}>Cancel</button>
                </div>
              </div>
            )}

            {earlyStep === "done" && (
              <div className="cadence-banner">
                <strong>Early draft requested.</strong> A provisional plan for{" "}
                {iso(weekStart)} → {iso(weekEnd)} will be prepared for review. It
                will be replaced by the confirmed plan on Sat {iso(saturday)}.
              </div>
            )}

            <p className="muted mock-note">
              Interface preview — generation isn't wired to the backend yet.
            </p>
          </div>
        ) : view === "no-data" ? (
          <div className="nextweek-body">
            <div className="nodata-hero">
              <span className="nodata-icon" aria-hidden="true">
                ⚠
              </span>
              <h3>Not enough data for next week</h3>
              <p className="muted">
                We can't build the plan for {iso(weekStart)} → {iso(weekEnd)}{" "}
                yet. A confirmed weekly dataset — open orders with due dates,
                machine availability and material stock — isn't complete for the
                coming week.
              </p>
            </div>

            <div className="nextweek-section">
              <span className="section-label">What's missing</span>
              <ul className="nodata-list">
                <li>No production orders released for the next week.</li>
                <li>Machine availability calendar not published past Saturday.</li>
                <li>Material stock snapshot is stale (older than this week).</li>
              </ul>
            </div>

            <div className="cadence-banner">
              <strong>The plan will generate automatically once data is
              available.</strong>{" "}
              Next attempt: Sat {iso(saturday)}. You can retry after loading the
              missing data.
            </div>

            <div className="modal-actions">
              <button className="primary" disabled>
                Retry generation
              </button>
              <button onClick={close}>Close</button>
            </div>
            <p className="muted mock-note">
              Interface preview — this popup appears when next week's dataset is
              incomplete.
            </p>
          </div>
        ) : (
          <div className="nextweek-body">
            <div className="cadence-banner due">
              <strong>Weekly plan update ready.</strong> It's Saturday — review
              next week ({iso(weekStart)} → {iso(weekEnd)}) and approve to
              publish.
            </div>

            <div className="kpi-grid">
              <div className="kpi-card tone-neutral">
                <div className="kpi-value">{totals.units}</div>
                <div className="kpi-label">Units to produce</div>
                {adjusting && deltaTag(totals.units, baseTotals.units)}
              </div>
              <div className="kpi-card tone-neutral">
                <div className="kpi-value">{totals.orders}</div>
                <div className="kpi-label">Orders to complete</div>
                {adjusting && deltaTag(totals.orders, baseTotals.orders)}
              </div>
              <div className="kpi-card tone-neutral">
                <div className="kpi-value">{totals.operations}</div>
                <div className="kpi-label">Operations</div>
                {adjusting && deltaTag(totals.operations, baseTotals.operations)}
              </div>
              <div className="kpi-card tone-neutral">
                <div className="kpi-value">{totals.hours}h</div>
                <div className="kpi-label">Work hours</div>
              </div>
            </div>

            {adjusting && (
              <div className="cadence-banner">
                <strong>Adjust mode.</strong> Type new values for operations,
                orders or units on any day — shift more onto one day and less
                onto another. Toggle overtime, accept or dismiss recommendations.
                Totals update live and show the change versus the original plan.
              </div>
            )}

            <div className="nextweek-section">
              <span className="section-label">Per-day workload</span>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Day</th>
                    <th>Target workload</th>
                    <th>Operations</th>
                    <th>Orders due</th>
                    <th>Units</th>
                    <th>Hours</th>
                    {adjusting && <th>Overtime</th>}
                  </tr>
                </thead>
                <tbody>
                  {days.map((d, i) => (
                    <tr key={iso(d)}>
                      <td>
                        <strong>{WEEKDAYS[i]}</strong> {iso(d).slice(5)}
                      </td>
                      <td>
                        <div className="bar-track">
                          <div
                            className="bar-fill plan"
                            style={{
                              width: `${(load[i].operations / maxOps) * 100}%`,
                            }}
                          />
                        </div>
                      </td>
                      <td>
                        {adjusting ? (
                          <input
                            type="number"
                            min={0}
                            className="cell-input"
                            value={load[i].operations}
                            onChange={(e) =>
                              setField(i, "operations", e.target.valueAsNumber)
                            }
                          />
                        ) : (
                          load[i].operations
                        )}
                      </td>
                      <td>
                        {adjusting ? (
                          <input
                            type="number"
                            min={0}
                            className="cell-input"
                            value={load[i].orders}
                            onChange={(e) =>
                              setField(i, "orders", e.target.valueAsNumber)
                            }
                          />
                        ) : (
                          load[i].orders
                        )}
                      </td>
                      <td>
                        {adjusting ? (
                          <input
                            type="number"
                            min={0}
                            className="cell-input cell-input-wide"
                            value={load[i].units}
                            onChange={(e) =>
                              setField(i, "units", e.target.valueAsNumber)
                            }
                          />
                        ) : (
                          load[i].units
                        )}
                      </td>
                      <td>
                        {dayHours(i)}h
                        {load[i].overtime && (
                          <span className="badge feas-approve ot-tag">+OT</span>
                        )}
                      </td>
                      {adjusting && (
                        <td>
                          <label className="ot-toggle">
                            <input
                              type="checkbox"
                              checked={load[i].overtime}
                              onChange={() => toggleOt(i)}
                            />
                            <span>+{OT_HOURS}h</span>
                          </label>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="nextweek-section">
              <span className="section-label">
                Recommendations to review
                {adjusting && (
                  <span className="muted">
                    {" "}
                    ·{" "}
                    {
                      MOCK_RECS.filter(
                        (r) => recStatus[r.title] === "accepted"
                      ).length
                    }{" "}
                    accepted
                  </span>
                )}
              </span>
              <ul className="rec-list">
                {MOCK_RECS.map((r) => {
                  const status = recStatus[r.title] ?? "pending";
                  return (
                    <li
                      key={r.title}
                      className={`rec-item rec-${status}`}
                    >
                      <div className="rec-item-head">
                        <span className="rec-title">{r.title}</span>
                        <span className="rec-item-badges">
                          {status === "accepted" && (
                            <span className="badge feas-ok">accepted</span>
                          )}
                          {status === "dismissed" && (
                            <span className="badge feas-no">dismissed</span>
                          )}
                          <span
                            className={`badge ${
                              r.feasibility === "FEASIBLE"
                                ? "feas-ok"
                                : "feas-approve"
                            }`}
                          >
                            {r.feasibility === "FEASIBLE"
                              ? "feasible"
                              : "needs approval"}
                          </span>
                        </span>
                      </div>
                      <p className="rec-detail">{r.detail}</p>
                      {adjusting && (
                        <div className="rec-actions">
                          <button
                            type="button"
                            className={status === "accepted" ? "primary" : ""}
                            onClick={() =>
                              setRec(
                                r.title,
                                status === "accepted" ? "pending" : "accepted"
                              )
                            }
                          >
                            {status === "accepted" ? "Accepted ✓" : "Accept"}
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              setRec(
                                r.title,
                                status === "dismissed" ? "pending" : "dismissed"
                              )
                            }
                          >
                            {status === "dismissed" ? "Dismissed" : "Dismiss"}
                          </button>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>

            <div className="modal-actions">
              {adjusting ? (
                <>
                  <button
                    className="primary"
                    onClick={() => setSatStep("confirm")}
                  >
                    Done adjusting
                  </button>
                  <button onClick={() => setSatStep("idle")}>
                    Back to review
                  </button>
                </>
              ) : (
                <>
                  <button
                    className="primary"
                    onClick={() => setSatStep("confirm")}
                    disabled={satStep === "published"}
                  >
                    Approve &amp; publish
                  </button>
                  <button
                    onClick={() => setSatStep("adjust")}
                    disabled={satStep === "published"}
                  >
                    Adjust
                  </button>
                  <button onClick={close}>Cancel</button>
                </>
              )}
            </div>

            {satStep === "confirm" && (
              <div className="cadence-banner due">
                <strong>Publish next week's plan?</strong> This commits the plan
                for {iso(weekStart)} → {iso(weekEnd)} and applies the accepted
                recommendations. Planners will see it as the active weekly plan.
                <div className="modal-actions">
                  <button
                    className="primary"
                    onClick={() => setSatStep("published")}
                  >
                    Confirm publish
                  </button>
                  <button onClick={() => setSatStep("idle")}>Cancel</button>
                </div>
              </div>
            )}

            {satStep === "published" && (
              <div className="cadence-banner">
                <strong>Next week published.</strong> The plan for{" "}
                {iso(weekStart)} → {iso(weekEnd)} is now the active weekly plan.
              </div>
            )}

            <p className="muted mock-note">
              Interface preview — sample data; generation and publishing aren't
              wired to the backend yet.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
