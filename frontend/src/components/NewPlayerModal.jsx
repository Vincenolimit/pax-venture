import { useState } from 'react'

const INDUSTRIES = ['automotive', 'tech', 'retail', 'energy', 'pharma', 'finance']
const STYLES = ['aggressive', 'balanced', 'conservative', 'innovation']
const RISKS = ['high', 'medium', 'low']

export default function NewPlayerModal({ onSubmit }) {
  const [form, setForm] = useState({
    name: '',
    company_name: '',
    industry: 'automotive',
    style: 'balanced',
    risk_tolerance: 'medium',
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    if (form.name && form.company_name) {
      onSubmit(form)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal">
        <h1>🏦 Pax Venture</h1>
        <p>You're the CEO. Run your company month by month. Compete for cash.</p>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Your Name</label>
            <input value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))} required />
          </div>
          <div className="form-group">
            <label>Company Name</label>
            <input value={form.company_name} onChange={e => setForm(f => ({...f, company_name: e.target.value}))} required />
          </div>
          <div className="form-group">
            <label>Industry</label>
            <div className="chip-group">
              {INDUSTRIES.map(i => (
                <button key={i} type="button" className={`chip ${form.industry === i ? 'active' : ''}`}
                  onClick={() => setForm(f => ({...f, industry: i}))}>{i}</button>
              ))}
            </div>
          </div>
          <div className="form-group">
            <label>CEO Style</label>
            <div className="chip-group">
              {STYLES.map(s => (
                <button key={s} type="button" className={`chip ${form.style === s ? 'active' : ''}`}
                  onClick={() => setForm(f => ({...f, style: s}))}>{s}</button>
              ))}
            </div>
          </div>
          <div className="form-group">
            <label>Risk Tolerance</label>
            <div className="chip-group">
              {RISKS.map(r => (
                <button key={r} type="button" className={`chip ${form.risk_tolerance === r ? 'active' : ''}`}
                  onClick={() => setForm(f => ({...f, risk_tolerance: r}))}>{r}</button>
              ))}
            </div>
          </div>
          <button type="submit" className="btn btn-start">Start Game</button>
        </form>
      </div>
    </div>
  )
}
