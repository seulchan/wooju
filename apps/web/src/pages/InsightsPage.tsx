import { useMemo, useState } from 'react'

import { fetchInsights } from '../api'
import { encodeId } from '../lib/paths'
import { statusMeta, titleCase } from '../lib/format'
import { useAsync } from '../lib/useAsync'
import { EmptyState, ErrorState, Spinner } from '../components/ui'
import { FilterChip } from '../components/FilterChip'
import { RecordListItem } from '../components/RecordListItem'
import { tr, pick } from '../lib/i18n'

export function InsightsPage() {
  const insights = useAsync((signal) => fetchInsights(undefined, undefined, signal), [])
  const [status, setStatus] = useState<string>('all')
  const [kind, setKind] = useState<string>('all')

  const { statuses, kinds } = useMemo(() => {
    if (insights.kind !== 'ready') return { statuses: [], kinds: [] }
    const s = new Map<string, string>()
    const k = new Map<string, string>()
    for (const item of insights.data.items) {
      if (item.status && !s.has(item.status)) {
        const meta = statusMeta(item.status)
        s.set(item.status, meta ? meta.label : item.status)
      }
      if (item.kind && !k.has(item.kind)) k.set(item.kind, titleCase(item.kind) ?? item.kind)
    }
    return {
      statuses: [...s.entries()].map(([key, label]) => ({ key, label })),
      kinds: [...k.entries()].map(([key, label]) => ({ key, label })),
    }
  }, [insights])

  if (insights.kind === 'loading') return <Spinner label={tr('Loading insights…')} />
  if (insights.kind === 'error') return <ErrorState message={insights.message} onRetry={insights.retry} />

  const items = insights.data.items
  const filtered = items.filter(
    (i) => (status === 'all' || i.status === status) && (kind === 'all' || i.kind === kind),
  )

  return (
    <>
      <h1 className="page-title">{tr('Insights')}</h1>
      <p className="subtitle">
        {pick(
          'Derived notes (marked origin: synthesis). Status is read verbatim — established is never inferred.',
          '여러 노트를 엮어 Wooju가 찾아낸 연결이에요. 상태는 노트에 적힌 그대로 보여 줘요.',
        )}
      </p>

      <div className="filters" role="group" aria-label="Filter by status">
        <span className="filter-label">{tr('Status')}</span>
        <FilterChip label={tr('All')} pressed={status === 'all'} onClick={() => setStatus('all')} />
        {statuses.map((s) => (
          <FilterChip key={s.key} label={s.label} pressed={status === s.key} onClick={() => setStatus(s.key)} />
        ))}
      </div>

      {kinds.length > 0 ? (
        <div className="filters" role="group" aria-label="Filter by kind">
          <span className="filter-label">{tr('Kind')}</span>
          <FilterChip label={tr('All')} pressed={kind === 'all'} onClick={() => setKind('all')} />
          {kinds.map((k) => (
            <FilterChip key={k.key} label={k.label} pressed={kind === k.key} onClick={() => setKind(k.key)} />
          ))}
        </div>
      ) : null}

      {items.length === 0 ? (
        <EmptyState title={tr('No insights')}>
          {pick(
            'No notes are marked as derived synthesis. Insights are shown separately from knowledge.',
            '아직 Wooju가 찾아낸 연결이 없어요.',
          )}
        </EmptyState>
      ) : filtered.length === 0 ? (
        <EmptyState title={tr('No insights for these filters')} />
      ) : (
        <div className="card-list">
          {filtered.map((item) => (
            <RecordListItem key={item.id} item={item} to={`/insights/${encodeId(item.id)}`} />
          ))}
        </div>
      )}
    </>
  )
}
