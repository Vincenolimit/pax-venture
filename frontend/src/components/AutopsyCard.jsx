const VERDICT_CLASS = {
  brilliant: "verdict-brilliant",
  sound: "verdict-sound",
  risky: "verdict-risky",
  fatal: "verdict-fatal",
};

export default function AutopsyCard({ autopsy, playerId, onPlayAgain }) {
  if (!autopsy) {
    return (
      <section className="panel panel-autopsy">
        <h2>Autopsy</h2>
        <p className="muted">Autopsy loading...</p>
      </section>
    );
  }

  const sharePath = `${window.location.origin}/autopsy/${playerId}`;

  return (
    <section className="panel panel-autopsy">
      <h2>Autopsy</h2>
      <h3>{autopsy.headline}</h3>
      <p>{autopsy.arc_summary}</p>
      <div className="pivotals">
        {(autopsy.pivotal_decisions || []).map((decision, idx) => (
          <article key={`${decision.month}-${idx}`}>
            <span>M{decision.month}</span>
            <p>{decision.one_liner}</p>
            <strong className={VERDICT_CLASS[decision.verdict] || "verdict-sound"}>{decision.verdict}</strong>
          </article>
        ))}
      </div>
      <p>
        <strong>Cause:</strong> {autopsy.cause_of_death}
      </p>
      <blockquote>{autopsy.board_quote}</blockquote>
      <div className="actions-row">
        <button
          type="button"
          onClick={() => {
            navigator.clipboard.writeText(sharePath).catch(() => {});
          }}
        >
          Share
        </button>
        <button type="button" onClick={onPlayAgain}>
          Play Again
        </button>
      </div>
    </section>
  );
}
