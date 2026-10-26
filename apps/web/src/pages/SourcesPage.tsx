import { fetchSources } from '../api'
import { encodeId } from '../lib/paths'
import { useAsync } from '../lib/useAsync'
import { EmptyState, ErrorState, Spinner } from '../components/ui'
import { RecordListItem } from '../components/RecordListItem'

export function SourcesPage() {
  const sources = useAsync((signal) => fetchSources(signal), [])

  if (sources.kind === 'loading') return <Spinner label="Loading sources…" />
  if (sources.kind === 'error') return <ErrorState message={sources.message} onRetry={sources.retry} />

  const items = sources.data.items
  if (items.length === 0) {
    return (
      <EmptyState title="No sources">
        No source notes indexed under <code>sources/</code> or <code>library/</code>.
      </EmptyState>
    )
  }

  return (
    <>
      <h1 className="page-title">Sources</h1>
      <p className="subtitle">Source notes from <code>sources/</code> and <code>library/</code>.</p>
      <div className="card-list">
        {items.map((item) => (
          <RecordListItem key={item.id} item={item} to={`/sources/${encodeId(item.id)}`} />
        ))}
      </div>
    </>
  )
}
