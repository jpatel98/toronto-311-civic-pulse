import { useEffect, useMemo, useState } from 'react'

const fmt = (n) => (n ?? 0).toLocaleString('en-CA')

function timeAgo(iso) {
  const then = new Date(iso.replace(' ', 'T'))
  const s = (Date.now() - then.getTime()) / 1000
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))}m ago`
  if (s < 86400) return `${Math.round(s / 3600)}h ago`
  return `${Math.round(s / 86400)}d ago`
}

function Sparkline({ daily, height = 44, color = 'var(--accent)' }) {
  if (!daily || daily.length === 0) return null
  const w = 620, h = height, pad = 2
  const max = Math.max(...daily.map((d) => d.n))
  const bw = w / daily.length
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="spark">
      {daily.map((d, i) => {
        const bh = Math.max(1, (d.n / max) * (h - pad))
        return (
          <rect key={d.d} x={i * bw + 0.5} y={h - bh} width={Math.max(0.8, bw - 1)}
                height={bh} fill={color} opacity={0.85}>
            <title>{`${d.d}: ${d.n} requests`}</title>
          </rect>
        )
      })}
    </svg>
  )
}

function Trend({ cur, prev }) {
  if (!prev) return <span className="trend dim">new window</span>
  const pct = Math.round(((cur - prev) / prev) * 1000) / 10
  const up = pct > 0
  return (
    <span className={`trend ${up ? 'up' : 'down'}`}>
      {up ? '+' : ''}{pct}% vs prior 90 days
    </span>
  )
}

function Stat({ label, value, sub }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  )
}

function Brief({ text, title }) {
  if (!text) return null
  return (
    <div className="brief">
      <div className="brief-title">
        <span className="pulse-dot" /> {title}
      </div>
      <p>{text}</p>
    </div>
  )
}

function WardChip({ ward, active, onClick }) {
  const num = ward.match(/\((\d+)\)/)?.[1]
  return (
    <button className={`chip ${active ? 'active' : ''}`} onClick={onClick}>
      <span className="chip-num">{num}</span>
      <span className="chip-name">{ward.replace(/\s*\(\d+\)/, '')}</span>
    </button>
  )
}

function App() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [ward, setWard] = useState(null)
  const [cat, setCat] = useState(null)

  useEffect(() => {
    fetch('data/civic-pulse.json')
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then((d) => { setData(d); setWard(d.wards[0].ward) })
      .catch((e) => setErr(String(e)))
  }, [])

  const wardData = useMemo(
    () => data?.wards.find((w) => w.ward === ward),
    [data, ward],
  )

  if (err) return <div className="container"><h1>311 Civic Pulse</h1><p className="error">Could not load data: {err}</p></div>
  if (!data) return <div className="container"><h1>311 Civic Pulse</h1><p className="loading">Loading city data...</p></div>

  const c = data.city
  const s = c.stats
  const gen = new Date(data.generated_at)

  return (
    <div className="container">
      <header>
        <div>
          <h1>311 <span className="accent-text">Civic Pulse</span></h1>
          <p className="tagline">
            What Torontonians report, and how the city responds. Last {c.window_days} days of
            City of Toronto 311 service requests.
          </p>
        </div>
        <div className="header-meta">
          <div>Updated {gen.toLocaleString('en-CA', { dateStyle: 'medium', timeStyle: 'short' })}</div>
          <div className="dim">Source: toronto.ca/open-data</div>
        </div>
      </header>

      <Brief text={data.briefs.city} title="Plain-language brief (generated nightly by AI from the data below)" />

      <div className="stats-grid">
        <Stat label="Requests (90 days)" value={fmt(s.count)} />
        <Stat label="Completion rate" value={`${s.completion_rate}%`} />
        <Stat label="Still open" value={fmt(s.open_count)} />
        <Stat label="Oldest open" value={`${s.oldest_open_days} days`} sub={s.oldest_open_type} />
      </div>

      <section>
        <div className="section-head">
          <h2>City-wide volume</h2>
          <Trend cur={s.count} prev={c.prev_count} />
        </div>
        <Sparkline daily={s.daily} height={52} />
      </section>

      <section>
        <div className="section-head"><h2>Pick a ward</h2></div>
        <div className="chips">
          {data.wards.map((w) => (
            <WardChip key={w.ward} ward={w.ward} active={w.ward === ward} onClick={() => setWard(w.ward)} />
          ))}
        </div>

        {wardData && (
          <div className="ward-panel">
            <div className="section-head">
              <h3>{wardData.ward}</h3>
              <Trend cur={wardData.stats.count} prev={wardData.prev_count} />
            </div>
            <div className="stats-grid small">
              <Stat label="Requests" value={fmt(wardData.stats.count)} />
              <Stat label="Completion rate" value={`${wardData.stats.completion_rate}%`} />
              <Stat label="Open" value={fmt(wardData.stats.open_count)} />
              <Stat label="Oldest open" value={`${wardData.stats.oldest_open_days}d`} sub={wardData.stats.oldest_open_type} />
            </div>
            <Sparkline daily={wardData.stats.daily} height={40} />
            <Brief text={data.briefs[`ward:${wardData.ward}`]} title="AI brief" />
            <div className="top-types">
              <div className="dim">Top in this ward</div>
              <ul>
                {wardData.top_types.map((t) => (
                  <li key={t.type}>
                    <span className="tt-name">{t.type}</span>
                    <span className="tt-bar"><i style={{ width: `${(t.count / wardData.top_types[0].count) * 100}%` }} /></span>
                    <span className="tt-count">{fmt(t.count)}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </section>

      <section>
        <div className="section-head"><h2>Top categories city-wide</h2></div>
        <table className="cat-table">
          <thead>
            <tr><th>#</th><th>Category</th><th>Requests</th><th>Completed</th><th>Open</th><th>Trend</th></tr>
          </thead>
          <tbody>
            {data.categories.map((ct, i) => (
              <tr key={ct.type} className={ct.type === cat ? 'selected' : ''} onClick={() => setCat(cat === ct.type ? null : ct.type)}>
                <td className="dim">{i + 1}</td>
                <td className="cat-name">{ct.type}</td>
                <td>{fmt(ct.stats.count)}</td>
                <td>{ct.stats.completion_rate}%</td>
                <td>{fmt(ct.stats.open_count)}</td>
                <td><span className={`trend ${ct.stats.count >= (ct.prev_count || 0) ? 'up' : 'down'}`}>{ct.prev_count ? `${Math.round(((ct.stats.count - ct.prev_count) / ct.prev_count) * 1000) / 10}%` : 'new'}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
        {cat && (
          <div className="cat-panel">
            <div className="section-head"><h3>{cat}</h3></div>
            <Brief text={data.briefs[`type:${cat}`]} title="AI brief" />
          </div>
        )}
      </section>

      <section>
        <div className="section-head"><h2>Latest requests</h2></div>
        <table className="cat-table">
          <thead><tr><th>When</th><th>Ward</th><th>Request</th><th>Status</th><th>FSA</th></tr></thead>
          <tbody>
            {data.recent.map((r, i) => (
              <tr key={i}>
                <td className="dim nowrap">{timeAgo(r.when)}</td>
                <td className="dim">{r.ward.replace(/\s*\(\d+\)/, '')}</td>
                <td>{r.type}</td>
                <td><span className={`status ${r.status === 'Completed' ? 'ok' : 'open'}`}>{r.status}</span></td>
                <td className="dim">{r.fsa}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <footer>
        <p>
          Built on the City of Toronto's open 311 dataset. AI briefs are generated nightly from the
          numbers on this page - they contain no information beyond the data. Not affiliated with the
          City of Toronto.
        </p>
        <p className="dim">
          <a href="https://github.com/jpatel98/toronto-311-civic-pulse">github.com/jpatel98/toronto-311-civic-pulse</a>
        </p>
      </footer>
    </div>
  )
}

export default App
