import React, { useEffect, useState } from 'react'
import { getOverview, getWeek } from '../api'
import CapacityChart from '../components/CapacityChart'
import BottleneckChart from '../components/BottleneckChart'
import BatchingCard from '../components/BatchingCard'
import RecommendationsCard from '../components/RecommendationsCard'
import OrdersTable from '../components/OrdersTable'

export default function CapacityPage({ week, setWeek }) {
  const [weeks, setWeeks] = useState(null)   // WeekSummary[] (for the chips)
  const [load, setLoad] = useState(null)     // WeekLoad (the selected week)
  const [err, setErr] = useState(null)

  // week chips + status colours come from the bulk overview
  useEffect(() => {
    getOverview()
      .then(ov => {
        setWeeks(ov.weeks)
        if (!week) {
          const worst = [...ov.weeks].sort((a, b) => b.bottleneck_util - a.bottleneck_util)[0]
          setWeek(worst.week_start)
        }
      })
      .catch(e => setErr(String(e)))
  }, [])

  // selected week detail
  useEffect(() => {
    if (!week) return
    setLoad(null)
    getWeek(week).then(setLoad).catch(e => setErr(String(e)))
  }, [week])

  if (err) return <div className="err">Cannot reach the backend ({err}). Start it on port 8001.</div>
  if (!weeks) return <div className="loading">Loading…</div>

  const statusClass = s => (s === 'OVERLOADED' ? 'over' : s === 'TIGHT' ? 'tight' : 'ok')

  return (
    <>
      <div className="pagehead">
        <h1>Capacity Analysis</h1>
        <p>Pick a week to see the load on every machine, the bottleneck, and the batching opportunity.</p>
      </div>

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

      {!load && <div className="loading">Loading week…</div>}

      {load && (
        <>
          <div className={`info ${load.bottleneck && load.bottleneck.utilization_pct > 100 ? 'amber' : ''}`}>
            <b>What to do:</b> {load.summary}
          </div>

          <div className="grid two-even">
            <CapacityChart resources={load.resources} />
            <BottleneckChart resources={load.resources} />
          </div>

          <div className="grid two-even">
            <RecommendationsCard recommendations={load.recommendations} />
            <BatchingCard batching={load.batching} />
          </div>

          <OrdersTable orders={load.orders} />
        </>
      )}
    </>
  )
}
