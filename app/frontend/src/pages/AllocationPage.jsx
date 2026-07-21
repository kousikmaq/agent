import React, { useEffect, useState } from 'react'
import { getOverview, getAllocation } from '../api'

function Bar({ pct }) {
  const over = pct > 100
  const w = Math.min(pct, 150) / 150 * 100
  return (
    <div className="mbar">
      <div className="mbar-fill" style={{ width: `${w}%`, background: over ? '#c0392b' : '#2e7d46' }} />
      <span className="mbar-txt">{pct}%</span>
    </div>
  )
}

export default function AllocationPage({ week, setWeek }) {
  const [weeks, setWeeks] = useState(null)
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

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

  useEffect(() => {
    if (!week) return
    setData(null)
    getAllocation(week).then(setData).catch(e => setErr(String(e)))
  }, [week])

  if (err) return <div className="err">Cannot reach the backend ({err}). Start it on port 8001.</div>
  if (!weeks) return <div className="loading">Loading…</div>

  const statusClass = s => (s === 'OVERLOADED' ? 'over' : s === 'TIGHT' ? 'tight' : 'ok')

  return (
    <>
      <div className="pagehead">
        <h1>Resource Allocation</h1>
        <p>Move work off overloaded machines onto qualified idle backups, and see the before/after balance.</p>
      </div>

      <div className="weeks">
        {weeks.map(w => (
          <button key={w.week_start}
            className={`weekchip ${w.week_start === week ? 'active' : ''}`}
            onClick={() => setWeek(w.week_start)}>
            <span className={`dot ${statusClass(w.status)}`} />
            {w.week_start.slice(5)}
          </button>
        ))}
      </div>

      {!data && <div className="loading">Balancing…</div>}

      {data && (
        <>
          <div className={`info ${data.overloads_after ? 'amber' : ''}`}>
            <b>{data.summary}</b>
          </div>

          <div className="grid cards3">
            <div className="card stat">
              <div className="label">Hours moved</div>
              <div className="value navy">{data.hours_moved}</div>
              <div className="sub">to idle backup machines</div>
            </div>
            <div className="card stat">
              <div className="label">Overloads before</div>
              <div className="value red">{data.overloads_before}</div>
            </div>
            <div className="card stat">
              <div className="label">Overloads after</div>
              <div className={`value ${data.overloads_after ? 'amber' : 'green'}`}>{data.overloads_after}</div>
              <div className="sub">{data.overloads_before - data.overloads_after} cleared by reallocation</div>
            </div>
          </div>

          <div className="grid two-even">
            <div className="card">
              <h3>Recommended moves</h3>
              {data.moves.length === 0
                ? <p className="muted">No moves possible — overloaded machines have no alternate, so use overtime, outsourcing or deferral.</p>
                : data.moves.map((m, i) => (
                  <div className="rec" key={i}>
                    <span className="rec-ico">⇄</span>
                    <div>
                      <div className="rec-t">{m.from_wc} → {m.to_wc} · {m.hours}h</div>
                      <div className="rec-d">{m.note}</div>
                    </div>
                  </div>
                ))}
            </div>

            <div className="card">
              <h3>Before → after (affected machines)</h3>
              {data.states.length === 0 && <p className="muted">Nothing overloaded this week.</p>}
              {data.states.map(s => (
                <div className="baline" key={s.work_center}>
                  <div className="ba-name">{s.work_center}</div>
                  <div className="ba-bars">
                    <div className="ba-row"><span className="ba-lbl">before</span><Bar pct={s.util_before} /></div>
                    <div className="ba-row"><span className="ba-lbl">after</span><Bar pct={s.util_after} /></div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  )
}
