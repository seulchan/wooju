import { useState, type FormEvent, type ReactNode } from 'react'

import { fetchHealth } from '../api'
import type { HealthResponse } from '../types'
import { tr, useT } from '../lib/i18n'
import { Link, navigate, routeSection, type Route, type Section } from '../lib/router'
import { useAsync, type LoadState } from '../lib/useAsync'

type HealthState = LoadState<HealthResponse>

const NAV: ReadonlyArray<{ section: Section; label: string; to: string }> = [
  { section: 'home', label: 'Home', to: '/' },
  { section: 'knowledge', label: 'Knowledge', to: '/knowledge' },
  { section: 'insights', label: 'Insights', to: '/insights' },
  { section: 'sources', label: 'Sources', to: '/sources' },
]

export function Layout({ route, children }: { route: Route; children: ReactNode }) {
  const active = routeSection(route)
  const t = useT()
  const nav = [
    ...NAV,
    { section: 'review' as const, label: t('review'), to: '/review' },
    { section: 'history' as const, label: t('history'), to: '/history' },
    { section: 'settings' as const, label: t('settings'), to: '/settings' },
  ]
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
            Wooju
          </Link>
          <nav className="nav" aria-label="Primary">
            {nav.map((item) => (
              <Link
                key={item.section}
                to={item.to}
                className="nav-item"
                aria-current={active === item.section ? 'page' : undefined}
              >
                {tr(item.label)}
              </Link>
            ))}
          </nav>
          <form className="search" role="search" onSubmit={onSearch}>
            <input
              type="search"
              name="q"
              className="search-input"
              placeholder={tr('Search the Brain…')}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label={tr('Search the Brain')}
            />
            <button className="btn search-btn" type="submit">
              {tr('Search')}
            </button>
          </form>
          <HealthChip health={health} />
        </div>
        {banner ? <div className={`banner banner-${banner.tone}`}>{banner.text}</div> : null}
      </header>

      <main className="main">{children}</main>

      <footer className="footer">
        <span>{t('footer')}</span>
      </footer>
    </div>
  )
}

function HealthChip({ health }: { health: HealthState }) {
  if (health.kind === 'loading') return <span className="health health-unknown" title={tr('Checking backend')}>·</span>
  if (health.kind === 'error')
    return (
      <span className="health health-err" title={health.message}>
        {tr('Offline')}
      </span>
    )
  const { data } = health
  if (data.status === 'ok')
    return (
      <span className="health health-ok" title={data.message}>
        {tr('Brain ready')}
      </span>
    )
  return (
    <span className="health health-warn" title={data.message}>
      {tr('Not configured')}
    </span>
  )
}

/** A calm, dismissible-free banner shown only when something needs attention. */
function healthBanner(health: HealthState): { tone: string; text: string } | null {
  if (health.kind === 'error') {
    return { tone: 'err', text: tr("Can't reach Wooju's server. Reopen the app if this continues.") }
  }
  if (health.kind === 'ready' && health.data.status !== 'ok') {
    return { tone: 'warn', text: health.data.message }
  }
  return null
}
