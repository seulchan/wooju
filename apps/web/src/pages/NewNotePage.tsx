import { useEffect, useRef, useState, type FormEvent } from 'react'

import { ApiError, createNote, fetchRecord, fetchSkeleton, searchBrain, type NoteKind } from '../api'
import { requestRefresh } from '../lib/freshness'
import { useT } from '../lib/i18n'
import { encodeId } from '../lib/paths'
import { navigate } from '../lib/router'

const KINDS: { kind: NoteKind; label: string; hint: string }[] = [
  { kind: 'thought', label: 'kindThought', hint: 'kindHintThought' },
  { kind: 'concept', label: 'kindConcept', hint: 'kindHintConcept' },
  { kind: 'overview', label: 'kindOverview', hint: 'kindHintOverview' },
  { kind: 'question', label: 'kindQuestion', hint: 'kindHintQuestion' },
  { kind: 'how-to', label: 'kindHowTo', hint: 'kindHintHowTo' },
  { kind: 'mental-model', label: 'kindMentalModel', hint: 'kindHintMentalModel' },
]
const INSIGHT_KINDS = [
  ['hypothesis', 'ikHypothesis'],
  ['connection', 'ikConnection'],
  ['pattern', 'ikPattern'],
  ['implication', 'ikImplication'],
  ['tension', 'ikTension'],
] as const

type Ground = { id: string; title: string }

/** Write a note in your own words; Wooju supplies only the form. */
export function NewNotePage({ kind: initialKind = '', ground = '' }: { kind?: string; ground?: string }) {
  const t = useT()
  const start = KINDS.some((k) => k.kind === initialKind) ? (initialKind as NoteKind) : ground ? 'thought' : 'concept'
  const [kind, setKind] = useState<NoteKind>(start)
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const touched = useRef(false)
  const [grounds, setGrounds] = useState<Ground[]>([])
  const [insightKind, setInsightKind] = useState('hypothesis')
  const [recall, setRecall] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Start from the kind's headings, unless the user already wrote something.
  useEffect(() => {
    if (touched.current) return
    fetchSkeleton(kind).then(
      (r) => {
        if (!touched.current) setBody(r.body)
      },
      () => undefined,
    )
  }, [kind])

  // Opened from a note ("Write a thought from this"): it is the first ground.
  useEffect(() => {
    if (!ground) return
    fetchRecord(ground).then(
      (r) => setGrounds((g) => (g.some((x) => x.id === r.id) ? g : [...g, { id: r.id, title: r.title }])),
      () => undefined,
    )
  }, [ground])

  async function save(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const { id } = await createNote({
        kind,
        title,
        body,
        grounds: grounds.map((g) => g.id),
        insight_kind: kind === 'thought' ? insightKind : undefined,
        recall,
      })
      requestRefresh()
      navigate(`/record/${encodeId(id)}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
      setBusy(false)
    }
  }

  const current = KINDS.find((k) => k.kind === kind)!
  return (
    <form className="new-note" onSubmit={save}>
      <h1 className="page-title">{t('newNoteTitle')}</h1>
      <p className="subtitle">{t('newNoteIntro')}</p>
      <div className="segmented" role="radiogroup" aria-label={t('newNoteTitle')}>
        {KINDS.map((k) => (
          <button
            key={k.kind}
            type="button"
            role="radio"
            aria-checked={kind === k.kind}
            className={`chip ${kind === k.kind ? 'chip-active' : ''}`}
            onClick={() => setKind(k.kind)}
          >
            {t(k.label as never)}
          </button>
        ))}
      </div>
      <p className="hint">{t(current.hint as never)}</p>

      <input
        className="text-input new-note__title"
        aria-label={t('noteTitle')}
        placeholder={t('noteTitle')}
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />

      {kind === 'thought' ? (
        <>
          <GroundPicker grounds={grounds} onChange={setGrounds} />
          <label className="field">
            <span>{t('insightKind')}</span>
            <select className="text-input" value={insightKind} onChange={(e) => setInsightKind(e.target.value)}>
              {INSIGHT_KINDS.map(([value, label]) => (
                <option key={value} value={value}>
                  {t(label)}
                </option>
              ))}
            </select>
          </label>
        </>
      ) : null}

      <textarea
        className="note-editor__text"
        aria-label={t('edit')}
        value={body}
        rows={14}
        onChange={(e) => {
          touched.current = true
          setBody(e.target.value)
        }}
      />
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      <label className="check">
        <input type="checkbox" checked={recall} onChange={(e) => setRecall(e.target.checked)} />{' '}
        {t('recallOnNew')}
      </label>
      <div className="card-actions">
        <button
          className="btn btn-primary"
          type="submit"
          disabled={busy || !title.trim() || (kind === 'thought' && !grounds.length)}
        >
          {t('save')}
        </button>
      </div>
    </form>
  )
}

function GroundPicker({ grounds, onChange }: { grounds: Ground[]; onChange: (g: Ground[]) => void }) {
  const t = useT()
  const [query, setQuery] = useState('')
  const [found, setFound] = useState<Ground[]>([])

  useEffect(() => {
    const q = query.trim()
    if (!q) {
      setFound([])
      return
    }
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      searchBrain(q, { limit: '8' }, controller.signal).then(
        (r) => setFound(r.hits.map((h) => ({ id: h.id, title: h.title }))),
        () => undefined,
      )
    }, 250)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [query])

  return (
    <fieldset className="grounds">
      <legend>{t('grounds')}</legend>
      {grounds.length ? (
        <ul className="ground-chips">
          {grounds.map((g) => (
            <li key={g.id} className="chip chip-active">
              {g.title}{' '}
              <button
                type="button"
                className="btn-link"
                aria-label={`${t('remove')} ${g.title}`}
                onClick={() => onChange(grounds.filter((x) => x.id !== g.id))}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <input
        className="text-input"
        type="search"
        aria-label={t('groundsSearch')}
        placeholder={t('groundsSearch')}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {found.length ? (
        <ul className="ground-results">
          {found
            .filter((f) => !grounds.some((g) => g.id === f.id))
            .map((f) => (
              <li key={f.id}>
                <span>{f.title}</span>
                <button type="button" className="btn btn-small" onClick={() => onChange([...grounds, f])}>
                  {t('add')}
                </button>
              </li>
            ))}
        </ul>
      ) : null}
    </fieldset>
  )
}
