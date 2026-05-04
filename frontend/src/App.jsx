import { useCallback, useEffect, useMemo, useState } from "react";

import AutopsyCard from "./components/AutopsyCard.jsx";
import CashPanel from "./components/CashPanel.jsx";
import ChatPanel from "./components/ChatPanel.jsx";
import CostBadge from "./components/CostBadge.jsx";
import Inbox from "./components/Inbox.jsx";
import Leaderboard from "./components/Leaderboard.jsx";
import ModelPicker from "./components/ModelPicker.jsx";
import NewPlayerModal from "./components/NewPlayerModal.jsx";
import {
  createPlayer,
  decideStream,
  endMonth,
  getAutopsy,
  getCost,
  getLeaderboard,
  getMessages,
  getState,
  markMessageRead,
  patchPlayer,
  startMonthStream,
} from "./lib/api";

function monthInPlay(state) {
  return (state?.player?.current_month ?? 0) + 1;
}

function formatImpactLine(result) {
  if (!result) {
    return "";
  }
  const cash = Number(result.cash_impact ?? 0);
  const revenue = Number(result.revenue_impact ?? 0);
  const market = Number(result.market_impact ?? 0);
  const employees = Number(result.employees_change ?? 0);
  return `${cash >= 0 ? "+" : ""}${cash.toLocaleString()} cash, ${revenue >= 0 ? "+" : ""}${revenue.toLocaleString()} rev/mo, ${market >= 0 ? "+" : ""}${market}% share, ${employees >= 0 ? "+" : ""}${employees} employees`;
}

function PublicAutopsyView({ playerId }) {
  const [autopsy, setAutopsy] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    getAutopsy(playerId)
      .then((payload) => {
        if (active) {
          setAutopsy(payload);
        }
      })
      .catch((err) => {
        if (active) {
          setError(String(err.message || err));
        }
      });
    return () => {
      active = false;
    };
  }, [playerId]);

  return (
    <main className="public-autopsy">
      <h1>Pax Venture - Autopsy</h1>
      {error ? <p className="error-banner">{error}</p> : null}
      <AutopsyCard autopsy={autopsy} playerId={playerId} onPlayAgain={() => (window.location.href = "/")} />
    </main>
  );
}

