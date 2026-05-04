export default function Inbox({ messages, activeId, onOpen }) {
  return (
    <section className="panel panel-inbox">
      <h2>Inbox</h2>
      {!messages.length ? <p className="muted">No emails yet. Start the month to receive the brief.</p> : null}
      <ul className="inbox-list">
        {messages.map((message) => (
          <li key={message.id} className={activeId === message.id ? "is-active" : ""}>
            <button type="button" className="inbox-button" onClick={() => onOpen(message)}>
              <div className="inbox-meta">
                <span>{message.sender}</span>
                {message.requires_action ? <span className="badge urgent">Action</span> : <span className="badge">{message.category}</span>}
                {message.is_read ? null : <span className="badge unread">Unread</span>}
              </div>
              <strong>{message.subject}</strong>
              <p>{message.body}</p>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
