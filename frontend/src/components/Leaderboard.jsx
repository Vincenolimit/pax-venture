import { useEffect, useState } from 'react'

export default function Leaderboard({ entries, currentPlayerId }) {
  const [sortBy, setSortBy] = useState('cash')
  
  const sorted = [...entries].sort((a, b) => {
    if (sortBy === 'cash') return b.cash - a.cash
    if (sortBy === 'revenue') return b.revenue - a.revenue
    if (sortBy === 'share') return b.market_share - a.market_share
    return 0
  })

  const fmt = (n) => {
    if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`
    if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`
    return `$${n}`
  }

  return (
    <div className="panel leaderboard-panel">
      <div className="panel-header">
        <h2>Leaderboard</h2>
        <div className="sort-controls">
          {['cash', 'revenue', 'share'].map(s => (
            <button key={s} className={`sort-btn ${sortBy === s ? 'active' : ''}`} onClick={() => setSortBy(s)}>
              {s === 'share' ? 'Mkt%' : s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>
      <div className="leaderboard-list">
        {sorted.map(entry => (
          <div key={entry.player_id} className={`lb-row ${entry.player_id === currentPlayerId ? 'self' : ''}`}>
            <span className="lb-rank">#{entry.rank}</span>
            <span className="lb-name">{entry.company_name}</span>
            <span className="lb-stat">{fmt(entry[sortBy === 'share' ? 'market_share' : sortBy === 'revenue' ? 'revenue' : 'cash'])}</span>
            <span className="lb-month">M{entry.current_month}</span>
          </div>
        ))}
        {sorted.length === 0 && <div className="lb-empty">No players yet</div>}
      </div>
    </div>
  )
}
