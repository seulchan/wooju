import { useState } from 'react'

import {
  ApiError,
  challengeInsight,
  setInsightStatus,
  editNote,
  fetchDependents,
  fetchRelated,
  findNotes,
  saveTakeaway,
  fetchRecord,
  NotFoundError,
  restoreNote,
  retireNote,
} from '../api'
import { encodeId } from '../lib/paths'
import { NoteEditor } from '../components/NoteEditor'
import { ThinkPanel } from '../components/ThinkPanel'
import { requestRefresh } from '../lib/freshness'
import type { BrainRecord, Category, ProposalView, RelatedNote } from '../types'
import { titleCase } from '../lib/format'
import { extractEpistemicSections, stripLeadingH1, type EpistemicKey } from '../lib/sections'
import { Link } from '../lib/router'
import { useAsync } from '../lib/useAsync'
import { Markdown } from '../components/Markdown'
import { RecordSidebar } from '../components/RecordSidebar'
import { EmptyState, ErrorState, MetaBadge, Spinner, StatusBadge } from '../components/ui'
import { tr, pick, useT } from '../lib/i18n'

const BACK_LABEL: Partial<Record<Category, string>> = {
  knowledge: 'Knowledge',
  insight: 'Insights',
  source: 'Sources',
}

const SECTION_ROUTE: Partial<Record<Category, string>> = {
  knowledge: '/knowledge',
  insight: '/insights',
  source: '/sources',
}

const CALLOUT: Record<EpistemicKey, { label: string; tone: string }> = {
  evidence: { label: 'Supporting evidence', tone: 'callout-evidence' },
  challenge: { label: 'Challenge', tone: 'callout-challenge' },
  boundaries: { label: 'Boundaries', tone: 'callout-boundaries' },
}

export function RecordDetailPage({ id }: { id: string }) {
  const state = useAsync<BrainRecord | null>(
    async (signal) => {
      try {
        return await fetchRecord(id, signal)
      } catch (err) {
        if (err instanceof NotFoundError) return null
        throw err
      }
    },
    [id],
  )

  if (state.kind === 'loading') return <Spinner label={tr('Loading record…')} />
  if (state.kind === 'error') return <ErrorState message={state.message} onRetry={state.retry} />
  if (state.data === null) {
    return (
      <EmptyState title={tr('Record not found')}>
        {pick(`No record matches “${id}”. It may have been moved or removed.`, `“${id}” 노트가 없어요. 옮겨졌거나 지워졌을 수 있어요.`)}
      </EmptyState>
    )
  }
  return <RecordView record={state.data} />
}

