import { fetchSources } from '../api'
import { encodeId } from '../lib/paths'
import { useAsync } from '../lib/useAsync'
import { EmptyState, ErrorState, Spinner } from '../components/ui'
import { RecordListItem } from '../components/RecordListItem'
import { tr, pick } from '../lib/i18n'

export function SourcesPage() {
  const sources = useAsync((signal) => fetchSources(signal), [])

  if (sources.kind === 'loading') return <Spinner label={tr('Loading sources…')} />
  if (sources.kind === 'error') return <ErrorState message={sources.message} onRetry={sources.retry} />

  const items = sources.data.items
  if (items.length === 0) {
    return (
      <EmptyState title={tr('No sources')}>
        {pick(
          'No source notes indexed under sources/ or library/.',
          '홈에서 파일을 넣으면 정리된 자료가 여기에 모여요.',
        )}
      </EmptyState>
    )
  }

  return (
    <>
      <h1 className="page-title">{tr('Sources')}</h1>
      <p className="subtitle">
        {pick('Source notes from sources/ and library/.', '넣은 자료를 정리한 노트예요. 원본은 함께 보관돼요.')}
      </p>
      <div className="card-list">
        {items.map((item) => (
          <RecordListItem key={item.id} item={item} to={`/sources/${encodeId(item.id)}`} />
        ))}
      </div>
    </>
  )
}
