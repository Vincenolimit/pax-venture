import { useState } from "react";

export default function ChatPanel({
  transcript,
  liveNarrative,
  resultLine,
  onSubmitDecision,
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
    onSubmitDecision(text);
  };

  return (
    <section className="panel panel-chat">
      <h2>Decision Desk</h2>
      <div className="chat-feed">
        {transcript.map((row, index) => (
          <article key={`${row.role}-${index}`} className={`msg msg-${row.role}`}>
            <p>{row.text}</p>
          </article>
        ))}
        {liveNarrative ? (
          <article className="msg msg-llm streaming">
            <p>{liveNarrative}</p>
          </article>
        ) : null}
      </div>
      {resultLine ? <p className="impact-line">{resultLine}</p> : null}
      <form onSubmit={handleSubmit} className="chat-compose">
        <textarea
          value={draft}
          onChange={(ev) => setDraft(ev.target.value)}
          disabled={disabled || busy}
          placeholder="Type your decision and press Enter. Shift+Enter for a newline."
          onKeyDown={(ev) => {
            if (ev.key === "Enter" && !ev.shiftKey) {
              handleSubmit(ev);
            }
          }}
        />
      </form>
    </section>
  );
}
