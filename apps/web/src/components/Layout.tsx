import { useState, type FormEvent, type ReactNode } from 'react'

import { fetchHealth } from '../api'
import type { HealthResponse } from '../types'
import { Link, navigate, routeSection, type Route } from '../lib/router'
import { useAsync, type LoadState } from '../lib/useAsync'

type HealthState = LoadState<HealthResponse>

const NAV: ReadonlyArray<{ section: 'home' | 'knowledge' | 'insights' | 'sources'; label: string; to: string }> = [
  { section: 'home', label: 'Home', to: '/' },
  { section: 'knowledge', label: 'Knowledge', to: '/knowledge' },
  { section: 'insights', label: 'Insights', to: '/insights' },
  { section: 'sources', label: 'Sources', to: '/sources' },
]

export function Layout({ route, children }: { route: Route; children: ReactNode }) {
  const active = routeSection(route)
  const health = useAsync((signal) => fetchHealth(signal), [])
  const [query, setQuery] = useState('')

  function onSearch(e: FormEvent) {
    e.preventDefault()
    const q = query.trim()
    navigate(q ? `/search?q=${encodeURIComponent(q)}` : '/search')
  }

  const banner = healthBanner(health)

  return (
    <div className="app">
      <header className="header">
        <div className="header-row">
          <Link to="/" className="brand">
            Wooju Brain
          </Link>
          <nav className="nav" aria-label="Primary">
            {NAV.map((item) => (
              <Link
                key={item.section}
                to={item.to}
                className="nav-item"
                aria-current={active === item.section ? 'page' : undefined}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <form className="search" role="search" onSubmit={onSearch}>
            <input
              type="search"
              name="q"
              className="search-input"
              placeholder="Search the Brain…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search the Brain"
            />
            <button className="btn search-btn" type="submit">
              Search
            </button>
          </form>
          <HealthChip health={health} />
        </div>
        {banner ? <div className={`banner banner-${banner.tone}`}>{banner.text}</div> : null}
      </header>

      <main className="main">{children}</main>

      <footer className="footer">
        <span>Read-only view · the Brain is never modified</span>
      </footer>
    </div>
  )
}

function HealthChip({ health }: { health: HealthState }) {
  if (health.kind === 'loading') return <span className="health health-unknown" title="Checking backend">·</span>
  if (health.kind === 'error')
    return (
      <span className="health health-err" title={health.message}>
        Offline
      </span>
    )
  const { data } = health
  if (data.status === 'ok')
    return (
      <span className="health health-ok" title={data.message}>
        Brain ready
      </span>
    )
  return (
    <span className="health health-warn" title={data.message}>
      Not configured
    </span>
  )
}

/** A calm, dismissible-free banner shown only when something needs attention. */
function healthBanner(health: HealthState): { tone: string; text: string } | null {
  if (health.kind === 'error') {
    return { tone: 'err', text: 'Backend unavailable. Start the API (uvicorn on :8000) and it will reconnect.' }
  }
  if (health.kind === 'ready' && health.data.status !== 'ok') {
    return { tone: 'warn', text: health.data.message }
  }
  return null
}
