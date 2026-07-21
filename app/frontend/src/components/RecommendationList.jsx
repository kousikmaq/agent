import React from 'react'

// A consistent "Recommended actions" panel. Items are derived from the real
// numbers already on the page (no invented figures), each optionally with a
// button that jumps to the page where you act on it.
export default function RecommendationList({ title = 'Recommended actions', items }) {
  if (!items || items.length === 0) return null
  return (
    <div className="card">
      <h3>{title}</h3>
      {items.map((it, i) => (
        <div className="rec" key={i}>
          <span className="rec-ico">{it.icon || '→'}</span>
          <div style={{ flex: 1 }}>
            <div className="rec-t">{it.title}</div>
            {it.detail && <div className="rec-d">{it.detail}</div>}
          </div>
          {it.cta && <button className="btn-ghost" style={{ alignSelf: 'center', whiteSpace: 'nowrap' }} onClick={it.onClick}>{it.cta}</button>}
        </div>
      ))}
    </div>
  )
}
