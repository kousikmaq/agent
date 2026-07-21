import React, { useState } from 'react'
import InfoTip from './InfoTip'
import { weekRange } from '../weekUtils'

const statusClass = s => (s === 'OVERLOADED' ? 'over' : s === 'TIGHT' ? 'tight' : 'ok')
const statusWord = s => (s === 'OVERLOADED' ? 'overloaded' : s === 'TIGHT' ? 'running tight' : 'comfortable')

export function relLabel(i) {
  if (i === 0) return 'This week'
  if (i === 1) return 'Next week'
  return `In ${i} weeks`
}

// Smart week selector shared by every week-based page.
// Defaults people to "this week" / "next week", with a one-click jump to the
// busiest week, and hides the full 16-week strip behind a toggle so the page
// is not overwhelming.
export default function WeekBar({ weeks, week, setWeek }) {
  const [showAll, setShowAll] = useState(false)
  if (!weeks || weeks.length === 0) return null

  const sorted = [...weeks].sort((a, b) => a.week_start.localeCompare(b.week_start))
  const current = sorted[0]
  const next = sorted[1]
  const busiest = [...sorted].sort((a, b) => b.bottleneck_util - a.bottleneck_util)[0]
  const idx = sorted.findIndex(w => w.week_start === week)
  const sel = idx >= 0 ? sorted[idx] : null

  const Quick = ({ w, label }) => w ? (
    <button className={`wq ${w.week_start === week ? 'active' : ''}`} onClick={() => setWeek(w.week_start)}>
      <span className={`dot ${statusClass(w.status)}`} />{label}
      <span className="wq-date">{w.week_start.slice(5)}</span>
    </button>
  ) : null

  return (
    <div className="weekbar">
      <div className="weekbar-top">
        <span className="weekbar-lbl">
          Week
          <InfoTip text="Your order book holds 16 weeks (about 4 months) of committed customer orders — that is the planning horizon. Pick any week to analyse it. 'This week' is the current planning week." />
        </span>
        <Quick w={current} label="This week" />
        <Quick w={next} label="Next week" />
        <button className={`wq busy ${busiest.week_start === week ? 'active' : ''}`}
          onClick={() => setWeek(busiest.week_start)} title="Jump to the most overloaded week">
          <span className="dot over" />Busiest week
          <span className="wq-date">{busiest.week_start.slice(5)}</span>
        </button>
        <button className="wq ghost" onClick={() => setShowAll(s => !s)}>
          {showAll ? 'Hide weeks' : 'All 16 weeks'} {showAll ? '▲' : '▾'}
        </button>
      </div>

      {sel && (
        <div className="weekbar-cur">
          Showing <b>{relLabel(idx)}</b> · <b>{weekRange(week)}</b> ·
          {' '}busiest machine at <b className={sel.bottleneck_util > 100 ? 'txt-red' : ''}>{sel.bottleneck_util}%</b>
          {' '}({statusWord(sel.status)})
        </div>
      )}

      {showAll && (
        <div className="weeks">
          {sorted.map((w, i) => (
            <button key={w.week_start}
              className={`weekchip ${w.week_start === week ? 'active' : ''}`}
              onClick={() => setWeek(w.week_start)}
              title={`${relLabel(i)} — ${statusWord(w.status)} (${w.bottleneck_util}%)`}>
              <span className={`dot ${statusClass(w.status)}`} />{w.week_start.slice(5)}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
