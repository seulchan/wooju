import { Fragment, useEffect, useState, type FormEvent, type ReactNode } from 'react'

import { ApiError, askBrainStreaming, askPreview, type AskAnswer, type AskCitation } from '../api'
import { Badge } from '../components/ui'
import { titleCase } from '../lib/format'
import { useT } from '../lib/i18n'
import { encodeId } from '../lib/paths'
import { Link } from '../lib/router'

// Answers from this app session, newest first. Kept outside the component so
// they survive moving to another page and back; not saved anywhere.
let earlier: AskAnswer[] = []

/** Ask a question in plain words; the answer cites the user's own notes. */
export function AskPage({ initial = '' }: { initial?: string }) {
  const t = useT()
  const [question, setQuestion] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [answers, setAnswers] = useState<AskAnswer[]>(earlier)
  const [reading, setReading] = useState<{ id: string; title: string }[]>([])
  // The answer so far, while the AI is still writing it.
  const [draft, setDraft] = useState<AskAnswer | null>(null)

  async function submit(q: string) {
    const text = q.trim()
    if (!text || busy) return
    setBusy(true)
    setError(null)
    setReading([])
    // Show the notes being read right away; the answer takes longer.
    askPreview(text).then(
      (r) => setReading(r.items),
      () => undefined,
    )
    setDraft(null)
    try {
      const answer = await askBrainStreaming(text, setDraft)
      earlier = [answer, ...earlier].slice(0, 20)
      setAnswers(earlier)
      setQuestion('')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setBusy(false)
      setReading([])
      setDraft(null)
    }
  }

  useEffect(() => {
    if (initial.trim()) void submit(initial)
    // Only once, for a question passed in the address (#/ask?q=...).
  }, [])

  const [latest, ...rest] = answers
  return (
    <div className="ask">
      <h1 className="page-title">{t('askTitle')}</h1>
      <p className="subtitle">{t('askIntro')}</p>
      <form
        className="ask-form"
        onSubmit={(e: FormEvent) => {
          e.preventDefault()
          void submit(question)
        }}
      >
        <textarea
          className="ask-input"
          aria-label={t('askTitle')}
          placeholder={t('askPlaceholder')}
          value={question}
          rows={2}
          maxLength={1000}
          disabled={busy}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault()
              void submit(question)
            }
          }}
        />
        <button className="btn btn-primary" type="submit" disabled={busy || !question.trim()}>
          {t('askButton')}
        </button>
      </form>
      {busy ? (
        <div className="ask-thinking" role="status">
          <p>
            <span className="spinner-dot" aria-hidden="true" />{' '}
            {draft?.checking_originals ? t('askCheckingOriginals') : draft ? t('askWriting') : t('askThinking')}
          </p>
          {reading.length && !draft ? (
            <p className="hint">
              {t('askReading')}:{' '}
              {reading.map((r, i) => (
                <span key={r.id}>
                  {i ? ' · ' : ''}
                  <Link to={`/record/${encodeId(r.id)}`}>{r.title}</Link>
                </span>
              ))}
            </p>
          ) : null}
        </div>
      ) : null}
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      {draft ? <AnswerCard answer={draft} /> : latest ? <AnswerCard answer={latest} /> : null}
      {rest.length ? (
        <section className="section">
          <h2 className="section-title">{t('askEarlier')}</h2>
          {rest.map((a, i) => (
            <AnswerCard key={`${a.question}-${i}`} answer={a} compact />
          ))}
        </section>
      ) : null}
    </div>
  )
}

