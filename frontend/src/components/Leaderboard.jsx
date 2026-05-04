function money(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value ?? 0);
}

export default function Leaderboard({ rows, playerId }) {
  return (
    <section className="panel panel-board">
      <h2>Leaderboard</h2>
      <ul className="leaderboard">
        {rows.map((row) => (
          <li key={row.player_id} className={row.player_id === playerId ? "is-you" : ""}>
            <div>
              <span className="rank">#{row.rank}</span>
              <strong>{row.company_name}</strong>
            </div>
            <span>{money(row.cash)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
