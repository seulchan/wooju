import { useCallback, useEffect, useRef, useState, type DragEvent } from 'react'

import { ApiError, captureText, fetchJobs, removeJob, retryJob, saveTakeaway, uploadFiles } from '../api'
import { requestRefresh } from '../lib/freshness'
import { useT } from '../lib/i18n'
import type { Job } from '../types'

/** Drag files in (or pick them). Shows each file's progress until it is saved. */
export function DropZone() {
  const t = useT()
  const [jobs, setJobs] = useState<Job[]>([])
  const [over, setOver] = useState(false)
  const [notes, setNotes] = useState<string[]>([])
  const input = useRef<HTMLInputElement>(null)
  const [text, setText] = useState('')
  const [saved, setSaved] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function sendText() {
    if (!text.trim() || busy) return
    setBusy(true)
    setNotes([])
    setSaved(null)
    try {
      const result = await captureText(text)
      setSaved(
        result.kind === 'memo'
          ? t('memoSaved')
          : result.duplicate
            ? `${t('alreadySaved')} ${result.title ?? ''}`
            : t('linkSaved'),
      )
      setText('')
      requestRefresh()
    } catch (err) {
      setNotes([err instanceof ApiError ? err.message : String(err)])
    } finally {
      setBusy(false)
    }
    await refresh()
  }

  const refresh = useCallback(async () => {
    try {
      const items = (await fetchJobs()).items
      setJobs(Array.isArray(items) ? items : [])
    } catch {
      /* the health banner already reports a missing backend */
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const active = jobs.some((j) => j.state === 'queued' || j.state === 'working' || j.state === 'waiting')
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => void refresh(), 2000)
    return () => window.clearInterval(timer)
  }, [active, refresh])

  // Reload the rest of the page only when a file finishes, not on every check.
  const finished = jobs.filter((j) => j.state === 'done' || j.state === 'failed').length
  const lastFinished = useRef(finished)
  useEffect(() => {
    if (finished > lastFinished.current) requestRefresh()
    lastFinished.current = finished
  }, [finished])

  async function send(files: File[]) {
    if (!files.length) return
    setNotes([])
    try {
      const result = await uploadFiles(files)
      setNotes(result.refused.map((r) => r.message))
    } catch (err) {
      setNotes([err instanceof ApiError ? err.message : 'Something went wrong.'])
    }
    await refresh()
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setOver(false)
    void send(Array.from(e.dataTransfer.files))
  }

  const label: Record<Job['state'], string> = {
    queued: t('queued'),
    working: t('working'),
    waiting: t('waiting'),
    done: t('done'),
    failed: t('failed'),
  }

  return (
    <section className="section section-first" aria-label={t('dropTitle')}>
      <div
        className={`dropzone${over ? ' dropzone-over' : ''}`}
        data-testid="dropzone"
        onDragOver={(e) => {
          e.preventDefault()
          setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
      >
        <strong>{t('dropTitle')}</strong>
        <p>{t('dropBody')}</p>
        <button className="btn" onClick={() => input.current?.click()}>
          {t('choose')}
        </button>
        <input
          ref={input}
          type="file"
          multiple
          hidden
          accept=".pdf,.txt,.md,.markdown,.html,.htm,.webloc,.url"
          data-testid="file-input"
          onChange={(e) => {
            void send(Array.from(e.target.files ?? []))
            e.target.value = ''
          }}
        />
      </div>
      <form
        className="capture-form"
        onSubmit={(e) => {
          e.preventDefault()
          void sendText()
        }}
      >
        <textarea
          className="ask-input"
          aria-label={t('captureLabel')}
          placeholder={t('capturePlaceholder')}
          rows={2}
          value={text}
          disabled={busy}
          onChange={(e) => setText(e.target.value)}
        />
        <button className="btn" type="submit" disabled={busy || !text.trim()}>
          {busy ? t('working') : t('captureSave')}
        </button>
      </form>
      {saved ? (
        <p className="form-ok" role="status">
          {saved}
        </p>
      ) : null}
      {notes.map((n) => (
        <p key={n} className="form-error" role="alert">
          {n}
        </p>
      ))}
      <TakeawayBox jobs={jobs} />
      {jobs.length ? (
        <ul className="job-list">
          {jobs.slice(0, 8).map((job) => (
            <li key={job.id} className={`job job-${job.state}`}>
              <span className="job-file">{job.file.replace(/^inbox\//, '')}</span>
              <span className="job-state">{label[job.state]}</span>
              {job.message ? <span className="job-message">{job.message}</span> : null}
              {job.state === 'failed' ? (
                <span className="job-actions">
                  <button
                    className="btn btn-small"
                    onClick={() => void retryJob(job.id).then(refresh, () => refresh())}
                  >
                    {t('retry')}
                  </button>
                  <button
                    className="btn btn-small btn-quiet"
                    onClick={() => void removeJob(job.id).then(refresh, () => refresh())}
                  >
                    {t('remove')}
                  </button>
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}

/** After a source is saved: one sentence in the user's own words (optional). */
function TakeawayBox({ jobs }: { jobs: Job[] }) {
  const t = useT()
  const [done, setDone] = useState<Set<string>>(new Set())
  const [text, setText] = useState('')
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const job = jobs.find((j) => j.state === 'done' && j.note_id && !done.has(j.id))
  if (saved && !job) {
    return (
      <p className="form-ok" role="status">
        {t('takeawaySaved')}
      </p>
    )
  }
  if (!job || !job.note_id) return null
  const noteId = job.note_id
  const close = () => {
    setDone((d) => new Set(d).add(job.id))
    setText('')
  }
  return (
    <form
      className="takeaway"
      onSubmit={(e) => {
        e.preventDefault()
        if (!text.trim()) return
        saveTakeaway(noteId, text).then(
          () => {
            setSaved(true)
            close()
          },
          (err: unknown) => setError(err instanceof ApiError ? err.message : String(err)),
        )
      }}
    >
      <p>{t('takeawayPrompt')}</p>
      <p className="hint">{job.title ?? job.file}</p>
      <input
        className="text-input"
        aria-label={t('takeawayLabel')}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="card-actions">
        <button className="btn btn-primary" type="submit" disabled={!text.trim()}>
          {t('save')}
        </button>
        <button className="btn btn-quiet" type="button" onClick={close}>
          {t('skip')}
        </button>
      </div>
    </form>
  )
}
