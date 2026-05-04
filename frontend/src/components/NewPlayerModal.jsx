import { useState } from "react";

const DEFAULTS = {
  industry_id: "automotive",
  name: "",
  company_name: "",
  style: "balanced",
  risk_tolerance: "medium",
  model_tier: "balanced",
};

export default function NewPlayerModal({ onCreate, creating }) {
  const [form, setForm] = useState(DEFAULTS);

  const update = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const onSubmit = (ev) => {
    ev.preventDefault();
    if (!form.name.trim() || !form.company_name.trim() || creating) {
      return;
    }
    onCreate({
      ...form,
      name: form.name.trim(),
      company_name: form.company_name.trim(),
    });
  };

  return (
    <div className="modal-backdrop">
      <form className="modal" onSubmit={onSubmit}>
        <h2>Start New Run</h2>
        <label htmlFor="ceo-name">CEO Name</label>
        <input id="ceo-name" value={form.name} onChange={(ev) => update("name", ev.target.value)} />
        <label htmlFor="company-name">Company Name</label>
        <input id="company-name" value={form.company_name} onChange={(ev) => update("company_name", ev.target.value)} />
        <label htmlFor="style">Style</label>
        <select id="style" value={form.style} onChange={(ev) => update("style", ev.target.value)}>
          <option value="aggressive">Aggressive</option>
          <option value="balanced">Balanced</option>
          <option value="conservative">Conservative</option>
        </select>
        <label htmlFor="risk">Risk Tolerance</label>
        <select id="risk" value={form.risk_tolerance} onChange={(ev) => update("risk_tolerance", ev.target.value)}>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <label htmlFor="tier">Model Tier</label>
        <select id="tier" value={form.model_tier} onChange={(ev) => update("model_tier", ev.target.value)}>
          <option value="cheap">Cheap</option>
          <option value="balanced">Balanced</option>
          <option value="premium">Premium</option>
        </select>
        <button type="submit" disabled={creating}>
          {creating ? "Creating..." : "Create Player"}
        </button>
      </form>
    </div>
  );
}
