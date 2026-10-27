import { lazy, Suspense, useEffect, useRef, useState } from 'react'

import { ApiError, addSamples, fetchChanges, fetchOverview, fetchUiState, updateUiState } from '../api'
import { useAsync } from '../lib/useAsync'
import { Link } from '../lib/router'
import { changesSince, isFirstVisit, type PeriodId } from '../lib/periods'
import { EmptyState, ErrorState, Spinner } from '../components/ui'
import { AttentionSection } from '../components/AttentionSection'
import { HomeChanges } from '../components/HomeChanges'
import { DropZone } from '../components/DropZone'
import { RecentMemos } from '../components/RecentMemos'
import { tr, useT } from '../lib/i18n'
import { requestRefresh } from '../lib/freshness'

const BrainMap = lazy(() =>
  import('../components/BrainMap').then(({ BrainMap: BrainMapComponent }) => ({
    default: BrainMapComponent,
  })),
)

/** Nothing in the Brain yet: offer a few sample notes to look around with. */
function SampleOffer() {
  const t = useT()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function add() {
    setBusy(true)
    setError(null)
    try {
      await addSamples()
      requestRefresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
      setBusy(false)
    }
  }
  return (
    <section className="sample-offer">
      <p>{t('samplesIntro')}</p>
      <button className="btn" disabled={busy} onClick={() => void add()}>
        {busy ? t('samplesAdding') : t('samplesAdd')}
      </button>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  )
}

export function HomePage() {
  const overview = useAsync((signal) => fetchOverview(signal), [])
  const uiState = useAsync((signal) => fetchUiState(signal), [])
  const [period, setPeriod] = useState<PeriodId>('sinceLastVisit')

  const lastSeenAt = uiState.kind === 'ready' ? (uiState.data.last_seen_at ?? null) : null
  const changes = useAsync(
    (signal) => fetchChanges(changesSince(period, lastSeenAt), signal),
    [period, lastSeenAt],
  )

  // Update UI-local last_seen_at only after the current state has loaded
  // successfully (overview + the selected period's changes + ui-state). The
  // disposable `known` id snapshot is rebuilt so the next visit can tell
  // newly-created records from modified ones.
  const finalizedRef = useRef(false)
  useEffect(() => {
    if (finalizedRef.current) return
    if (overview.kind !== 'ready' || changes.kind !== 'ready' || uiState.kind !== 'ready') return
    finalizedRef.current = true
    const sessionStart = new Date().toISOString()
    void (async () => {
      try {
        const all = await fetchChanges(null)
        await updateUiState({ last_seen_at: sessionStart, known: all.items.map((i) => i.id) })
      } catch {
        // Still record the visit even if the snapshot capture fails.
        try {
          await updateUiState({ last_seen_at: sessionStart })
        } catch {
          // UI-state persistence is best effort and must never become an
          // unhandled rejection after the page has unmounted.
        }
      }
    })()
  }, [overview.kind, changes.kind, uiState.kind])

  if (overview.kind === 'loading') return <Spinner label={tr('Loading Brain summary…')} />
  if (overview.kind === 'error') return <ErrorState message={overview.message} onRetry={overview.retry} />

  const { knowledge, insight, source, main_areas: mainAreas } = overview.data
  // The template's own docs count in `total`; what matters is the user's notes.
  if (knowledge + insight + source === 0) {
    return (
      <>
        <DropZone />
        <RecentMemos />
        <EmptyState title={tr('Your Brain is empty')}>
          {tr('Drop a file above to add your first note.')}
        </EmptyState>
        <SampleOffer />
      </>
    )
  }

  const tiles = [
    { label: 'Knowledge', count: knowledge, to: '/knowledge' },
    { label: 'Insights', count: insight, to: '/insights' },
    { label: 'Sources', count: source, to: '/sources' },
  ]

  const firstVisit = isFirstVisit(period, lastSeenAt)

  return (
    <>
      <h1 className="page-title">Brain</h1>

      <DropZone />
      <RecentMemos />

      {/* Period-independent: attention reflects the Brain's *current* uncertainty
          (provisional/candidate insights, open questions, explicit contested
          claims, unresolved refs), not only recent changes. */}
      <section aria-labelledby="attention-heading" className="section">
        <h2 id="attention-heading" className="section-title">
          {tr('What needs attention?')}
        </h2>
        <AttentionSection />
      </section>

      <section className="section section-first" aria-labelledby="know-heading">
        <h2 id="know-heading" className="section-title">
          {tr('What do I know?')}
        </h2>
        <div className="tiles" aria-label="Brain summary">
          {tiles.map((t) => (
            <Link key={t.label} to={t.to} className="tile">
              <span className="tile-count">{t.count}</span>
              <span className="tile-label">{tr(t.label)}</span>
            </Link>
          ))}
        </div>
        {mainAreas.length > 0 ? (
          <p className="main-areas">
            <span className="main-areas__label">{tr('Main areas')}</span>
            {mainAreas.map((a) => (
              <span key={a.label} className="main-areas__area">
                {a.label}
              </span>
            ))}
          </p>
        ) : null}
      </section>
      <HomeChanges
        period={period}
        changes={changes}
        firstVisit={firstVisit}
        onPeriodChange={setPeriod}
      />

      <section aria-labelledby="connected-heading" className="section">
        <h2 id="connected-heading" className="section-title">
          {tr('What is connected?')}
        </h2>
        {/* The map reuses the "What changed?" period window so recent-change
            highlighting tracks the same selection the user made above. */}
        <details className="map-toggle">
          <summary>{tr('Show map')}</summary>
          <Suspense fallback={<Spinner label={tr('Loading map…')} />}>
            <BrainMap since={changesSince(period, lastSeenAt)} />
          </Suspense>
        </details>
      </section>

    </>
  )
}
