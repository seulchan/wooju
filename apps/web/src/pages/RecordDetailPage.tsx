import { useState } from 'react'

import { ApiError, challengeInsight, fetchRecord, NotFoundError } from '../api'
import type { BrainRecord, Category, ProposalView } from '../types'
import { titleCase } from '../lib/format'
import { extractEpistemicSections, stripLeadingH1, type EpistemicKey } from '../lib/sections'
import { Link } from '../lib/router'
import { useAsync } from '../lib/useAsync'
import { Markdown } from '../components/Markdown'
import { RecordSidebar } from '../components/RecordSidebar'
import { EmptyState, ErrorState, MetaBadge, Spinner, StatusBadge } from '../components/ui'
import { tr, pick, useT } from '../lib/i18n'

const SECTION_ROUTE: Partial<Record<Category, string>> = {
  knowledge: '/knowledge',
  insight: '/insights',
  source: '/sources',
}

const CALLOUT: Record<EpistemicKey, { label: string; tone: string }> = {
  evidence: { label: 'Supporting evidence', tone: 'callout-evidence' },
  challenge: { label: 'Challenge', tone: 'callout-challenge' },
  boundaries: { label: 'Boundaries', tone: 'callout-boundaries' },
}

export function RecordDetailPage({ id }: { id: string }) {
  const state = useAsync<BrainRecord | null>(
    async (signal) => {
      try {
        return await fetchRecord(id, signal)
      } catch (err) {
        if (err instanceof NotFoundError) return null
        throw err
      }
    },
    [id],
  )

  if (state.kind === 'loading') return <Spinner label={tr('Loading record…')} />
  if (state.kind === 'error') return <ErrorState message={state.message} onRetry={state.retry} />
  if (state.data === null) {
    return (
      <EmptyState title={tr('Record not found')}>
        {pick(`No record matches “${id}”. It may have been moved or removed.`, `“${id}” 노트가 없어요. 옮겨졌거나 지워졌을 수 있어요.`)}
      </EmptyState>
    )
  }
  return <RecordView record={state.data} />
}

function RecordView({ record }: { record: BrainRecord }) {
  const isInsight = record.category === 'insight'
  const back = SECTION_ROUTE[record.category] ?? '/'
  const body = stripLeadingH1(record.content, record.title)
  const sections = isInsight ? extractEpistemicSections(body) : null
  const mainBody = sections ? sections.rest : body

  return (
    <article className="detail">
      <p className="back">
        <Link to={back}>
          {pick(`← Back to ${titleCase(record.category) ?? 'list'}`, `← ${titleCase(record.category) ?? '목록'}(으)로`)}
        </Link>
      </p>
      <h1 className="page-title">{record.title}</h1>
      {record.original_title ? (
        <p className="subtitle original-title">
          {tr('Original title')}: {record.original_title}
        </p>
      ) : null}
      <div className="badges">
        {isInsight ? <StatusBadge status={record.status} /> : null}
        {isInsight ? <MetaBadge label="Kind" value={titleCase(record.kind)} /> : null}
        <MetaBadge label="Type" value={titleCase(record.subtype)} />
        <MetaBadge label="Category" value={titleCase(record.category)} />
      </div>

      <div className="detail-grid">
        <div className="detail-main">
          {sections ? (
            <div className="callouts">
              {(['evidence', 'challenge', 'boundaries'] as const).map((key) => {
                const content = sections[key]
                if (!content) return null
                return (
                  <section key={key} className={`callout ${CALLOUT[key].tone}`} aria-label={tr(CALLOUT[key].label)}>
                    <h3 className="callout-label">{tr(CALLOUT[key].label)}</h3>
                    <Markdown content={content} links={record.links} path={record.path} />
                  </section>
                )
              })}
            </div>
          ) : null}

          {mainBody.trim() ? (
            <Markdown content={mainBody} links={record.links} path={record.path} />
          ) : (
            <p className="subtitle">{tr('This note has no body content.')}</p>
          )}
          {isInsight ? <ChallengePanel id={record.id} /> : null}
        </div>

        <RecordSidebar record={record} />
      </div>
    </article>
  )
}

/** Ask the Challenger to test this insight; the result waits in Review. */
function ChallengePanel({ id }: { id: string }) {
  const t = useT()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [made, setMade] = useState<ProposalView | null>(null)

  async function run() {
    setBusy(true)
    setError(null)
    try {
      setMade(await challengeInsight(id))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="challenge-panel" aria-label={t('challengeTitle')}>
      <h2 className="section-title">{t('challengeTitle')}</h2>
      <p className="hint">{t('challengeIntro')}</p>
      {made ? (
        <div className="form-ok" role="status">
          <p>
            {t('challengeReady')} <strong>{made.summary}</strong>
          </p>
          <Link to="/review" className="btn btn-primary">
            {t('openReview')}
          </Link>
        </div>
      ) : (
        <button className="btn" onClick={() => void run()} disabled={busy}>
          {busy ? t('challengeWorking') : t('challengeButton')}
        </button>
      )}
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  )
}
