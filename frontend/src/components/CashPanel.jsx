export default function CashPanel({ player }) {
  const fmt = (n) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)
  
  return (
    <div className="panel cash-panel">
      <div className="panel-header">
        <h2>{player.company_name}</h2>
        <span className="month-badge">Month {player.current_month}</span>
      </div>
      <div className="cash-grid">
        <div className="cash-item main">
          <label>Cash Position</label>
          <span className="cash-value">{fmt(player.cash)}</span>
        </div>
        <div className="cash-item">
          <label>Revenue</label>
          <span className="revenue-value">{fmt(player.revenue)}</span>
        </div>
        <div className="cash-item">
          <label>Market Share</label>
          <span className="share-value">{player.market_share.toFixed(1)}%</span>
        </div>
      </div>
      <div className="player-meta">
        <span className="tag">{player.industry}</span>
        <span className="tag">{player.style}</span>
        <span className="tag">Risk: {player.risk_tolerance}</span>
      </div>
    </div>
  )
}
