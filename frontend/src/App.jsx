import { useEffect, useState } from "react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

const money = (v) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(v ?? 0);

const compactMoney = (v) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(v ?? 0);

const signedMoney = (v) => `${(v ?? 0) >= 0 ? "+" : ""}${money(v ?? 0)}`;
const signedCompact = (v) => `${(v ?? 0) >= 0 ? "+" : ""}${compactMoney(v ?? 0)}`;

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

function Impact({ turn }) {
  if (!turn) return null;
  return (
    <div className="impact-row">
      <span>Cash {signedMoney(turn.player_total_cash_delta ?? turn.player_cash_delta)}</span>
      <span>Revenue {signedMoney(turn.player_total_revenue_delta ?? turn.player_revenue_delta)}</span>
      <span>Value {signedCompact(turn.player_total_market_cap_delta ?? turn.player_market_cap_delta)}</span>
    </div>
  );
}

function EventCard({ event }) {
  if (!event) return null;
  const source = event.source || event.name || "Market";
  const title = event.title || event.action || "Update";
  const body = event.body || event.summary || "";
  return (
    <article className="event-row">
      <span>{source}</span>
      <div>
        <h3>{title}</h3>
        {body ? <p>{body}</p> : null}
      </div>
    </article>
  );
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
      setDraft("");
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy("");
    }
  };

  const simulate = async (e) => {
    e.preventDefault();
    if (!state || state.game_over) return;
    setBusy("sim");
    setError("");
    try {
      const next = await api(`/api/game/${gameId}/simulate`, {
        method: "POST",
        body: JSON.stringify({ text: draft.trim() }),
      });
      setState(next);
      setDraft("");
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
    setDraft("");
  };

  if (!gameId || !state) {
    return (
      <main className="start-shell">
        <section className="start-panel">
          <p className="eyebrow">Pax Venture</p>
          <h1>Start an automotive company.</h1>
          <p>One monthly CEO order. The LLM runs the market, rivals, inbox, and memory.</p>
          {error ? <p className="error-banner">{error}</p> : null}
          <input
            id="company-name"
            name="company_name"
            value={companyDraft}
            onChange={(e) => setCompanyDraft(e.target.value)}
            placeholder="Company name"
          />
          <input
            id="ceo-name"
            name="ceo_name"
            value={ceoDraft}
            onChange={(e) => setCeoDraft(e.target.value)}
            placeholder="CEO name"
          />
          <button type="button" onClick={startGame} disabled={busy === "new"}>
            {busy === "new" ? "Starting..." : "Start company"}
          </button>
        </section>
      </main>
    );
  }

  const lastTurn = state.history?.[state.history.length - 1];
  const identity = state.memory?.identity || {};
  const competitorEvents = lastTurn?.competitor_events || lastTurn?.competitor_actions || [];
  const worldEvents = lastTurn?.world_events || (lastTurn?.market ? [lastTurn.market] : []);
  const memoryThreads = state.memory?.threads || [];

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>Pax Venture</h1>
          <p>
            {identity.ceo_name ? `${identity.ceo_name} / ` : ""}
            {state.company_name} / Month {state.month}
          </p>
        </div>
        <div className="top-actions">
          <button type="button" className="ghost-btn" onClick={reset}>
            New game
          </button>
        </div>
      </header>

      {error ? <p className="error-banner">{error}</p> : null}

      <section className="kpi-strip">
        <div>
          <span>Cash</span>
          <strong>{money(state.cash)}</strong>
        </div>
        <div>
          <span>Revenue / month</span>
          <strong>{money(state.revenue)}</strong>
        </div>
        <div>
          <span>Market value</span>
          <strong>{compactMoney(state.market_cap)}</strong>
        </div>
        <div className={state.game_over ? "status danger" : "status"}>
          <span>Status</span>
          <strong>{state.game_over ? "Eliminated" : "Operating"}</strong>
        </div>
      </section>

      <div className="workspace">
        <section className="main-column">
          <section className="inbox-band">
            <div className="section-head">
              <h2>Inbox</h2>
              <span>{state.inbox?.length || 0} items</span>
            </div>
            <div className="inbox-list">
              {(state.inbox || []).map((item, index) => (
                <article key={`${item.subject}-${index}`} className="inbox-item">
                  <span>{item.sender}</span>
                  <h3>{item.subject}</h3>
                  <p>{item.body}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="order-band">
            <div className="section-head">
              <h2>CEO Order</h2>
              <span>One decision resolves the month</span>
            </div>
            <form onSubmit={simulate} className="order-form">
              <textarea
                id="ceo-order"
                name="ceo_order"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder={state.game_over ? "Game over" : "Type the order for next month..."}
                disabled={busy === "sim" || state.game_over}
                rows={4}
              />
              <button type="submit" disabled={busy === "sim" || state.game_over}>
                {busy === "sim" ? "Resolving..." : `Simulate month ${state.month + 1}`}
              </button>
            </form>
          </section>

          <section className="report-band">
            <div className="section-head">
              <h2>{lastTurn ? `Month ${lastTurn.month} Report` : "Monthly Report"}</h2>
              <Impact turn={lastTurn} />
            </div>
            {lastTurn ? (
              <div className="report-stack">
                <EventCard event={lastTurn.your_move} />
                <div className="split-report">
                  <div>
                    <h3 className="subhead">Competitors</h3>
                    {competitorEvents.map((event, index) => (
                      <EventCard key={`${event.name || "competitor"}-${index}`} event={event} />
                    ))}
                  </div>
                  <div>
                    <h3 className="subhead">World</h3>
                    {worldEvents.map((event, index) => (
                      <EventCard key={`${event.title || "world"}-${index}`} event={event} />
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <p className="empty-state">Your first monthly result will appear here after the CEO order resolves.</p>
            )}
          </section>

          {state.game_over && state.autopsy ? (
            <section className="autopsy-band">
              <h2>Board Autopsy</h2>
              <p>{state.autopsy.board_note}</p>
              <span>Last decision: {state.autopsy.last_decision}</span>
            </section>
          ) : null}
        </section>

        <aside className="side-column">
          <section>
            <div className="section-head">
              <h2>Leaderboard</h2>
            </div>
            <ul className="leaderboard">
              {state.leaderboard.map((row, index) => (
                <li key={row.name} className={row.is_player ? "is-you" : ""}>
                  <span>#{index + 1}</span>
                  <strong>{row.name}</strong>
                  <em>{compactMoney(row.market_cap ?? row.cash)}</em>
                </li>
              ))}
            </ul>
          </section>

          <section>
            <div className="section-head">
              <h2>Active Plans</h2>
            </div>
            <ul className="thread-list">
              {(state.initiatives || []).length ? (
                state.initiatives.map((item) => (
                  <li key={item.name}>
                    <strong>{item.name}</strong>
                    <span>
                      {item.remaining_months} mo left / {signedMoney(item.monthly_cash_delta)} cash/mo
                    </span>
                  </li>
                ))
              ) : (
                <li className="muted">No recurring company plans yet.</li>
              )}
            </ul>
          </section>

          <section>
            <div className="section-head">
              <h2>Memory</h2>
            </div>
            <ul className="thread-list">
              {memoryThreads.length ? (
                memoryThreads.map((thread) => (
                  <li key={thread.label}>
                    <strong>{thread.label}</strong>
                    <span>{thread.summary}</span>
                  </li>
                ))
              ) : (
                <li className="muted">Threads will build as the LLM remembers the company.</li>
              )}
            </ul>
          </section>
        </aside>
      </div>
    </main>
  );
}
