import { useState } from 'react'

import { ApiError, fetchHistory, undoChange } from '../api'
import { EmptyState, ErrorState, Spinner } from '../components/ui'
import { formatDate } from '../lib/format'
import { requestRefresh } from '../lib/freshness'
import { useT } from '../lib/i18n'
import { useAsync } from '../lib/useAsync'

/** Every saved change, newest first, each with an undo button. */
export function HistoryPage() {
  const t = useT()
  const [nonce, setNonce] = useState(0)
  const state = useAsync((signal) => fetchHistory(signal), [nonce])
  const [error, setError] = useState<string | null>(null)

  async function onUndo(id: string) {
    setError(null)
    try {
      await undoChange(id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
    }
    setNonce((n) => n + 1)
    requestRefresh()
  }

  if (state.kind === 'loading') return <Spinner />
  if (state.kind === 'error') return <ErrorState message={state.message} onRetry={state.retry} />
  const items = state.data.items
  return (
    <div>
      <h1 className="page-title">{t('historyTitle')}</h1>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      {!items.length ? <EmptyState title={t('historyEmpty')} /> : null}
      <ul className="history-list">
        {items.map((item, i) => {
          const first = i === items.length - 1
          return (
            <li key={item.id} className="history-item">
              <div>
                <div className="card-title">{item.title}</div>
                <div className="card-meta">{formatDate(item.committed_at)}</div>
              </div>
              {item.undone ? (
                <span className="badge tone-muted">{t('undone')}</span>
              ) : first || item.undoes ? null : (
                <button className="btn" onClick={() => onUndo(item.id)}>
                  {t('undo')}
                </button>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
