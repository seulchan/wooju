import { fetchRecord, NotFoundError } from '../api'
import type { BrainRecord, Category } from '../types'
import { titleCase } from '../lib/format'
import { extractEpistemicSections, stripLeadingH1, type EpistemicKey } from '../lib/sections'
import { Link } from '../lib/router'
import { useAsync } from '../lib/useAsync'
import { Markdown } from '../components/Markdown'
import { RecordSidebar } from '../components/RecordSidebar'
import { EmptyState, ErrorState, MetaBadge, Spinner, StatusBadge } from '../components/ui'

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

  if (state.kind === 'loading') return <Spinner label="Loading record…" />
  if (state.kind === 'error') return <ErrorState message={state.message} onRetry={state.retry} />
  if (state.data === null) {
    return (
      <EmptyState title="Record not found">
        No record matches “{id}”. It may have been moved or removed.
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
        <Link to={back}>← Back to {titleCase(record.category) ?? 'list'}</Link>
      </p>
      <h1 className="page-title">{record.title}</h1>
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
                  <section key={key} className={`callout ${CALLOUT[key].tone}`} aria-label={CALLOUT[key].label}>
                    <h3 className="callout-label">{CALLOUT[key].label}</h3>
                    <Markdown content={content} links={record.links} />
                  </section>
                )
              })}
            </div>
          ) : null}

          {mainBody.trim() ? (
            <Markdown content={mainBody} links={record.links} />
          ) : (
            <p className="subtitle">This note has no body content.</p>
          )}
        </div>

        <RecordSidebar record={record} />
      </div>
    </article>
  )
}