function RecordView({ record }: { record: BrainRecord }) {
  const t = useT()
  const [editing, setEditing] = useState(false)
  const [retiring, setRetiring] = useState(false)
  const [dependents, setDependents] = useState<{ id: string; title: string }[]>([])
  const isInsight = record.category === 'insight'
  const back = SECTION_ROUTE[record.category] ?? '/'
  const body = stripLeadingH1(record.content, record.title)
  const sections = isInsight ? extractEpistemicSections(body) : null
  const mainBody = sections ? sections.rest : body

  return (
    <article className="detail">
      <p className="back">
        <Link to={back}>
          ← {tr(BACK_LABEL[record.category] ?? 'Home')}
        </Link>
      </p>
      <div className="title-row">
        <h1 className="page-title">{record.title}</h1>
        {!editing && record.category !== 'other' ? (
          <button className="btn btn-small" onClick={() => setEditing(true)}>
            {t('edit')}
          </button>
        ) : null}
        {!editing && !record.retired && record.category !== 'other' ? (
          <Link className="btn btn-small" to={`/new?kind=thought&ground=${encodeURIComponent(record.id)}`}>
            {t('writeThought')}
          </Link>
        ) : null}
        {!editing && !record.retired && record.category !== 'other' ? (
          <button className="btn btn-small btn-quiet" onClick={() => setRetiring(true)}>
            {t('retire')}
          </button>
        ) : null}
      </div>
      {record.retired ? <RetiredBanner record={record} /> : null}
      {!editing && record.category === 'source' && !record.retired && !/^##\s+(내 생각|My Takeaway)\s*$/m.test(record.content) ? (
        <TakeawayInline id={record.id} />
      ) : null}
      {retiring ? (
        <RetireForm
          id={record.id}
          onCancel={() => setRetiring(false)}
          onRetire={async (reason, replacedBy) => {
            await retireNote(record.id, reason, replacedBy)
            setRetiring(false)
            requestRefresh()
            fetchDependents(record.id).then((r) => setDependents(r.items), () => setDependents([]))
          }}
        />
      ) : null}
      {record.original_title ? (
        <p className="subtitle original-title">
          {tr('Original title')}: {record.original_title}
        </p>
      ) : null}
      <div className="badges">
        {isInsight ? <StatusBadge status={record.status} /> : null}
        {isInsight ? <MetaBadge label="Kind" value={titleCase(record.kind)} /> : null}
        <MetaBadge label="Type" value={titleCase(record.subtype)} />
        <MetaBadge label="Category" value={titleCase(record.category)} />
      </div>

      <div className="detail-grid">
        <div className="detail-main">
          {dependents.length ? (
            <div className="dependents" role="status">
              <p>{t('dependentsTitle')}</p>
              <ul>
                {dependents.map((d) => (
                  <li key={d.id}>
                    <Link to={`/record/${encodeId(d.id)}`}>{d.title}</Link>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {editing ? (
            <NoteEditor
              initial={record.content}
              isSource={record.category === 'source'}
              onCancel={() => setEditing(false)}
              onSave={async (body) => {
                await editNote(record.id, body, record.content)
                setEditing(false)
                requestRefresh()
                // Point at the notes that rest on this one; they are not rewritten.
                fetchDependents(record.id).then((r) => setDependents(r.items), () => setDependents([]))
              }}
            />
          ) : null}
          {!editing && sections ? (
            <div className="callouts">
              {(['evidence', 'challenge', 'boundaries'] as const).map((key) => {
                const content = sections[key]
                if (!content) return null
                return (
                  <section key={key} className={`callout ${CALLOUT[key].tone}`} aria-label={tr(CALLOUT[key].label)}>
                    <h3 className="callout-label">{tr(CALLOUT[key].label)}</h3>
                    <Markdown content={content} links={record.links} path={record.path} />
                  </section>
                )
              })}
            </div>
          ) : null}

          {editing ? null : mainBody.trim() ? (
            <Markdown content={mainBody} links={record.links} path={record.path} />
          ) : (
            <p className="subtitle">{tr('This note has no body content.')}</p>
          )}
          {!editing && !record.retired && record.category !== 'other' ? (
            <section className="think-box" aria-labelledby="think-box-heading">
              <h2 id="think-box-heading" className="section-title">
                {t('thinkBox')}
              </h2>
              <ThinkPanel id={record.id} />
              {isInsight ? <ChallengePanel id={record.id} /> : null}
              {isInsight ? <StatusControl record={record} hasChallenge={Boolean(sections?.challenge)} /> : null}
            </section>
          ) : null}
        </div>

        <RecordSidebar record={record} />
      </div>
    </article>
  )
}

/** Ask the Challenger to test this insight; the result waits in Review. */
function ChallengePanel({ id }: { id: string }) {
  const t = useT()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [made, setMade] = useState<ProposalView | null>(null)

  async function run() {
    setBusy(true)
    setError(null)
    try {
      setMade(await challengeInsight(id))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="challenge-panel" aria-label={t('challengeTitle')}>
      <h3 className="think-sub">{t('challengeTitle')}</h3>
      <p className="hint">{t('challengeIntro')}</p>
      {made ? (
        <div className="form-ok" role="status">
          <p>
            {t('challengeReady')} <strong>{made.summary}</strong>
          </p>
          <Link to="/review" className="btn btn-primary">
            {t('openReview')}
          </Link>
        </div>
      ) : (
        <button className="btn" onClick={() => void run()} disabled={busy}>
          {busy ? t('challengeWorking') : t('challengeButton')}
        </button>
      )}
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  )
}

const STATUS_MOVES: Record<string, Array<{ to: string; key: 'statusUp' | 'statusDown' }>> = {
  candidate: [{ to: 'provisional', key: 'statusUp' }],
  provisional: [
    { to: 'established', key: 'statusUp' },
    { to: 'candidate', key: 'statusDown' },
  ],
  established: [{ to: 'provisional', key: 'statusDown' }],
}

const STATUS_NAME = {
  candidate: 'statusCandidate',
  provisional: 'statusProvisional',
  established: 'statusEstablished',
} as const

/** Where this insight stands, and a one-step move up or down. */
function StatusControl({ record, hasChallenge }: { record: BrainRecord; hasChallenge: boolean }) {
  const t = useT()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const current = record.status ?? 'candidate'
  const moves = STATUS_MOVES[current] ?? []
  if (!moves.length) return null
  const name = (s: string) => (s in STATUS_NAME ? t(STATUS_NAME[s as keyof typeof STATUS_NAME]) : s)

  async function move(to: string) {
    setBusy(true)
    setError(null)
    try {
      await setInsightStatus(record.id, to)
      requestRefresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="status-control" aria-label={t('statusTitle')}>
      <h3 className="think-sub">{t('statusTitle')}</h3>
      <p>
        <strong>{name(current)}</strong> — {t(`${STATUS_NAME[current as keyof typeof STATUS_NAME] ?? 'statusCandidate'}Help` as 'statusCandidateHelp')}
      </p>
      <div className="row-actions">
        {moves.map((m) => {
          const blocked = m.to === 'provisional' && current === 'candidate' && !hasChallenge
          return (
            <button key={m.to} className="btn btn-small" disabled={busy || blocked} onClick={() => void move(m.to)}>
              {t(m.key)} {name(m.to)}
            </button>
          )
        })}
      </div>
      {current === 'candidate' && !hasChallenge ? <p className="hint">{t('statusNeedsChallenge')}</p> : null}
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  )
}

function RetiredBanner({ record }: { record: BrainRecord }) {
  const t = useT()
  const [error, setError] = useState<string | null>(null)
  const when = typeof record.metadata.retired === 'string' ? record.metadata.retired : ''
  const reason = typeof record.metadata.retired_reason === 'string' ? record.metadata.retired_reason : ''
  const replacedBy =
    typeof record.metadata.superseded_by === 'string' ? record.metadata.superseded_by.replace(/\.md$/, '') : ''
  return (
    <div className="retired-banner" role="note">
      <p>
        <strong>{t('retiredBanner')}</strong> {when ? `(${when})` : null}
        {reason ? ` — ${reason}` : null}
      </p>
      {replacedBy ? (
        <p>
          {t('retiredReplacedBy')} <Link to={`/record/${encodeId(replacedBy)}`}>{t('retiredOpenReplacement')}</Link>
        </p>
      ) : null}
      <button
        className="btn btn-small"
        onClick={() =>
          void restoreNote(record.id).then(
            () => requestRefresh(),
            (err: unknown) => setError(err instanceof ApiError ? err.message : String(err)),
          )
        }
      >
        {t('restore')}
      </button>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  )
}

function RetireForm({
  id,
  onRetire,
  onCancel,
}: {
  id: string
  onRetire: (reason: string, replacedBy: string | null) => Promise<unknown>
  onCancel: () => void
}) {
  const t = useT()
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [replacement, setReplacement] = useState<string | null>(null)
  return (
    <form
      className="retire-form"
      onSubmit={(e) => {
        e.preventDefault()
        setBusy(true)
        setError(null)
        onRetire(reason, replacement).catch((err: unknown) => {
          setError(err instanceof ApiError ? err.message : String(err))
          setBusy(false)
        })
      }}
    >
      <p>
        <strong>{t('retireTitle')}</strong>
      </p>
      <p className="hint">{t('retireHint')}</p>
      <input
        className="text-input"
        aria-label={t('retireReason')}
        placeholder={t('retireReasonPlaceholder')}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      <ReplacementPicker id={id} value={replacement} onChange={setReplacement} />
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="card-actions">
        <button className="btn btn-primary" type="submit" disabled={busy || !reason.trim()}>
          {t('retireConfirm')}
        </button>
        <button className="btn" type="button" disabled={busy} onClick={onCancel}>
          {t('cancel')}
        </button>
      </div>
    </form>
  )
}

/**
 * Optionally, the note that takes this one's place. Notes close in meaning are
 * offered first (the likeliest replacements); any other note can be searched.
 */
function ReplacementPicker({
  id,
  value,
  onChange,
}: {
  id: string
  value: string | null
  onChange: (id: string | null) => void
}) {
  const t = useT()
  const [query, setQuery] = useState('')
  const [found, setFound] = useState<RelatedNote[]>([])
  const related = useAsync((signal) => fetchRelated(id, signal), [id])
  const suggested = related.kind === 'ready' ? related.data.similar.slice(0, 4) : []
  const options = [...suggested, ...found.filter((f) => !suggested.some((s) => s.id === f.id))].filter(
    (n) => n.id !== id,
  )

  async function search(q: string) {
    setQuery(q)
    if (q.trim().length < 2) return setFound([])
    try {
      const r = await findNotes(q)
      setFound(r.hits.slice(0, 5).map((h) => ({ id: h.id, title: h.title, category: h.category })))
    } catch {
      setFound([])
    }
  }

  return (
    <fieldset className="replacement">
      <legend>{t('retireReplacement')}</legend>
      <label className="check-row">
        <input type="radio" name="replacement" checked={value === null} onChange={() => onChange(null)} />{' '}
        {t('retireNoReplacement')}
      </label>
      {options.map((n) => (
        <label key={n.id} className="check-row">
          <input type="radio" name="replacement" checked={value === n.id} onChange={() => onChange(n.id)} />{' '}
          {n.title}
        </label>
      ))}
      <input
        className="text-input"
        aria-label={t('retireFindReplacement')}
        placeholder={t('retireFindReplacement')}
        value={query}
        onChange={(e) => void search(e.target.value)}
      />
    </fieldset>
  )
}

/** A source without the user's own line yet: a quiet place to add one. */
function TakeawayInline({ id }: { id: string }) {
  const t = useT()
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  return (
    <form
      className="takeaway takeaway-inline"
      onSubmit={(e) => {
        e.preventDefault()
        if (!text.trim()) return
        saveTakeaway(id, text).then(
          () => requestRefresh(),
          (err: unknown) => setError(err instanceof ApiError ? err.message : String(err)),
        )
      }}
    >
      <input
        className="text-input"
        aria-label={t('takeawayLabel')}
        placeholder={t('takeawayLabel')}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <button className="btn btn-small" type="submit" disabled={!text.trim()}>
        {t('save')}
      </button>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  )
}
