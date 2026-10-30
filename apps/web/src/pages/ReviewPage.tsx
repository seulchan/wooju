import { useState } from 'react'

import { ApiError, approveProposal, approveProposals, editProposal, fetchProposals, rejectProposal } from '../api'
import { NoteEditor } from '../components/NoteEditor'
import { Markdown } from '../components/Markdown'
import { Badge, EmptyState, ErrorState, Spinner } from '../components/ui'
import { requestRefresh } from '../lib/freshness'
import { useT, type StringKey } from '../lib/i18n'
import { useAsync } from '../lib/useAsync'
import type { DiffLine, ProposalView, Via } from '../types'

/** Approval cards: what agents propose and the user has not decided yet. */
export function ReviewPage() {
  const t = useT()
  const [nonce, setNonce] = useState(0)
  const state = useAsync((signal) => fetchProposals('pending', signal), [nonce])
  const [error, setError] = useState<string | null>(null)

  async function act(fn: () => Promise<unknown>) {
    setError(null)
    try {
      await fn()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
    }
    setNonce((n) => n + 1)
    requestRefresh()
  }

  if (state.kind === 'loading') return <Spinner />
  if (state.kind === 'error') return <ErrorState message={state.message} onRetry={state.retry} />
  const items = state.data.items
  const batchable = items.filter((p) => p.approval !== 'individual')

  return (
    <div>
      <h1 className="page-title">{t('reviewTitle')}</h1>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      {!items.length ? <EmptyState title={t('reviewEmpty')} /> : null}
      {batchable.length > 1 ? (
        <button className="btn btn-primary" onClick={() => act(() => approveProposals(batchable.map((p) => p.id)))}>
          {t('approveAll')} ({batchable.length})
        </button>
      ) : null}
      <ul className="card-list">
        {items.map((p) => (
          <ProposalCard
            key={p.id}
            proposal={p}
            onApprove={() => act(() => approveProposal(p.id))}
            onReject={() => act(() => rejectProposal(p.id))}
            onEdit={(body) => editProposal(p.id, body).then(() => setNonce((n) => n + 1))}
          />
        ))}
      </ul>
    </div>
  )
}

const FRONTMATTER = /^---[\s\S]*?\n---\n/

function ProposalCard({
  proposal,
  onApprove,
  onReject,
  onEdit,
}: {
  proposal: ProposalView
  onApprove: () => void
  onReject: () => void
  onEdit: (body: string) => Promise<unknown>
}) {
  const t = useT()
  const diffs = proposal.changes.filter((c) => c.diff && c.diff.length)
  // A change to an existing note shows its diff; a new note shows its text.
  // Either way the reviewer sees the change itself, not only the AI's summary.
  const [open, setOpen] = useState(!diffs.length)
  const [editing, setEditing] = useState(false)
  const body = (proposal.preview ?? '').replace(FRONTMATTER, '').replace(/^\n+/, '')
  const editable = proposal.changes.some((c) => c.op === 'write' && c.path.endsWith('.md'))
  return (
    <li className="card proposal-card">
      <div className="card-title">{proposal.title}</div>
      {proposal.summary ? <p className="card-excerpt">{proposal.summary}</p> : null}
      {proposal.via ? (
        <p className="proposal-from" aria-label={t('proposalFrom')}>
          {t(VIA_LABEL[proposal.via])}
          {proposal.source ? <span className="hint"> · {proposal.source}</span> : null}
        </p>
      ) : null}
      {proposal.flags?.length ? (
        <div className="answer-warning proposal-flags" role="alert">
          <p>{t('proposalFlags')}</p>
          {proposal.flags.map((f) => (
            <blockquote key={f} className="citation-quote">
              {f}
            </blockquote>
          ))}
        </div>
      ) : null}
      {!editing && diffs.length ? (
        <section className="proposal-diffs" aria-label={t('proposalChanges')}>
          {diffs.map((c) => (
            <Diff key={c.path} path={c.path} lines={c.diff ?? []} />
          ))}
        </section>
      ) : null}
      <div className="card-meta">
        <Badge tone={proposal.approval === 'individual' ? 'tone-warn' : 'tone-neutral'}>
          {proposal.approval === 'individual' ? t('needsYou') : t('canBatch')}
        </Badge>
      </div>
      <div className="card-actions">
        <button className="btn btn-primary" onClick={onApprove}>
          {t('approve')}
        </button>
        <button className="btn" onClick={onReject}>
          {t('reject')}
        </button>
        {editable && !editing ? (
          <button className="btn" onClick={() => setEditing(true)}>
            {t('edit')}
          </button>
        ) : null}
        {proposal.preview ? (
          <button className="btn-link" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            {open ? t('hideDetail') : diffs.length ? t('proposalWhole') : t('showDetail')}
          </button>
        ) : null}
      </div>
      {editing ? (
        <NoteEditor
          initial={body}
          isSource={proposal.changes.some((c) => c.path.startsWith('sources/'))}
          onCancel={() => setEditing(false)}
          onSave={async (next) => {
            await onEdit(next)
            setEditing(false)
            setOpen(true)
          }}
        />
      ) : null}
      {!editing && open && proposal.preview ? (
        <div className="proposal-preview">
          <ul className="proposal-paths">
            {proposal.changes.map((c) => (
              <li key={c.op + c.path}>
                <code>{c.op}</code> {c.path}
              </li>
            ))}
          </ul>
          <Markdown content={body} />
        </div>
      ) : null}
    </li>
  )
}

const VIA_LABEL: Record<Via, StringKey> = {
  you: 'viaYou',
  app: 'viaApp',
  icloud: 'viaIcloud',
  telegram: 'viaTelegram',
  claude: 'viaClaude',
  wooju: 'viaWooju',
}

/** What a change does to an existing note: removed lines, then added ones. */
function Diff({ path, lines }: { path: string; lines: DiffLine[] }) {
  return (
    <div className="diff">
      <div className="diff-path">
        <code>{path}</code>
      </div>
      <pre className="diff-lines">
        {lines.map((l, i) =>
          l.kind === 'gap' ? (
            <span key={i} className="diff-gap">
              {'⋯\n'}
            </span>
          ) : (
            <span key={i} className={`diff-${l.kind}`}>
              {(l.kind === 'add' ? '+ ' : l.kind === 'remove' ? '− ' : '  ') + l.text + '\n'}
            </span>
          ),
        )}
      </pre>
    </div>
  )
}
