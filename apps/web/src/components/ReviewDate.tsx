import { useState } from 'react'

import { ApiError, setReviewDate } from '../api'
import { requestRefresh } from '../lib/freshness'
import { useT } from '../lib/i18n'

/** YYYY-MM-DD for a date `months` from today (local time). */
export function monthsFromToday(months: number, today = new Date()): string {
  const d = new Date(today.getFullYear(), today.getMonth() + months, today.getDate())
  // Month overflow (e.g. Jan 31 + 1 month) lands on the last day of the target month.
  if (d.getDate() !== today.getDate()) d.setDate(0)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** "Reviewed → in 3 months / 1 year / clear" for one note. */
export function ReviewButtons({ id, compact = false }: { id: string; compact?: boolean }) {
  const t = useT()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [custom, setCustom] = useState('')

  async function set(until: string | null) {
    setBusy(true)
    setError(null)
    try {
      await setReviewDate(id, until)
      requestRefresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="review-buttons">
      {compact ? <span className="hint">{t('reviewDone')}</span> : null}
      <button className="btn btn-small" disabled={busy} onClick={() => void set(monthsFromToday(3))}>
        {t('review3m')}
      </button>
      <button className="btn btn-small" disabled={busy} onClick={() => void set(monthsFromToday(12))}>
        {t('review1y')}
      </button>
      {!compact ? (
        <form
          className="review-custom"
          onSubmit={(e) => {
            e.preventDefault()
            if (custom) void set(custom)
          }}
        >
          <input
            type="date"
            className="text-input"
            aria-label={t('reviewNext')}
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
          />
          <button className="btn btn-small" type="submit" disabled={busy || !custom}>
            {t('reviewSet')}
          </button>
        </form>
      ) : null}
      <button className="btn btn-small btn-quiet" disabled={busy} onClick={() => void set(null)}>
        {t('reviewClear')}
      </button>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  )
}

/** Side panel on a note: its review date and how to change it. */
export function ReviewPanel({ id, value }: { id: string; value: unknown }) {
  const t = useT()
  const current = typeof value === 'string' && value ? value : null
  const [open, setOpen] = useState(false)
  return (
    <section className="panel review-panel" aria-label={t('reviewNext')}>
      <p className="review-panel__line">
        <span className="panel-title">{t('reviewNext')}</span> · {current ?? t('reviewNone')}{' '}
        <button className="btn-link" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {open ? t('close') : t('reviewSet')}
        </button>
      </p>
      {open ? (
        <>
          <ReviewButtons id={id} />
          <p className="hint">{t('reviewHint')}</p>
        </>
      ) : null}
    </section>
  )
}
