import { useState } from "react";

export default function ActionPanel({
  actions,
  resolution,
  resultLine,
  onSubmitAction,
  disabled,
  busy,
}) {
  const [draft, setDraft] = useState("");

  const handleSubmit = (ev) => {
    ev.preventDefault();
    const text = draft.trim();
    if (!text || disabled || busy) {
      return;
    }
    setDraft("");
    onSubmitAction(text);
  };

  return (
    <section className="panel panel-actions">
      <div className="panel-title-row">
        <h2>Action Plan</h2>
        <span>{actions.length} queued</span>
      </div>
      <div className="action-list">
        {actions.length ? (
          actions.map((action, index) => (
            <article key={action.id ?? `${action.text}-${index}`} className="action-item">
              <span>{index + 1}</span>
              <p>{action.text}</p>
            </article>
          ))
        ) : (
          <p className="empty-state">No actions queued.</p>
        )}
      </div>
      {resolution ? (
        <article className="month-resolution">
          <strong>Monthly result</strong>
          <p>{resolution}</p>
          {resultLine ? <span>{resultLine}</span> : null}
        </article>
      ) : null}
      <form onSubmit={handleSubmit} className="action-compose">
        <textarea
          value={draft}
          onChange={(ev) => setDraft(ev.target.value)}
          disabled={disabled || busy}
          placeholder="Launch fleet pilot with two logistics customers"
        />
        <button type="submit" disabled={disabled || busy || !draft.trim()}>
          {busy ? "Adding..." : "Add Action"}
        </button>
      </form>
    </section>
  );
}
