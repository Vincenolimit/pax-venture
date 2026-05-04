const TIERS = ["cheap", "balanced", "premium"];

export default function ModelPicker({ value, onChange, disabled }) {
  return (
    <section className="panel panel-settings">
      <h2>Model Tier</h2>
      <div className="tier-row">
        {TIERS.map((tier) => (
          <button
            key={tier}
            type="button"
            className={tier === value ? "is-selected" : ""}
            onClick={() => onChange(tier)}
            disabled={disabled}
          >
            {tier}
          </button>
        ))}
      </div>
    </section>
  );
}
