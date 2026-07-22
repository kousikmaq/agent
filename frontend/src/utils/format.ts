/** Small formatting helpers shared across components. */

/** Format an ISO datetime as "MM-DD HH:MM". */
export function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(
    d.getMinutes()
  )}`;
}

/** Format an ISO datetime as "HH:MM". */
export function fmtTime(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Render a 0-1 ratio as a percentage string. */
export function fmtPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

/** Render a USD amount as a compact currency string (e.g. $12,340). */
export function fmtCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

/** Render minutes as "Xd Yh Zm". */
export function fmtMinutes(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "—";
  const m = Math.round(minutes);
  const days = Math.floor(m / 1440);
  const hours = Math.floor((m % 1440) / 60);
  const mins = m % 60;
  const parts: string[] = [];
  if (days) parts.push(`${days}d`);
  if (hours) parts.push(`${hours}h`);
  parts.push(`${mins}m`);
  return parts.join(" ");
}

/** Minutes between two ISO datetimes. */
export function durationMinutes(startIso: string, endIso: string): number {
  return Math.round(
    (new Date(endIso).getTime() - new Date(startIso).getTime()) / 60000
  );
}

/** Today's date as an ISO date string (YYYY-MM-DD), local time. */
export function todayIso(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Keep only dates on or before today (future days belong to next week). */
export function datesUpToToday(dates: string[]): string[] {
  const today = todayIso();
  return dates.filter((d) => d <= today);
}

/** Saturday (end) of the current Monday–Saturday working week, ISO date. */
export function endOfWeekIso(): string {
  const d = new Date();
  const js = d.getDay(); // Sun=0..Sat=6
  const toMonday = js === 0 ? -6 : 1 - js;
  const sat = new Date(d);
  sat.setDate(d.getDate() + toMonday + 5); // Monday + 5 = Saturday
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${sat.getFullYear()}-${pad(sat.getMonth() + 1)}-${pad(sat.getDate())}`;
}

/** Keep dates up to the end of the current week (excludes next week). */
export function datesThisWeekOrEarlier(dates: string[]): string[] {
  const end = endOfWeekIso();
  return dates.filter((d) => d <= end);
}
