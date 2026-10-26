import { useMemo, useState } from 'react'

import { fetchKnowledge } from '../api'
import { encodeId } from '../lib/paths'
import { titleCase } from '../lib/format'
import { useAsync } from '../lib/useAsync'
import { EmptyState, ErrorState, Spinner } from '../components/ui'
import { FilterChip } from '../components/FilterChip'
import { RecordListItem } from '../components/RecordListItem'
import { tr, pick } from '../lib/i18n'

export function KnowledgePage() {
  const knowledge = useAsync((signal) => fetchKnowledge(undefined, signal), [])
  const [subtype, setSubtype] = useState<string>('all')

  const subtypes = useMemo(() => {
    if (knowledge.kind !== 'ready') return []
    const seen = new Map<string, string>()
    for (const item of knowledge.data.items) {
      if (item.subtype && !seen.has(item.subtype)) seen.set(item.subtype, titleCase(item.subtype) ?? item.subtype)
    }
    return [...seen.entries()].map(([key, label]) => ({ key, label }))
  }, [knowledge])

  if (knowledge.kind === 'loading') return <Spinner label={tr('Loading knowledge…')} />
  if (knowledge.kind === 'error') return <ErrorState message={knowledge.message} onRetry={knowledge.retry} />

  const items = knowledge.data.items
  const filtered = subtype === 'all' ? items : items.filter((i) => i.subtype === subtype)

  return (
    <>
      <h1 className="page-title">{tr('Knowledge')}</h1>
      <p className="subtitle">{tr('Durable wiki notes — concepts, overviews, models, and how-tos.')}</p>

      {subtypes.length > 0 ? (
        <div className="filters" role="group" aria-label="Filter by subtype">
          <FilterChip label={tr('All')} pressed={subtype === 'all'} onClick={() => setSubtype('all')} />
          {subtypes.map((s) => (
            <FilterChip
              key={s.key}
              label={s.label}
              pressed={subtype === s.key}
              onClick={() => setSubtype(s.key)}
            />
          ))}
        </div>
      ) : null}

      {items.length === 0 ? (
        <EmptyState title={tr('No knowledge notes')}>
          {pick('Nothing indexed under wiki/ yet.', '위에서 파일을 넣으면 Wooju가 정리해서 여기에 모아 줘요.')}
        </EmptyState>
      ) : filtered.length === 0 ? (
        <EmptyState title={tr('No notes for this filter')} />
      ) : (
        <div className="card-list">
          {filtered.map((item) => (
            <RecordListItem key={item.id} item={item} to={`/knowledge/${encodeId(item.id)}`} />
          ))}
        </div>
      )}
    </>
  )
}
