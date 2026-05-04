import { useState, useEffect, useCallback } from 'react'
import CashPanel from './components/CashPanel.jsx'
import Inbox from './components/Inbox.jsx'
import Leaderboard from './components/Leaderboard.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import NewPlayerModal from './components/NewPlayerModal.jsx'

const API = '/api/v1'

export default function App() {
  const [player, setPlayer] = useState(null)
  const [inbox, setInbox] = useState([])
  const [leaderboard, setLeaderboard] = useState([])
  const [lastDecision, setLastDecision] = useState(null)
  const [showNewPlayer, setShowNewPlayer] = useState(false)
  const [loading, setLoading] = useState(false)

  // Load player from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem('pax_venture_player_id')
    if (saved) {
      loadPlayer(saved)
    } else {
      setShowNewPlayer(true)
    }
  }, [])

  // Refresh leaderboard periodically
  useEffect(() => {
    if (!player) return
    refreshLeaderboard()
    const interval = setInterval(refreshLeaderboard, 15000)
    return () => clearInterval(interval)
  }, [player])

  const loadPlayer = async (playerId) => {
    try {
      const res = await fetch(`${API}/players/${playerId}`)
      if (res.ok) {
        const data = await res.json()
        setPlayer(data)
        loadInbox(playerId)
      } else {
        localStorage.removeItem('pax_venture_player_id')
        setShowNewPlayer(true)
      }
    } catch {
      localStorage.removeItem('pax_venture_player_id')
      setShowNewPlayer(true)
    }
  }

  const loadInbox = async (playerId) => {
    const res = await fetch(`${API}/players/${playerId}/inbox`)
    if (res.ok) setInbox(await res.json())
  }

  const refreshLeaderboard = async () => {
    const res = await fetch(`${API}/leaderboard`)
    if (res.ok) setLeaderboard(await res.json())
  }

  const handleNewPlayer = async (data) => {
    const res = await fetch(`${API}/players`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (res.ok) {
      const player = await res.json()
      setPlayer(player)
      localStorage.setItem('pax_venture_player_id', player.id)
      setShowNewPlayer(false)
    }
  }

  const handleStartMonth = async () => {
    if (!player) return
    setLoading(true)
    const res = await fetch(`${API}/players/${player.id}/start-month`, { method: 'POST' })
    if (res.ok) {
      const data = await res.json()
      await loadPlayer(player.id)
      await loadInbox(player.id)
    }
    setLoading(false)
  }

  const handleSubmitDecision = async (text) => {
    if (!player) return
    setLoading(true)
    const res = await fetch(`${API}/players/${player.id}/decide`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision_text: text }),
    })
    if (res.ok) {
      const result = await res.json()
      setLastDecision(result)
      await loadPlayer(player.id)
      await loadInbox(player.id)
    }
    setLoading(false)
  }

  const handleEndMonth = async () => {
    if (!player) return
    setLoading(true)
    const res = await fetch(`${API}/players/${player.id}/end-month`, { method: 'POST' })
    if (res.ok) {
      await loadPlayer(player.id)
      await refreshLeaderboard()
    }
    setLoading(false)
  }

  const markRead = async (messageId) => {
    if (!player) return
    await fetch(`${API}/players/${player.id}/inbox/${messageId}/read`, { method: 'POST' })
    loadInbox(player.id)
  }

  if (!player) {
    return (
      <div className="app-loading">
        {showNewPlayer && <NewPlayerModal onSubmit={handleNewPlayer} />}
      </div>
    )
  }

  return (
    <div className="app-layout">
      {/* LEFT COLUMN: Inbox + Chat */}
      <div className="left-column">
        <Inbox messages={inbox} onMarkRead={markRead} />
        <ChatPanel
          onDecide={handleSubmitDecision}
          onStartMonth={handleStartMonth}
          onEndMonth={handleEndMonth}
          currentMonth={player.current_month}
          loading={loading}
          lastDecision={lastDecision}
        />
      </div>

      {/* RIGHT COLUMN: Cash + Leaderboard */}
      <div className="right-column">
        <CashPanel player={player} />
        <Leaderboard entries={leaderboard} currentPlayerId={player.id} />
      </div>
    </div>
  )
}
