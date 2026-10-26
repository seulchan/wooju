import { useState, type FormEvent } from 'react'

import { searchBrain } from '../api'
import { encodeId } from '../lib/paths'
import { titleCase } from '../lib/format'
import { navigate, Link } from '../lib/router'
import { useAsync } from '../lib/useAsync'
import type { Category, SearchHit, SearchResponse } from '../types'
import { EmptyState, ErrorState, MetaBadge, Spinner, StatusBadge } from '../components/ui'
import { tr, pick } from '../lib/i18n'

const EMPTY: SearchResponse = { query: '', total: 0, hits: [] }

const BUCKETS: ReadonlyArray<{ title: string; cats: ReadonlyArray<Category> }> = [
  { title: 'Knowledge', cats: ['knowledge'] },
  { title: 'Insights', cats: ['insight'] },
  { title: 'Sources', cats: ['source'] },
  { title: 'Memory / Projects / Areas', cats: ['memory', 'project', 'area', 'other'] },
]

function detailPath(hit: SearchHit): string {
  const id = encodeId(hit.id)
  if (hit.category === 'knowledge') return `/knowledge/${id}`
  if (hit.category === 'insight') return `/insights/${id}`
  if (hit.category === 'source') return `/sources/${id}`
  return `/record/${id}`
}

export function SearchPage({ q }: { q: string }) {
  const [input, setInput] = useState(q)
  const results = useAsync(
    async (signal) => (q.trim() ? searchBrain(q, {}, signal) : EMPTY),
    [q],
  )

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    const term = input.trim()
    navigate(term ? `/search?q=${encodeURIComponent(term)}` : '/search')
  }

  return (
    <>
      <h1 className="page-title">{tr('Search')}</h1>
      <form className="search search-page" role="search" onSubmit={onSubmit}>
        <input
          type="search"
          name="q"
          className="search-input"
          placeholder={tr('Search titles, aliases, and note text…')}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          autoFocus
          aria-label="Search query"
        />
        <button className="btn search-btn" type="submit">
          {tr('Search')}
        </button>
      </form>

      {!q.trim() ? (
        <EmptyState title={tr('Search the Brain')}>{tr('Full-text search across every indexed note.')}</EmptyState>
      ) : results.kind === 'loading' ? (
        <Spinner label={tr('Searching…')} />
      ) : results.kind === 'error' ? (
        <ErrorState message={results.message} onRetry={results.retry} />
      ) : results.data.total === 0 ? (
        <EmptyState title={tr('No results')}>
          {pick(`No notes matched “${q}”. Try different or fewer terms.`, `“${q}”와 맞는 노트가 없어요. 다른 낱말로 찾아 보세요.`)}
        </EmptyState>
      ) : (
        <p className="subtitle">
          {pick(
            `${results.data.total} match${results.data.total === 1 ? '' : 'es'} for “${q}”`,
            `“${q}” 검색 결과 ${results.data.total}개`,
          )}
        </p>
      )}

      {results.kind === 'ready' &&
        BUCKETS.map((bucket) => {
          const hits = results.data.hits.filter((h) => bucket.cats.includes(h.category))
          if (hits.length === 0) return null
          return (
            <section key={bucket.title} className="section">
              <h2 className="section-title">
                {tr(bucket.title)} <span className="count">({hits.length})</span>
              </h2>
              <div className="card-list">
                {hits.map((hit) => (
                  <article className="card" key={hit.id}>
                    <h3 className="card-title">
                      <Link to={detailPath(hit)}>{hit.title}</Link>
                    </h3>
                    <div className="card-meta">
                      <StatusBadge status={hit.status} />
                      {hit.category === 'insight' ? (
                        <MetaBadge label="Kind" value={titleCase(hit.kind)} />
                      ) : (
                        <MetaBadge label="Type" value={titleCase(hit.subtype)} />
                      )}
                    </div>
                    {hit.snippet ? <p className="card-excerpt">{hit.snippet}</p> : null}
                  </article>
                ))}
              </div>
            </section>
          )
        })}
    </>
  )
}
