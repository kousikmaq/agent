import React, { useState } from 'react'
import { askAgent } from '../api'

// Suggested questions are scoped to the tab the planner is on.
const SAMPLES_BY_PAGE = {
  dashboard: [
    'Which week is the most overloaded?',
    'How many weeks need attention?',
    'Can we commit to the whole order book?',
  ],
  capacity: [
    'What is the bottleneck this week?',
    'Which machines are over capacity?',
    'How much would batching save?',
  ],
  priority: [
    'Which orders should I run first?',
    'How many orders are at risk?',
    'Why is the top order urgent?',
  ],
  allocation: [
    'How can I offload the overloaded machines?',
    'How many hours can be moved to backups?',
    'Which overloads can reallocation clear?',
  ],
  schedule: [
    'Which orders are most urgent to schedule?',
    'What is the bottleneck for scheduling?',
    'How should I sequence this week?',
  ],
  risk: [
    'Which orders are likely to be late?',
    'Which components are short?',
    'What is causing the delay risk?',
  ],
  demand: [
    'Can we commit to the whole order book?',
    'Which departments are short on capacity?',
    'What is the total load vs capacity?',
  ],
  scenarios: [
    'Which scenario is best this week?',
    'Does adding a shift fix the overload?',
    'What happens if we defer orders?',
  ],
}
const DEFAULT_SAMPLES = SAMPLES_BY_PAGE.dashboard
const PAGE_LABEL = {
  dashboard: 'Dashboard', capacity: 'Capacity', priority: 'Prioritization',
  allocation: 'Allocation', schedule: 'Schedule', risk: 'Delay risk',
  demand: 'Demand', scenarios: 'Scenarios',
}

export default function AssistantWidget({ page }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [msgs, setMsgs] = useState([]) // {role:'me'|'bot', text, used_llm}

  const samples = SAMPLES_BY_PAGE[page] || DEFAULT_SAMPLES

  async function send(question) {
    const text = (question ?? q).trim()
    if (!text || busy) return
    setMsgs(m => [...m, { role: 'me', text }])
    setQ(''); setBusy(true)
    try {
      const r = await askAgent(text, page)
      setMsgs(m => [...m, { role: 'bot', text: r.answer, used_llm: r.used_llm }])
    } catch (e) {
      setMsgs(m => [...m, { role: 'bot', text: 'Could not reach the assistant. Is the backend running on port 8000?' }])
    } finally {
      setBusy(false)
    }
  }

  function newChat() { setMsgs([]); setQ('') }

  if (!open) {
    return (
      <button className="fab" onClick={() => setOpen(true)}>
        <span className="ico">💬</span> Ask the assistant
      </button>
    )
  }

  return (
    <div className="assistant">
      <div className="ahead">
        <div>
          <div className="at">Planning copilot</div>
          <div className="as">Answers use real numbers from the engine</div>
        </div>
        <div className="ahead-actions">
          <button className="newchat" onClick={newChat} disabled={busy || msgs.length === 0} title="Start a new chat">＋ New chat</button>
          <button className="x" onClick={() => setOpen(false)} title="Close">×</button>
        </div>
      </div>

      <div className="body">
        {msgs.length === 0 && (
          <div className="muted" style={{ marginBottom: 10 }}>
            You’re on the <b>{PAGE_LABEL[page] || 'Dashboard'}</b> tab. Ask about {(PAGE_LABEL[page] || 'the plan').toLowerCase()} — or anything about this week’s plan.
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`bubble ${m.role === 'me' ? 'me' : ''}`}>
            {m.role === 'bot' && m.used_llm !== undefined && (
              <div style={{ marginBottom: 6 }}>
                <span className={`tag ${m.used_llm ? 'llm' : 'fallback'}`}>
                  {m.used_llm ? 'Azure OpenAI' : 'engine (no key)'}
                </span>
              </div>
            )}
            {m.text}
          </div>
        ))}
        {busy && <div className="muted">Thinking…</div>}
      </div>

      <div className="foot">
        <div className="chips">
          {samples.map(s => <span key={s} className="chip" onClick={() => send(s)}>{s}</span>)}
        </div>
        <div className="arow">
          <input
            placeholder={`Ask about ${(PAGE_LABEL[page] || 'the plan').toLowerCase()}…`}
            value={q}
            maxLength={500}
            onChange={e => setQ(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && send()}
          />
          <button className="btn" disabled={busy} onClick={() => send()}>Send</button>
        </div>
      </div>
    </div>
  )
}
