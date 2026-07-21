import React, { useEffect, useState } from 'react'
import { getOverview, getWeek } from '../api'
import CapacityChart from '../components/CapacityChart'
import BottleneckChart from '../components/BottleneckChart'
import BatchingCard from '../components/BatchingCard'
import RecommendationsCard from '../components/RecommendationsCard'
import OrdersTable from '../components/OrdersTable'
import WeekBar from '../components/WeekBar'
import HelpBox from '../components/HelpBox'
import InfoTip from '../components/InfoTip'

function MachineRow({ r, open, onToggle }) {
  const over = r.utilization_pct > 100
  const tight = !over && r.utilization_pct >= 85
  const color = over ? '#c0392b' : tight ? '#b47a1e' : '#2e7d46'
  const width = Math.min(r.utilization_pct, 150) / 150 * 100
  const hundred = 100 / 150 * 100
  return (
    <>
      <div className="mc-row" onClick={onToggle}>
        <div className="mc-name">
          <b>{r.work_center}</b> · {r.name}<br />
          <span className="mc-dept">{r.department}</span>
        </div>
        <div className="mc-bar">
          <div className="mc-bar-fill" style={{ width: `${width}%`, background: color }} />
          <div className="mc-100" style={{ left: `${hundred}%` }} title="100% = full capacity" />
        </div>
        <div className="mc-pct" style={{ color }}>{r.utilization_pct}%</div>
      </div>
      {open && (
        <div className="dp-inner" style={{ paddingLeft: 0 }}>
          <div className="dp-grid">
            <div className="dp-cell"><div className="k">Work needed</div><div className="v">{r.required_hours} h</div></div>
            <div className="dp-cell"><div className="k">Capacity available</div><div className="v">{r.available_hours} h</div></div>
            <div className="dp-cell"><div className="k">Over capacity by</div><div className="v" style={{ color: over ? '#c0392b' : '#2e7d46' }}>{r.overload_hours} h</div></div>
            <div className="dp-cell"><div className="k">Status</div><div className="v" style={{ color }}>{over ? 'Overloaded' : tight ? 'Tight' : 'OK'}</div></div>
          </div>
          <p className="muted" style={{ marginTop: 8 }}>
            {over
              ? `This machine has ${r.overload_hours}h more work than it can do this week. Offload some work to a backup machine, add a shift, or move less-urgent orders to another week.`
              : tight
                ? 'Almost full — little slack. A single extra order could push it over.'
                : `Comfortable — ${(r.available_hours - r.required_hours).toFixed(1)}h of spare capacity.`}
          </p>
        </div>
      )}
    </>
  )
}

