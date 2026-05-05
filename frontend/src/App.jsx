import { useEffect, useState } from "react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

const money = (v) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(v ?? 0);

const signed = (v) => `${v >= 0 ? "+" : ""}${money(v)}`;

async function api(path, opts = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export default function App() {
  const [gameId, setGameId] = useState(() => localStorage.getItem("game_id") || "");
  const [state, setState] = useState(null);
  const [draft, setDraft] = useState("");
  const [companyDraft, setCompanyDraft] = useState("Pax Motors");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!gameId) return;
    api(`/api/game/${gameId}`)
      .then(setState)
      .catch(() => {
        localStorage.removeItem("game_id");
        setGameId("");
      });
  }, [gameId]);

  const startGame = async () => {
    setBusy("new");
    setError("");
    try {
      const game = await api("/api/game", {
        method: "POST",
        body: JSON.stringify({ company_name: companyDraft.trim() || "Pax Motors" }),
      });
      localStorage.setItem("game_id", game.id);
      setGameId(game.id);
      setState(game);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy("");
    }
  };

  const addAction = async (e) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setBusy("add");
    setError("");
    try {
      const next = await api(`/api/game/${gameId}/action`, {
        method: "POST",
        body: JSON.stringify({ text }),
      });
      setState(next);
      setDraft("");
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy("");
    }
  };

  const removeAction = async (index) => {
    setError("");
    try {
      const next = await api(`/api/game/${gameId}/action/${index}`, { method: "DELETE" });
      setState(next);
    } catch (e) {
      setError(String(e.message || e));
    }
  };

  const simulate = async () => {
    setBusy("sim");
    setError("");
    try {
      const next = await api(`/api/game/${gameId}/simulate`, { method: "POST" });
      setState(next);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy("");
    }
  };

  const reset = () => {
    localStorage.removeItem("game_id");
    setGameId("");
    setState(null);
  };

  if (!gameId || !state) {
    return (
      <main className="app-shell start-screen">
        <header className="topbar">
          <h1>Pax Venture</h1>
          <p>Write actions. Simulate the month. The LLM runs the world.</p>
        </header>
        {error ? <p className="error-banner">{error}</p> : null}
        <section className="panel start-card">
          <h2>New Game</h2>
          <input
            value={companyDraft}
            onChange={(e) => setCompanyDraft(e.target.value)}
            placeholder="Company name"
          />
          <button type="button" onClick={startGame} disabled={busy === "new"}>
            {busy === "new" ? "Starting..." : "Start Company"}
          </button>
        </section>
      </main>
    );
  }

  const lastTurn = state.history[state.history.length - 1];

  return (
    <main className="app-shell">
      <header className="topbar">
        <h1>Pax Venture</h1>
        <p>
          {state.company_name} — Month {state.month}
          <button type="button" className="link" onClick={reset}>
            new game
          </button>
        </p>
      </header>
      {error ? <p className="error-banner">{error}</p> : null}
      <div className="layout-grid">
        <aside className="col-left">
          <section className="panel panel-cash">
            <h2>Position</h2>
            <div className="kpi-grid">
              <div>
                <span>Cash</span>
                <strong>{money(state.cash)}</strong>
              </div>
              <div>
                <span>Revenue / Mo</span>
                <strong>{money(state.revenue)}</strong>
              </div>
            </div>
            <button
              type="button"
              className="simulate-btn"
              onClick={simulate}
              disabled={busy === "sim"}
            >
              {busy === "sim" ? "Simulating..." : `Simulate Month ${state.month + 1}`}
            </button>
          </section>

          <section className="panel">
            <h2>Leaderboard</h2>
            <ul className="leaderboard">
              {state.leaderboard.map((row, i) => (
                <li key={row.name} className={row.is_player ? "is-you" : ""}>
                  <div>
                    <span className="rank">#{i + 1}</span>
                    <strong>{row.name}</strong>
                  </div>
                  <span>{money(row.cash)}</span>
                </li>
              ))}
            </ul>
          </section>
        </aside>

        <section className="col-center">
          <section className="panel">
            <div className="panel-title-row">
              <h2>Action Plan</h2>
              <span>{state.actions.length} queued</span>
            </div>
            <div className="action-list">
              {state.actions.length ? (
                state.actions.map((text, i) => (
                  <article key={`${i}-${text}`} className="action-item">
                    <span>{i + 1}</span>
                    <p>{text}</p>
                    <button type="button" className="remove" onClick={() => removeAction(i)}>
                      ×
                    </button>
                  </article>
                ))
              ) : (
                <p className="empty-state">No actions queued. Write what you want to do this month.</p>
              )}
            </div>
            <form className="action-compose" onSubmit={addAction}>
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="e.g. Launch fleet pilot with two logistics customers"
                disabled={busy === "add"}
              />
              <button type="submit" disabled={busy === "add" || !draft.trim()}>
                {busy === "add" ? "Adding..." : "Add"}
              </button>
            </form>
          </section>

          {lastTurn ? (
            <section className="panel panel-month">
              <div className="panel-title-row">
                <h2>Month {lastTurn.month}</h2>
                <div className="impact-row">
                  <span>Cash {signed(lastTurn.player_cash_delta)}</span>
                  <span>Revenue {signed(lastTurn.player_revenue_delta)}</span>
                </div>
              </div>
              {[lastTurn.your_move, lastTurn.competitor_spotlight, lastTurn.market]
                .filter((s) => s && (s.title || s.body))
                .map((s, i) => (
                  <article key={i} className="story-card">
                    <h3>{s.title}</h3>
                    <p>{s.body}</p>
                  </article>
                ))}
              {lastTurn.competitor_actions?.length ? (
                <details className="competitor-actions-wrap">
                  <summary>What competitors did this month</summary>
                  <ul className="competitor-actions">
                    {lastTurn.competitor_actions.map((c) => (
                      <li key={c.name}>
                        <strong>{c.name}:</strong> {c.action}
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </section>
          ) : null}
        </section>
      </div>
    </main>
  );
}
