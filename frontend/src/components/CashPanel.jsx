function money(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value ?? 0);
}

export default function CashPanel({ player, derived, onStartMonth, onEndMonth, disabled, monthStarted, busyAction }) {
  return (
    <section className="panel panel-cash">
      <h2>Command Deck</h2>
      <p className="eyebrow">Month {player.current_month + 1}</p>
      <div className="kpi-grid">
        <div>
          <span>Cash</span>
          <strong>{money(player.cash)}</strong>
        </div>
        <div>
          <span>Burn / Mo</span>
          <strong>{money(derived.burn_rate)}</strong>
        </div>
        <div>
          <span>Revenue</span>
          <strong>{money(player.revenue)}</strong>
        </div>
        <div>
          <span>Headcount</span>
          <strong>{player.employees}</strong>
        </div>
      </div>
      <div className={`runway runway-${derived.cash_runway}`}>Runway: {derived.cash_runway}</div>
      <div className="actions-row">
        <button type="button" onClick={onStartMonth} disabled={disabled || monthStarted}>
          {busyAction === "start" ? "Opening..." : monthStarted ? "Month Open" : "Open Month"}
        </button>
        <button type="button" onClick={onEndMonth} disabled={disabled}>
          {busyAction === "end" ? "Simulating..." : "Simulate Month"}
        </button>
      </div>
    </section>
  );
}
