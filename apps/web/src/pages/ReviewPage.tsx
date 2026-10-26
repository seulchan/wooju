import { useState } from 'react'

import { ApiError, approveProposal, approveProposals, fetchProposals, rejectProposal } from '../api'
import { Markdown } from '../components/Markdown'
import { Badge, EmptyState, ErrorState, Spinner } from '../components/ui'
import { requestRefresh } from '../lib/freshness'
import { useT } from '../lib/i18n'
import { useAsync } from '../lib/useAsync'
import type { ProposalView } from '../types'

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
          />
        ))}
      </ul>
    </div>
  )
}

function ProposalCard({
  proposal,
  onApprove,
  onReject,
}: {
  proposal: ProposalView
  onApprove: () => void
  onReject: () => void
}) {
  const t = useT()
  const [open, setOpen] = useState(false)
  return (
    <li className="card proposal-card">
      <div className="card-title">{proposal.title}</div>
      {proposal.summary ? <p className="card-excerpt">{proposal.summary}</p> : null}
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
        {proposal.preview ? (
          <button className="btn-link" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            {open ? t('hideDetail') : t('showDetail')}
          </button>
        ) : null}
      </div>
      {open && proposal.preview ? (
        <div className="proposal-preview">
          <ul className="proposal-paths">
            {proposal.changes.map((c) => (
              <li key={c.op + c.path}>
                <code>{c.op}</code> {c.path}
              </li>
            ))}
          </ul>
          <Markdown content={proposal.preview.replace(/^---[\s\S]*?\n---\n/, '')} />
        </div>
      ) : null}
    </li>
  )
}