function AnswerCard({ answer, compact = false }: { answer: AskAnswer; compact?: boolean }) {
  const t = useT()
  const byN = new Map(answer.citations.map((c) => [c.n, c]))
  return (
    <article className={`answer ${compact ? 'answer-compact' : ''}`} aria-label={answer.question}>
      <h2 className="answer-question">{answer.question}</h2>
      {!answer.answer ? (
        <p className="answer-empty">{t('askNothing')}</p>
      ) : (
        <>
          {answer.related_only ? (
            <p className="answer-warning">{t('askUnchecked')}</p>
          ) : answer.missing ? (
            <p className="answer-warning">
              {t('askPartial')} {answer.missing}
            </p>
          ) : null}
          <div className="answer-text">{renderAnswer(answer.answer, byN)}</div>
        </>
      )}
      {answer.citations.length ? (
        <section className="answer-sources" aria-label={t('askBasedOn')}>
          <h3 className="subsection-title">{answer.related_only ? t('askRelated') : t('askBasedOn')}</h3>
          <ol className="citation-list">
            {answer.citations.map((c) => (
              <li key={c.n} id={`cite-${c.n}`} className="citation">
                <span className="citation-n">{c.n}</span>
                <div>
                  <Link to={`/record/${encodeId(c.id)}`} className="citation-title">
                    {c.title}
                  </Link>
                  {c.heading ? <span className="hint"> · {c.heading}</span> : null}{' '}
                  <Badge tone="tone-neutral">{titleCase(c.category)}</Badge>
                  {!compact ? <p className="citation-excerpt">{c.excerpt}</p> : null}
                </div>
              </li>
            ))}
          </ol>
          {!compact ? <p className="hint">{t('askCheck')}</p> : null}
        </section>
      ) : null}
      {answer.original_answer ? <FromOriginals answer={answer} compact={compact} /> : null}
      {!answer.original_answer && answer.original_missing && !compact ? (
        <p className="hint">
          {t('askOriginalsStill')} {answer.original_missing}
        </p>
      ) : null}
    </article>
  )
}

/** The part the notes left open, answered from the originals: shown apart,
 *  with the original's own sentences, because no note vouches for it. */
function FromOriginals({ answer, compact }: { answer: AskAnswer; compact: boolean }) {
  const t = useT()
  const cited = answer.original_citations ?? []
  const byN = new Map(cited.map((c) => [c.n, c]))
  return (
    <section className="answer-originals" aria-label={t('askFromOriginals')}>
      <h3 className="subsection-title">{t('askFromOriginals')}</h3>
      <p className="answer-warning">{t('askFromOriginalsNote')}</p>
      <div className="answer-text">{renderAnswer(answer.original_answer ?? '', byN)}</div>
      {answer.original_missing ? (
        <p className="hint">
          {t('askOriginalsStill')} {answer.original_missing}
        </p>
      ) : null}
      {!compact ? (
        <ol className="citation-list">
          {cited.map((c) => (
            <li key={c.n} className="citation">
              <span className="citation-n">{c.n}</span>
              <div>
                <Link to={`/record/${encodeId(c.id)}`} className="citation-title">
                  {c.title}
                </Link>{' '}
                <Badge tone="tone-warn">{t('askOriginalBadge')}</Badge>
                <blockquote className="citation-quote">{c.excerpt}</blockquote>
              </div>
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  )
}

/** Plain text with [n] markers turned into links to the cited note. */
function renderAnswer(text: string, byN: Map<number, AskCitation>): ReactNode {
  const lines = text.split(/\n+/).filter((l) => l.trim())
  return lines.map((line, i) => {
    const bullet = /^\s*[-*•]\s+/.test(line)
    const body = line.replace(/^\s*[-*•]\s+/, '')
    const parts = body.split(/(\[\d+\])/g).map((part, j) => {
      const m = /^\[(\d+)\]$/.exec(part)
      const c = m ? byN.get(Number(m[1])) : undefined
      if (!c) return <Fragment key={j}>{part}</Fragment>
      return (
        <Link key={j} to={`/record/${encodeId(c.id)}`} className="cite" title={c.title}>
          {c.n}
        </Link>
      )
    })
    return bullet ? (
      <p key={i} className="answer-bullet">
        • {parts}
      </p>
    ) : (
      <p key={i}>{parts}</p>
    )
  })
}
