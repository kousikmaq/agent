import React, { useState } from 'react'

// Collapsible "How this works" explainer for people new to manufacturing.
// Closed by default so it never clutters the page; one click reveals plain-language help.
export default function HelpBox({ title = 'How to read this page', children }) {
  const [open, setOpen] = useState(false)
  return (
    <div className={`helpbox ${open ? 'open' : ''}`}>
      <button className="helpbox-head" onClick={() => setOpen(o => !o)}>
        <span className="helpbox-q">?</span>
        {title}
        <span className="helpbox-caret">{open ? '▲' : '▾'}</span>
      </button>
      {open && <div className="helpbox-body">{children}</div>}
    </div>
  )
}
