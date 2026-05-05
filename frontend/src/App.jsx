import { useEffect, useState } from "react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

const money = (v) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(v ?? 0);

const compactMoney = (v) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(v ?? 0);

const signed = (v) => `${v >= 0 ? "+" : ""}${money(v)}`;
const signedCompact = (v) => `${v >= 0 ? "+" : ""}${compactMoney(v)}`;

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
  const [ceoDraft, setCeoDraft] = useState("");
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
        body: JSON.stringify({
          company_name: companyDraft.trim() || "Pax Motors",
          ceo_name: ceoDraft.trim() || null,
        }),
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
          <input
            value={ceoDraft}
            onChange={(e) => setCeoDraft(e.target.value)}
            placeholder="CEO name (optional)"
          />
          <button type="button" onClick={startGame} disabled={busy === "new"}>
            {busy === "new" ? "Starting..." : "Start Company"}
          </button>
        </section>
      </main>
    );
  }

  const lastTurn = state.history[state.history.length - 1];
  const identity = state.memory?.identity || {};
  const rivalThreads = (state.competitors || [])
    .flatMap((competitor) =>
      (competitor.initiatives || []).map((initiative) => ({
        competitor: competitor.name,
        ...initiative,
      })),
    )
    .sort((a, b) => (a.remaining_months ?? 0) - (b.remaining_months ?? 0));

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <h1>Pax Venture</h1>
          <p className="brand-sub">
            {identity.ceo_name ? `${identity.ceo_name} · ` : ""}
            {state.company_name} · Month {state.month}
            <button type="button" className="link" onClick={reset}>
              new game
            </button>
          </p>
        </div>
        <div className="kpi-bar">
          <div className="kpi">
            <span>Cash</span>
            <strong>{money(state.cash)}</strong>
          </div>
          <div className="kpi">
            <span>Revenue / mo</span>
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
      </header>
      {error ? <p className="error-banner">{error}</p> : null}
      <div className="main-grid">
        <section className="col-main">
          <section className="panel actions-panel">
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
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    if (draft.trim() && busy !== "add") addAction(e);
                  }
                }}
                placeholder="Type your action..."
                disabled={busy === "add"}
                rows={1}
              />
              <button
                type="submit"
                className="send-btn"
                disabled={busy === "add" || !draft.trim()}
                aria-label="Add action"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 2 11 13" />
                  <path d="M22 2 15 22l-4-9-9-4 20-7Z" />
                </svg>
              </button>
            </form>
          </section>

          {lastTurn ? (
            <section className="panel panel-month">
              <div className="panel-title-row">
                <h2>Month {lastTurn.month}</h2>
                <div className="impact-row">
                  <span>Cash {signed(lastTurn.player_total_cash_delta ?? lastTurn.player_cash_delta)}</span>
                  <span>Revenue {signed(lastTurn.player_total_revenue_delta ?? lastTurn.player_revenue_delta)}</span>
                  <span>
                    Market Cap {signedCompact(lastTurn.player_total_market_cap_delta ?? lastTurn.player_market_cap_delta ?? 0)}
                  </span>
                  {lastTurn.initiative_effect?.names?.length ? (
                    <span>Recurring {signed(lastTurn.initiative_effect.cash_delta)} cash</span>
                  ) : null}
                </div>
              </div>
              <div className="month-body">
                {[lastTurn.your_move, lastTurn.competitor_spotlight, lastTurn.market]
                  .filter((s) => {
                    if (!s || (!s.title && !s.body)) return false;
                    const text = `${s.title || ""} ${s.body || ""}`.toLowerCase();
                    return !/impact chip|numeric impact|schema|simulation internal|shown in the impact/.test(text);
                  })
                  .map((s, i) => (
                    <article key={i} className="story-card">
                      {s.source ? <span className="story-source">{s.source}</span> : null}
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
                          <span>
                            Cash {signed(c.cash_delta ?? 0)} · Revenue {signedCompact(c.revenue_delta ?? 0)} ·
                            Market Cap {signedCompact(c.market_cap_delta ?? 0)}
                          </span>
                          {c.recurring_effect?.names?.length ? (
                            <span>
                              Recurring {signed(c.recurring_effect.cash_delta)} cash from{" "}
                              {c.recurring_effect.names.join(", ")}
                            </span>
                          ) : null}
                          {c.initiative ? (
                            <span>
                              {c.initiative_status === "continued" ? "Continuing plan" : "Active plan"}: {c.initiative}
                            </span>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  </details>
                ) : null}
              </div>
            </section>
          ) : null}
        </section>

        <aside className="col-side">
          <section className="panel ranking-panel">
            <h2>Market Cap Ranking</h2>
            <ul className="leaderboard">
              {state.leaderboard.map((row, i) => (
                <li key={row.name} className={row.is_player ? "is-you" : ""}>
                  <div>
                    <span className="rank">#{i + 1}</span>
                    <strong>{row.name}</strong>
                  </div>
                  <div className="value-stack">
                    <strong>{compactMoney(row.market_cap ?? row.cash)}</strong>
                    <span>{compactMoney(row.revenue)} / mo</span>
                    {row.initiatives ? <span>{row.initiatives} active plans</span> : null}
                  </div>
                </li>
              ))}
            </ul>
          </section>

          {state.initiatives?.length ? (
            <section className="panel initiatives-panel">
              <h2>Active Initiatives</h2>
              <ul className="initiative-list">
                {state.initiatives.map((initiative) => (
                  <li key={initiative.name}>
                    <strong>{initiative.name}</strong>
                    <span>
                      {initiative.remaining_months} mo · {signed(initiative.monthly_cash_delta)} cash/mo ·{" "}
                      {signedCompact(initiative.monthly_market_cap_delta)} value/mo
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {rivalThreads.length ? (
            <section className="panel initiatives-panel">
              <h2>Rival Threads</h2>
              <ul className="initiative-list rival-thread-list">
                {rivalThreads.slice(0, 6).map((initiative) => (
                  <li key={`${initiative.competitor}-${initiative.name}`}>
                    <strong>
                      {initiative.competitor}: {initiative.name}
                    </strong>
                    <span>
                      M{initiative.started_month || "?"} / {initiative.remaining_months} mo left /{" "}
                      {signedCompact(initiative.monthly_market_cap_delta)} value/mo
                    </span>
                    {initiative.last_action ? <span>{initiative.last_action}</span> : null}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </aside>
      </div>
    </main>
  );
}
