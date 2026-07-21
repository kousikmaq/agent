import React, { useEffect, useState } from 'react'
import { getOverview, getAllocation } from '../api'
import WeekBar from '../components/WeekBar'
import HelpBox from '../components/HelpBox'
import InfoTip from '../components/InfoTip'

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

export default function AllocationPage({ week, setWeek, navigate }) {
  const [weeks, setWeeks] = useState(null)
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [openMove, setOpenMove] = useState(null)

  useEffect(() => {
    getOverview()
      .then(ov => {
        setWeeks(ov.weeks)
        if (!week) {
          const current = [...ov.weeks].sort((a, b) => a.week_start.localeCompare(b.week_start))[0]
          setWeek(current.week_start)
        }
      })
      .catch(e => setErr(String(e)))
  }, [])

  useEffect(() => {
    if (!week) return
    setData(null); setOpenMove(null)
    getAllocation(week).then(setData).catch(e => setErr(String(e)))
  }, [week])

  if (err) return <div className="err">Cannot reach the backend ({err}). Start it on port 8000.</div>
  if (!weeks) return <div className="loading">Loading…</div>

  return (
    <>
      <div className="pagehead">
        <h1>Resource Allocation</h1>
        <p>Move work off overloaded machines onto qualified idle backups — and see the before/after balance.</p>
      </div>

      <HelpBox title="New here? What 'reallocation' means">
        <ul>
          <li>Some operations can run on more than one machine (a primary and a <b>backup / alternate</b>).</li>
          <li>When the primary is overloaded, we shift hours to a backup that still has spare time — <b>without pushing the backup over 100%</b>.</li>
          <li>The <b>before → after</b> bars show each affected machine's load dropping after the move.</li>
          <li>If a machine has no backup, reallocation can't help — you'd use overtime, outsourcing, or move orders to another week.</li>
        </ul>
        Click any recommended move to see the details.
      </HelpBox>

      <WeekBar weeks={weeks} week={week} setWeek={setWeek} />

      {!data && <div className="loading">Balancing…</div>}

      {data && (
        <>
          <div className={`info ${data.overloads_after ? 'amber' : ''}`}>
            <b>{data.summary}</b>
          </div>

          <div className="grid cards3">
            <div className="card stat">
              <div className="label">Hours moved <InfoTip text="Total machine-hours shifted from overloaded machines to their backups." /></div>
              <div className="value navy">{data.hours_moved}</div>
              <div className="sub">to idle backup machines</div>
            </div>
            <div className="card stat">
              <div className="label">Overloads before</div>
              <div className="value red">{data.overloads_before}</div>
              <div className="sub">machines over 100%</div>
            </div>
            <div className="card stat">
              <div className="label">Overloads after</div>
              <div className={`value ${data.overloads_after ? 'amber' : 'green'}`}>{data.overloads_after}</div>
              <div className="sub">{data.overloads_before - data.overloads_after} cleared by reallocation</div>
            </div>
          </div>

          <div className="grid two-even">
            <div className="card">
              <h3>Recommended moves <InfoTip text="Each move offloads hours from an overloaded machine to a qualified backup with spare capacity." /></h3>
              {data.moves.length === 0
                ? <p className="muted">No moves possible — overloaded machines have no alternate, so use overtime, outsourcing or deferral.</p>
                : data.moves.map((m, i) => {
                  const open = openMove === i
                  return (
                    <div key={i}>
                      <div className="rec" style={{ cursor: 'pointer' }} onClick={() => setOpenMove(open ? null : i)}>
                        <span className="rec-ico">⇄</span>
                        <div>
                          <div className="rec-t">{m.from_wc} → {m.to_wc} · {m.hours}h {open ? '▲' : '▾'}</div>
                          <div className="rec-d">{m.note}</div>
                        </div>
                      </div>
                      {open && (
                        <div className="dp-inner">
                          <div className="dp-grid">
                            <div className="dp-cell"><div className="k">From (overloaded)</div><div className="v">{m.from_wc}</div></div>
                            <div className="dp-cell"><div className="k">To (backup)</div><div className="v">{m.to_wc}</div></div>
                            <div className="dp-cell"><div className="k">Hours moved</div><div className="v">{m.hours} h</div></div>
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
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

          <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
            <button className="btn-ghost" onClick={() => navigate('capacity', week)}>← Back to capacity</button>
            <button className="btn-ghost" onClick={() => navigate('schedule', week)}>Build a machine schedule →</button>
          </div>
        </>
      )}
    </>
  )
}
