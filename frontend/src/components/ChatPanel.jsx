import { useState, useRef, useEffect } from 'react'

const QUICK_ACTIONS = [
  'Expand to new market',
  'Cut costs by 10%',
  'Invest in R&D',
  'Hire key talent',
  'Launch marketing campaign',
  'Acquire competitor',
]

export default function ChatPanel({ onDecide, onStartMonth, onEndMonth, currentMonth, loading, lastDecision }) {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState([])
  const chatEnd = useRef(null)

  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = () => {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    setMessages(prev => [...prev, { role: 'player', text }])
    onDecide(text).then(result => {
      if (result) {
        setMessages(prev => [...prev, { role: 'outcome', text: result.outcome, impacts: result }])
      }
    })
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const fmtImpact = (label, value, prefix = '', suffix = '') => {
    const sign = value >= 0 ? '+' : ''
    const cls = value >= 0 ? 'positive' : 'negative'
    return <span className={cls}>{prefix}{sign}{value.toLocaleString()}{suffix}</span>
  }

  return (
    <div className="panel chat-panel">
      <div className="panel-header">
        <h2>Decisions</h2>
        <div className="month-controls">
          <button className="btn btn-start" onClick={onStartMonth} disabled={loading || currentMonth > 0}>
            Start Month {currentMonth + 1}
          </button>
          {currentMonth > 0 && (
            <button className="btn btn-end" onClick={onEndMonth} disabled={loading}>
              End Month
            </button>
          )}
        </div>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            Start a month, then tell the AI how you want to run your company.
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`chat-msg ${msg.role}`}>
            {msg.role === 'player' && <div className="msg-player">{msg.text}</div>}
            {msg.role === 'outcome' && (
              <div className="msg-outcome">
                <div className="outcome-text">{msg.text}</div>
                {msg.impacts && (
                  <div className="outcome-impacts">
                    {fmtImpact('Cash', msg.impacts.cash_impact, '$')}{/**/}
                    {' · '}
                    {fmtImpact('Revenue', msg.impacts.revenue_impact, '$')}
                    {' · '}
                    {fmtImpact('Market', msg.impacts.market_impact, '', '%')}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        {loading && <div className="chat-msg system">Thinking...</div>}
      </div>

      <div className="quick-actions">
        {QUICK_ACTIONS.map(action => (
          <button key={action} className="quick-btn" onClick={() => setInput(action)} disabled={loading}>
            {action}
          </button>
        ))}
      </div>

      <div className="chat-input-row">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Describe your decision..."
          disabled={loading}
          rows={2}
        />
        <button className="btn btn-send" onClick={handleSend} disabled={loading || !input.trim()}>
          →
        </button>
      </div>
    </div>
  )
}
