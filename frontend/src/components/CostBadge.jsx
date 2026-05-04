import { useEffect, useState } from "react";

function money(value) {
  if (value == null) {
    return "No cap";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export default function CostBadge({ cost, onCapChange, disabled }) {
  const [draft, setDraft] = useState("");
  const pct = cost.cap_percent ?? 0;
  const level = pct >= 100 ? "critical" : pct >= 90 ? "warn" : "ok";

  useEffect(() => {
    setDraft(cost.cost_cap_usd == null ? "" : String(cost.cost_cap_usd));
  }, [cost.cost_cap_usd]);

  const onSubmit = (ev) => {
    ev.preventDefault();
    if (disabled) {
      return;
    }
    const trimmed = draft.trim();
    if (!trimmed) {
      onCapChange(null);
      return;
    }
    const parsed = Number(trimmed);
    if (Number.isNaN(parsed) || parsed < 0) {
      return;
    }
    onCapChange(parsed);
  };

  return (
    <section className={`panel panel-cost cost-${level}`}>
      <h2>Cost</h2>
      <p>
        {money(cost.cost_spent_usd)} / {money(cost.cost_cap_usd)}
      </p>
      <div className="meter">
        <span style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
      </div>
      {pct >= 100 ? <p className="cost-warning">Cap reached. Raise it in settings to continue.</p> : null}
      <form onSubmit={onSubmit} className="cap-form">
        <label htmlFor="cap">Cap</label>
        <input
          id="cap"
          type="number"
          step="0.01"
          min="0"
          placeholder="unset"
          value={draft}
          onChange={(ev) => setDraft(ev.target.value)}
          disabled={disabled}
        />
        <button type="submit" disabled={disabled}>
          Update Cap
        </button>
      </form>
    </section>
  );
}
