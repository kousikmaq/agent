import React from 'react'

const statusClass = s => (s === 'OVERLOADED' ? 'over' : s === 'TIGHT' ? 'tight' : 'ok')

// Shared week selector used across the week-based pages.
export default function WeekChips({ weeks, week, setWeek }) {
  return (
    <div className="weeks">
      {weeks.map(w => (
        <button
          key={w.week_start}
          className={`weekchip ${w.week_start === week ? 'active' : ''}`}
          onClick={() => setWeek(w.week_start)}
        >
          <span className={`dot ${statusClass(w.status)}`} />
          {w.week_start.slice(5)}
        </button>
      ))}
    </div>
  )
}