function GameApp() {
  const [playerId, setPlayerId] = useState(() => window.localStorage.getItem("player_id") || "");
  const [state, setState] = useState(null);
  const [inbox, setInbox] = useState([]);
  const [leaderboardRows, setLeaderboardRows] = useState([]);
  const [cost, setCost] = useState({ cost_spent_usd: 0, cost_cap_usd: null, cap_percent: 0 });
  const [autopsy, setAutopsy] = useState(null);
  const [selectedMessageId, setSelectedMessageId] = useState(null);
  const [transcript, setTranscript] = useState([]);
  const [liveNarrative, setLiveNarrative] = useState("");
  const [resultLine, setResultLine] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [busyAction, setBusyAction] = useState("");

  const capReached = useMemo(() => Number(cost.cap_percent ?? 0) >= 100, [cost.cap_percent]);
  const interactionDisabled = !playerId || !state || !!state.player.game_over || capReached;

  const loadSupplemental = useCallback(async (pid, currentState) => {
    const [leaderboard, costState, messages] = await Promise.all([
      getLeaderboard(),
      getCost(pid),
      getMessages(pid, monthInPlay(currentState)),
    ]);
    setLeaderboardRows(leaderboard.rows || []);
    setCost(costState);
    setInbox(messages.messages || []);
  }, []);

  const reloadPlayer = useCallback(
    async (pid) => {
      setLoading(true);
      try {
        const nextState = await getState(pid);
        setState(nextState);
        await loadSupplemental(pid, nextState);
        if (nextState.player.game_over) {
          setAutopsy(await getAutopsy(pid));
        } else {
          setAutopsy(null);
        }
      } finally {
        setLoading(false);
      }
    },
    [loadSupplemental],
  );

  useEffect(() => {
    if (!playerId) {
      return;
    }
    reloadPlayer(playerId).catch((err) => setError(String(err.message || err)));
  }, [playerId, reloadPlayer]);

  const handleCreatePlayer = async (payload) => {
    setCreating(true);
    setError("");
    try {
      const created = await createPlayer(payload);
      const pid = created.player.id;
      setPlayerId(pid);
      setState(created);
      setTranscript([]);
      setLiveNarrative("");
      setResultLine("");
      setAutopsy(null);
      window.localStorage.setItem("player_id", pid);
      await loadSupplemental(pid, created);
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setCreating(false);
    }
  };

  const handleOpenMessage = (message) => {
    setSelectedMessageId(message.id);
    setInbox((prev) => prev.map((item) => (item.id === message.id ? { ...item, is_read: true } : item)));
    markMessageRead(playerId, message.id, true).catch(() => {});
  };

  const handleStartMonth = async () => {
    if (interactionDisabled) {
      return;
    }
    setBusyAction("start");
    setError("");
    setResultLine("");
    try {
      const stream = startMonthStream(playerId);
      for await (const event of stream) {
        if (event.event === "email" && event.data) {
          setInbox((prev) => [...prev, { ...event.data, is_read: false }]);
        }
        if (event.event === "error" && event.data) {
          setError(event.data.message || "Failed to start month");
        }
      }
      await reloadPlayer(playerId);
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusyAction("");
    }
  };

  const handleDecision = async (text) => {
    if (interactionDisabled) {
      return;
    }
    setBusyAction("decide");
    setError("");
    setResultLine("");
    setLiveNarrative("");
    setTranscript((prev) => [...prev, { role: "player", text }]);
    try {
      const stream = decideStream(playerId, {
        text,
        inbox_ref_ids: selectedMessageId ? [selectedMessageId] : [],
      });
      let finalNarrative = "";
      for await (const event of stream) {
        if (event.event === "narrative.chunk" && event.data?.text) {
          finalNarrative += event.data.text;
          setLiveNarrative(finalNarrative);
        }
        if (event.event === "result" && event.data) {
          const narrative = event.data.narrative || finalNarrative;
          setTranscript((prev) => [...prev, { role: "llm", text: narrative }]);
          setLiveNarrative("");
          setResultLine(formatImpactLine(event.data));
          if (event.data.updated_state) {
            setState(event.data.updated_state);
            await loadSupplemental(playerId, event.data.updated_state);
            if (event.data.updated_state.player.game_over) {
              setAutopsy(await getAutopsy(playerId));
            }
          }
        }
        if (event.event === "error" && event.data) {
          setError(event.data.message || "Decision request failed");
        }
      }
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusyAction("");
    }
  };

  const handleEndMonth = async () => {
    if (interactionDisabled) {
      return;
    }
    setBusyAction("end");
    setError("");
    setResultLine("");
    try {
      const result = await endMonth(playerId);
      setTranscript((prev) => [...prev, { role: "system", text: `Month ${result.month} closed. Cash now ${Math.round(result.cash).toLocaleString()}.` }]);
      await reloadPlayer(playerId);
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusyAction("");
    }
  };

  const handleModelTierChange = async (tier) => {
    if (!playerId || !state || tier === state.player.model_tier) {
      return;
    }
    setError("");
    try {
      const payload = await patchPlayer(playerId, { model_tier: tier });
      setState((prev) => ({ ...prev, player: { ...prev.player, model_tier: payload.model_tier } }));
    } catch (err) {
      setError(String(err.message || err));
    }
  };

  const handleCostCapChange = async (nextCap) => {
    if (!playerId) {
      return;
    }
    setError("");
    try {
      await patchPlayer(playerId, { cost_cap_usd: nextCap });
      await reloadPlayer(playerId);
    } catch (err) {
      setError(String(err.message || err));
    }
  };

  const handlePlayAgain = () => {
    window.localStorage.removeItem("player_id");
    setPlayerId("");
    setState(null);
    setInbox([]);
    setLeaderboardRows([]);
    setAutopsy(null);
    setTranscript([]);
    setLiveNarrative("");
    setResultLine("");
    setSelectedMessageId(null);
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <h1>Pax Venture</h1>
        <p>Inbox. Decisions. Consequences.</p>
      </header>
      {error ? <p className="error-banner">{error}</p> : null}
      <div className="layout-grid">
        <aside className="col-left">
          {state ? (
            <CashPanel
              player={state.player}
              derived={state.derived}
              onStartMonth={handleStartMonth}
              onEndMonth={handleEndMonth}
              disabled={interactionDisabled || busyAction === "decide" || busyAction === "start" || busyAction === "end"}
              busyAction={busyAction}
            />
          ) : (
            <section className="panel">Preparing game state...</section>
          )}
          <Leaderboard rows={leaderboardRows} playerId={playerId} />
        </aside>
        <section className="col-center">
          <Inbox messages={inbox} activeId={selectedMessageId} onOpen={handleOpenMessage} />
          <ChatPanel
            transcript={transcript}
            liveNarrative={liveNarrative}
            resultLine={resultLine}
            onSubmitDecision={handleDecision}
            disabled={interactionDisabled}
            busy={busyAction === "decide" || loading}
          />
        </section>
        <aside className="col-right">
          <ModelPicker value={state?.player?.model_tier || "balanced"} onChange={handleModelTierChange} disabled={!state || loading} />
          <CostBadge cost={cost} onCapChange={handleCostCapChange} disabled={!state || loading} />
          {state?.player?.game_over ? <AutopsyCard autopsy={autopsy} playerId={playerId} onPlayAgain={handlePlayAgain} /> : null}
        </aside>
      </div>
      {!playerId ? <NewPlayerModal onCreate={handleCreatePlayer} creating={creating} /> : null}
    </main>
  );
}

export default function App() {
  const path = window.location.pathname;
  if (path.startsWith("/autopsy/")) {
    const playerId = path.replace("/autopsy/", "").trim();
    return <PublicAutopsyView playerId={playerId} />;
  }
  return <GameApp />;
}
