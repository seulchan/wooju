import { useCallback, useEffect, useRef, useState, type DragEvent } from 'react'

import { ApiError, fetchJobs, uploadFiles } from '../api'
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
    const timer = window.setInterval(() => {
      void refresh().then(() => requestRefresh())
    }, 1500)
    return () => window.clearInterval(timer)
  }, [active, refresh])

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
          accept=".pdf,.txt,.md,.markdown,.html,.htm"
          data-testid="file-input"
          onChange={(e) => {
            void send(Array.from(e.target.files ?? []))
            e.target.value = ''
          }}
        />
      </div>
      {notes.map((n) => (
        <p key={n} className="form-error" role="alert">
          {n}
        </p>
      ))}
      {jobs.length ? (
        <ul className="job-list">
          {jobs.slice(0, 8).map((job) => (
            <li key={job.id} className={`job job-${job.state}`}>
              <span className="job-file">{job.file.replace(/^inbox\//, '')}</span>
              <span className="job-state">{label[job.state]}</span>
              {job.message ? <span className="job-message">{job.message}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}
