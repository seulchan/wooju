import { useState } from 'react'

import { ApiError } from '../api'
import { useT } from '../lib/i18n'

/**
 * Plain-text editor for a note's body. The header (dates, source, status) is
 * not shown and never changes; only what the user reads is edited.
 */
export function NoteEditor({
  initial,
  isSource,
  onSave,
  onCancel,
}: {
  initial: string
  isSource: boolean
  onSave: (body: string) => Promise<unknown>
  onCancel: () => void
}) {
  const t = useT()
  const [body, setBody] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function save() {
    setBusy(true)
    setError(null)
    try {
      await onSave(body)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
      setBusy(false)
    }
  }

  return (
    <div className="note-editor">
      <p className="hint">{isSource ? t('editSourceHint') : t('editHint')}</p>
      <textarea
        className="note-editor__text"
        aria-label={t('edit')}
        value={body}
        rows={Math.min(30, Math.max(8, body.split('\n').length + 2))}
        onChange={(e) => setBody(e.target.value)}
      />
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="card-actions">
        <button className="btn btn-primary" disabled={busy || body === initial || !body.trim()} onClick={() => void save()}>
          {t('save')}
        </button>
        <button className="btn" disabled={busy} onClick={onCancel}>
          {t('cancel')}
        </button>
      </div>
    </div>
  )
}
