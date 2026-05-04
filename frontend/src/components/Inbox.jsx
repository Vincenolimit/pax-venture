import { useState } from 'react'

const CATEGORY_ICONS = {
  info: '📨',
  warning: '⚠️',
  opportunity: '💡',
  crisis: '🔥',
  board: '👔',
}

export default function Inbox({ messages, onMarkRead }) {
  const [selected, setSelected] = useState(null)

  const unreadCount = messages.filter(m => !m.is_read).length

  return (
    <div className="panel inbox-panel">
      <div className="panel-header">
        <h2>Inbox</h2>
        {unreadCount > 0 && <span className="badge">{unreadCount}</span>}
      </div>
      <div className="inbox-list">
        {messages.length === 0 && (
          <div className="inbox-empty">No messages yet. Start a new month!</div>
        )}
        {messages.map(msg => (
          <div
            key={msg.id}
            className={`inbox-item ${msg.is_read ? '' : 'unread'} ${selected === msg.id ? 'selected' : ''} cat-${msg.category}`}
            onClick={() => { setSelected(msg.id); if (!msg.is_read) onMarkRead(msg.id); }}
          >
            <div className="inbox-item-header">
              <span className="inbox-icon">{CATEGORY_ICONS[msg.category] || '📨'}</span>
              <span className="inbox-sender">{msg.sender}</span>
              {msg.requires_action && <span className="action-badge">!</span>}
              <span className="inbox-month">M{msg.month}</span>
            </div>
            <div className="inbox-subject">{msg.subject}</div>
          </div>
        ))}
      </div>
      {selected && (() => {
        const msg = messages.find(m => m.id === selected)
        if (!msg) return null
        return (
          <div className="inbox-detail">
            <div className="inbox-detail-header">
              <strong>{msg.sender}</strong>: {msg.subject}
            </div>
            <div className="inbox-detail-body">{msg.body}</div>
            {msg.requires_action && <div className="action-required">⚡ Action required — respond in chat below</div>}
          </div>
        )
      })()}
    </div>
  )
}