export default function CapacityPage({ week, setWeek, navigate }) {
  const [weeks, setWeeks] = useState(null)
  const [load, setLoad] = useState(null)
  const [err, setErr] = useState(null)
  const [openMc, setOpenMc] = useState(null)
  const [onlyBusy, setOnlyBusy] = useState(false)

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
    setLoad(null); setOpenMc(null)
    getWeek(week).then(setLoad).catch(e => setErr(String(e)))
  }, [week])

  if (err) return <div className="err">Cannot reach the backend ({err}). Start it on port 8000.</div>
  if (!weeks) return <div className="loading">Loading…</div>

  const bn = load && load.bottleneck
  const rows = load ? [...load.resources] : []
  const shown = onlyBusy ? rows.filter(r => r.utilization_pct >= 85) : rows

  return (
    <>
      <div className="pagehead">
        <h1>Capacity Analysis</h1>
        <p>How busy each machine is in the week you pick — and the one machine that limits everything (the bottleneck).</p>
      </div>

      <HelpBox title="New here? How capacity analysis works">
        <ul>
          <li><b>Capacity</b> = how many hours a machine can run in the week (shifts × hours × days).</li>
          <li><b>Load / utilisation</b> = the work booked onto it ÷ its capacity. <b>Over 100%</b> means more work than time — something will be late.</li>
          <li><b>Bottleneck</b> = the single busiest machine. It sets the pace for the whole factory, so it is where you act first.</li>
          <li><b>Batching</b> = running same-part orders back-to-back so you set the machine up once instead of many times, freeing hours.</li>
        </ul>
        Click any machine below to drill into its exact hours. Use the week buttons to compare weeks.
      </HelpBox>

      <WeekBar weeks={weeks} week={week} setWeek={setWeek} />

      {!load && <div className="loading">Analysing the week…</div>}

      {load && (
        <>
          {/* the headline: is there a bottleneck this week? made unambiguous */}
          {!bn ? (
            <div className="callout green"><span className="co-ico">✅</span>
              <div><div className="co-t">No orders due this week</div><div className="co-d">Nothing to schedule.</div></div>
            </div>
          ) : (() => {
            const tier = bn.utilization_pct > 100 ? 'over' : bn.utilization_pct >= 85 ? 'tight' : 'clear'
            const cfg = {
              over: { cls: 'red', ico: '⛔', title: `Bottleneck present — ${bn.work_center}`,
                      desc: `${bn.work_center} is over capacity by ${bn.overload_hours}h. It caps this week's output, so act on it first.`,
                      color: '#c0392b', lbl: `${bn.overload_hours}h over capacity` },
              tight: { cls: '', ico: '⚠️', title: `Near-bottleneck — ${bn.work_center} is tight`,
                       desc: `${bn.work_center} is close to full. No overload yet, but little slack — watch it.`,
                       color: '#b47a1e', lbl: 'running tight' },
              clear: { cls: 'green', ico: '✅', title: 'No bottleneck this week',
                       desc: `Every machine has spare capacity. Busiest is ${bn.work_center} at ${bn.utilization_pct}%.`,
                       color: '#2e7d46', lbl: 'within capacity' },
            }[tier]
            return (
              <div className={`callout ${cfg.cls}`} style={tier === 'tight' ? { background: '#fcf3e3', borderColor: '#efe0c0' } : undefined}>
                <span className="co-ico">{cfg.ico}</span>
                <div>
                  <div className="co-t">
                    {cfg.title}
                    <InfoTip text="A bottleneck is a machine loaded at or over 100% that limits the whole week's output. If the busiest machine has spare capacity, there is no bottleneck this week." />
                  </div>
                  <div className="co-d">{cfg.desc}</div>
                </div>
                <div className="co-metric">
                  <div className="m-val" style={{ color: cfg.color }}>{bn.utilization_pct}%</div>
                  <div className="m-lbl">{cfg.lbl}</div>
                </div>
              </div>
            )
          })()}

          {load.resources.length > 0 && (
            <div className="card">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                <h3 style={{ margin: 0 }}>
                  Machine load — click a machine to drill down
                  <InfoTip text="Each bar is one machine. The dark line marks 100% (full). Red = overloaded, amber = tight, green = comfortable." />
                </h3>
                <button className={`chipbtn ${onlyBusy ? 'on' : ''}`} onClick={() => setOnlyBusy(v => !v)}>
                  {onlyBusy ? 'Showing busy only' : 'Show only busy (≥85%)'}
                </button>
              </div>
              <div style={{ marginTop: 8 }}>
                {shown.map(r => (
                  <MachineRow key={r.work_center} r={r} open={openMc === r.work_center}
                    onToggle={() => setOpenMc(openMc === r.work_center ? null : r.work_center)} />
                ))}
                {shown.length === 0 && <p className="muted">No machines match this filter.</p>}
              </div>
            </div>
          )}

          <div className="grid two-even">
            <CapacityChart resources={load.resources} />
            <BottleneckChart resources={load.resources} />
          </div>

          <div className="grid two-even">
            <RecommendationsCard recommendations={load.recommendations} />
            <BatchingCard batching={load.batching} />
          </div>

          {load.recommendations.length > 0 && (
            <div style={{ display: 'flex', gap: 8, margin: '2px 0 14px' }}>
              <button className="btn-ghost" onClick={() => navigate('allocation', week)}>See the reallocation plan →</button>
              <button className="btn-ghost" onClick={() => navigate('schedule', week)}>Build a machine schedule →</button>
            </div>
          )}

          <OrdersTable orders={load.orders} />
        </>
      )}
    </>
  )
}
