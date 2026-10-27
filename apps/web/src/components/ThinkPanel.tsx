import { useState } from 'react'

import { ApiError, createNote, fetchQuestions, saveReflection, type ThinkQuestion } from '../api'
import { requestRefresh } from '../lib/freshness'
import { useT } from '../lib/i18n'
import { encodeId } from '../lib/paths'
import { Link } from '../lib/router'
import { Badge } from './ui'

const KIND_LABEL = { why: 'thinkKindWhy', connect: 'thinkKindConnect', limits: 'thinkKindLimits' } as const

/** On demand: the AI asks two or three questions about a note; the user answers. */
export function ThinkPanel({ id }: { id: string }) {
  const t = useT()
  const [questions, setQuestions] = useState<ThinkQuestion[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(0)

  async function load() {
    setBusy(true)
    setError(null)
    try {
      setQuestions((await fetchQuestions(id)).questions)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="think-panel" aria-label={t('thinkTitle')}>
      <h2 className="section-title">{t('thinkTitle')}</h2>
      <p className="hint">{t('thinkIntro')}</p>
      {questions?.length ? (
        <ul className="think-list">
          {questions.map((q) => (
            <QuestionItem
              key={q.text}
              noteId={id}
              question={q}
              onSaved={() => {
                setQuestions((qs) => (qs ?? []).filter((x) => x.text !== q.text))
                setSaved((n) => n + 1)
                requestRefresh()
              }}
            />
          ))}
        </ul>
      ) : null}
      {questions && !questions.length && !saved ? <p className="hint">{t('thinkNone')}</p> : null}
      {saved ? (
        <p className="form-ok" role="status">
          {t('thinkSaved')}
        </p>
      ) : null}
      <button className="btn" disabled={busy} onClick={() => void load()}>
        {busy ? t('thinkWorking') : questions ? t('thinkMore') : t('thinkAsk')}
      </button>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  )
}

function QuestionItem({
  noteId,
  question,
  onSaved,
}: {
  noteId: string
  question: ThinkQuestion
  onSaved: () => void
}) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const [answer, setAnswer] = useState('')
  const [title, setTitle] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function run(fn: () => Promise<unknown>) {
    setError(null)
    try {
      await fn()
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    }
  }

  const related = question.related
  return (
    <li className="think-item">
      <p>
        <Badge tone="tone-neutral">{t(KIND_LABEL[question.kind])}</Badge> {question.text}
        {related ? (
          <>
            {' '}
            <Link to={`/record/${encodeId(related.id)}`}>{related.title}</Link>
          </>
        ) : null}
      </p>
      {!open ? (
        <button className="btn btn-small" onClick={() => setOpen(true)}>
          {t('thinkAnswer')}
        </button>
      ) : (
        <div className="think-answer">
          <textarea
            className="note-editor__text"
            aria-label={t('thinkMyAnswer')}
            rows={4}
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
          />
          {related ? (
            <input
              className="text-input"
              aria-label={t('thinkThoughtTitle')}
              placeholder={t('thinkThoughtTitle')}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          ) : null}
          <div className="card-actions">
            <button
              className="btn btn-primary"
              disabled={!answer.trim()}
              onClick={() => void run(() => saveReflection(noteId, question.text, answer))}
            >
              {t('thinkKeep')}
            </button>
            {related ? (
              <button
                className="btn"
                disabled={!answer.trim() || !title.trim()}
                onClick={() =>
                  void run(() =>
                    createNote({
                      kind: 'thought',
                      title,
                      body: `## Insight\n\n${answer.trim()}\n`,
                      grounds: [noteId, related.id],
                      insight_kind: 'connection',
                    }),
                  )
                }
              >
                {t('thinkAsThought')}
              </button>
            ) : null}
          </div>
          {error ? (
            <p className="form-error" role="alert">
              {error}
            </p>
          ) : null}
        </div>
      )}
    </li>
  )
}
