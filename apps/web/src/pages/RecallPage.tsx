import { useState } from 'react'

import { ApiError, fetchAttention, fetchRecord, recallNote, type RecallRating } from '../api'
import { Markdown } from '../components/Markdown'
import { ErrorState, Spinner } from '../components/ui'
import { requestRefresh } from '../lib/freshness'
import { useT } from '../lib/i18n'
import { encodeId } from '../lib/paths'
import { Link, navigate } from '../lib/router'
import { stripLeadingH1 } from '../lib/sections'
import { useAsync } from '../lib/useAsync'

/**
 * Recall before reading: the title only, a box for what the user remembers,
 * then the note to compare, then how well it went (which spaces the next time).
 */
export function RecallPage({ id }: { id: string }) {
  const t = useT()
  const state = useAsync((signal) => fetchRecord(id, signal), [id])
  const [mine, setMine] = useState('')
  const [revealed, setRevealed] = useState(false)
  const [next, setNext] = useState<string | null>(null)
  const [nextId, setNextId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (state.kind === 'loading') return <Spinner />
  if (state.kind === 'error') return <ErrorState message={state.message} onRetry={state.retry} />
  const record = state.data

  async function rate(rating: RecallRating) {
    setError(null)
    try {
      const result = await recallNote(id, rating)
      setNext(result.next)
      requestRefresh()
      const attention = await fetchAttention()
      const due = attention.groups.find((g) => g.key === 'review_due')
      setNextId(due?.items.find((item) => item.id !== id)?.id ?? null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    }
  }

  return (
    <article className="recall">
      <p className="hint">{t('recallTitle')}</p>
      <h1 className="page-title">{record.title}</h1>

      {!revealed ? (
        <>
          <p>{t('recallPrompt')}</p>
          <textarea
            className="note-editor__text"
            aria-label={t('recallMine')}
            rows={6}
            value={mine}
            onChange={(e) => setMine(e.target.value)}
          />
          <div className="card-actions">
            <button className="btn btn-primary" onClick={() => setRevealed(true)}>
              {t('recallReveal')}
            </button>
            {!mine.trim() ? (
              <button className="btn btn-quiet" onClick={() => setRevealed(true)}>
                {t('recallBlank')}
              </button>
            ) : null}
          </div>
        </>
      ) : (
        <>
          {mine.trim() ? (
            <section className="recall-mine" aria-label={t('recallMine')}>
              <h2 className="subsection-title">{t('recallMine')}</h2>
              <p className="recall-mine__text">{mine}</p>
            </section>
          ) : null}
          <section className="recall-note">
            <Markdown content={stripLeadingH1(record.content, record.title)} links={record.links} path={record.path} />
          </section>
          {next ? (
            <div className="form-ok" role="status">
              <p>
                {t('recallScheduled')} <strong>{next}</strong>
              </p>
              <div className="card-actions">
                {nextId ? (
                  <button className="btn btn-primary" onClick={() => navigate(`/recall/${encodeId(nextId)}`)}>
                    {t('recallNext')}
                  </button>
                ) : null}
                <Link className="btn" to="/">
                  {t('recallHome')}
                </Link>
              </div>
            </div>
          ) : (
            <div className="recall-rate">
              <p>{t('recallHow')}</p>
              <div className="card-actions">
                <button className="btn btn-primary" onClick={() => void rate('good')}>
                  {t('recallGood')}
                </button>
                <button className="btn" onClick={() => void rate('partial')}>
                  {t('recallPartial')}
                </button>
                <button className="btn" onClick={() => void rate('poor')}>
                  {t('recallPoor')}
                </button>
              </div>
            </div>
          )}
          {error ? (
            <p className="form-error" role="alert">
              {error}
            </p>
          ) : null}
        </>
      )}
    </article>
  )
}
