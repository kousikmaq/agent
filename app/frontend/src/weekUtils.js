// Week-range helpers. A week_start is always a Monday (from the backend).
// We show the full Mon–Sun span so "this week" reads as a real date range,
// not just a single end date.

function parse(weekStart) {
  return new Date(weekStart + 'T00:00:00')
}

// "Jul 6 – Jul 12"
export function weekRange(weekStart) {
  if (!weekStart) return ''
  const start = parse(weekStart)
  const end = new Date(start)
  end.setDate(end.getDate() + 6)
  const fmt = d => d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  return `${fmt(start)} \u2013 ${fmt(end)}`
}

// "Jul 6 – Jul 12, 2026"
export function weekRangeLong(weekStart) {
  if (!weekStart) return ''
  const start = parse(weekStart)
  const end = new Date(start)
  end.setDate(end.getDate() + 6)
  const fmt = d => d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  return `${fmt(start)} \u2013 ${fmt(end)}, ${end.getFullYear()}`
}
