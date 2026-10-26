import { useState, type FormEvent } from 'react'

import { searchBrain } from '../api'
import { encodeId } from '../lib/paths'
import { titleCase } from '../lib/format'
import { navigate, Link } from '../lib/router'
import { useAsync } from '../lib/useAsync'
import type { Category, SearchHit, SearchResponse } from '../types'
import { EmptyState, ErrorState, MetaBadge, Spinner, StatusBadge } from '../components/ui'

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
      <h1 className="page-title">Search</h1>
      <form className="search search-page" role="search" onSubmit={onSubmit}>
        <input
          type="search"
          name="q"
          className="search-input"
          placeholder="Search titles, aliases, and note text…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          autoFocus
          aria-label="Search query"
        />
        <button className="btn search-btn" type="submit">
          Search
        </button>
      </form>

      {!q.trim() ? (
        <EmptyState title="Search the Brain">Full-text search across every indexed note.</EmptyState>
      ) : results.kind === 'loading' ? (
        <Spinner label="Searching…" />
      ) : results.kind === 'error' ? (
        <ErrorState message={results.message} onRetry={results.retry} />
      ) : results.data.total === 0 ? (
        <EmptyState title="No results">
          No notes matched “{q}”. Try different or fewer terms.
        </EmptyState>
      ) : (
        <p className="subtitle">{results.data.total} match{results.data.total === 1 ? '' : 'es'} for “{q}”</p>
      )}

      {results.kind === 'ready' &&
        BUCKETS.map((bucket) => {
          const hits = results.data.hits.filter((h) => bucket.cats.includes(h.category))
          if (hits.length === 0) return null
          return (
            <section key={bucket.title} className="section">
              <h2 className="section-title">
                {bucket.title} <span className="count">({hits.length})</span>
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
