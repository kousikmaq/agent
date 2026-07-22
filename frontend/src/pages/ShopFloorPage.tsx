import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { RiskReport, ShopFloorStatus } from "../types/api";
import { ShopFloorBoard } from "../components/ShopFloorBoard";
import { ReportEmailButton } from "../components/EmailButton";
import { datesUpToToday } from "../utils/format";

/** Shop-floor monitoring page: live status of machines, workers, orders, materials. */
export function ShopFloorPage() {
  const [dates, setDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [status, setStatus] = useState<ShopFloorStatus | null>(null);
  const [risks, setRisks] = useState<RiskReport | null>(null);
  const [message, setMessage] = useState<string>("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .listDates()
      .then((res) => {
        // Shop floor is live status up to today only.
        const dates = datesUpToToday(res.dates);
        setDates(dates);
        if (dates.length > 0) setSelectedDate(dates[dates.length - 1]);
      })
      .catch(() => setMessage("Failed to load dates."));
  }, []);

  const load = useCallback(async (date: string) => {
    setBusy(true);
    try {
      setStatus(await api.getShopFloor(date));
      setMessage("");
    } catch {
      setStatus(null);
      setMessage("No snapshot for this day yet — generate it on the Planning page.");
    } finally {
      setBusy(false);
    }
    try {
      setRisks(await api.getRisks(date));
    } catch {
      setRisks(null);
    }
  }, []);

  useEffect(() => {
    if (selectedDate) load(selectedDate);
  }, [selectedDate, load]);

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>Live Operations</h1>
          <p className="subtitle">Live status up to {selectedDate || "—"}</p>
        </div>
        <div className="controls">
          <select
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            disabled={dates.length === 0}
          >
            {dates.length === 0 && <option>No days</option>}
            {dates.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          <button onClick={() => selectedDate && load(selectedDate)} disabled={busy}>
            Refresh
          </button>
        </div>
      </header>

      {message && <div className="status-bar">{message}</div>}

      <section className="tab-panel">
        {selectedDate && status && (
          <div className="tab-actionbar">
            <ReportEmailButton
              date={selectedDate}
              reportType="live_ops"
              label="Email status"
            />
          </div>
        )}
        {status ? (
          <ShopFloorBoard status={status} risks={risks} />
        ) : (
          <p className="empty">Select a day to see shop-floor status.</p>
        )}
      </section>
    </div>
  );
}
