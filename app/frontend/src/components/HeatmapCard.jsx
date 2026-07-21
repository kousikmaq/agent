import React from 'react'

// Colour for a utilisation value (the classic capacity heatmap scale).
function cellStyle(util) {
  let bg = '#eaf6ec', fg = '#2e7d46'            // light (idle)
  if (util >= 100) { bg = '#c0392b'; fg = '#fff' }        // overloaded
  else if (util >= 85) { bg = '#e08a2e'; fg = '#fff' }    // tight
  else if (util >= 60) { bg = '#bfe3c8'; fg = '#14432a' } // moderate
  return { background: bg, color: fg }
}

export default function HeatmapCard({ heatmap, onSelectWeek }) {
  const { weeks, rows } = heatmap
  const cols = `150px repeat(${weeks.length}, minmax(30px, 1fr))`

  return (
    <div className="card">
      <h3>Capacity heatmap — every machine, every week</h3>
      <div style={{ overflowX: 'auto' }}>
        <div className="heat" style={{ gridTemplateColumns: cols }}>
          <div className="heat-corner" />
          {weeks.map(w => <div key={w} className="heat-colh">{w.slice(5)}</div>)}

          {rows.map(row => (
            <React.Fragment key={row.work_center}>
              <div className="heat-rowh" title={`${row.name} · ${row.department}`}>
                {row.work_center}
              </div>
              {row.cells.map(c => (
                <div
                  key={c.week_start}
                  className="heat-cell"
                  style={{ ...cellStyle(c.utilization_pct), cursor: 'pointer' }}
                  title={`${row.work_center} — week of ${c.week_start}: ${c.utilization_pct}% (${c.status})`}
                  onClick={() => onSelectWeek && onSelectWeek(c.week_start)}
                >
                  {Math.round(c.utilization_pct)}
                </div>
              ))}
            </React.Fragment>
          ))}
        </div>
      </div>
      <div className="legend">
        <span><i className="sw" style={{ background: '#eaf6ec' }} /> idle</span>
        <span><i className="sw" style={{ background: '#bfe3c8' }} /> 60–85%</span>
        <span><i className="sw" style={{ background: '#e08a2e' }} /> 85–100%</span>
        <span><i className="sw" style={{ background: '#c0392b' }} /> over 100%</span>
        <span className="muted">Click any cell to open that week.</span>
      </div>
    </div>
  )
}
