/**
 * Home "What needs attention?" section (Phase 4).
 *
 * Surfaces only uncertainty the Brain already represents — provisional/candidate
 * insights, open questions, explicit `epistemic.status: contested` claims, and
 * unresolved `derived_from`/wikilink references. The UI invents no confidence,
 * quality, or conflict: a single source, an old timestamp, or wording
 * differences are never treated as weak/stale/conflicting. Status tone is
 * supplementary; a label is always shown (never color-only).
 *
 * Period-independent: this reflects the Brain's *current* uncertainty, not only
 * recent changes, so it fetches once and does not depend on the period selector.
 *
 * Compact layout: a one-line count summary first, then a short representative
 * list (a few items drawn across the reasons) rather than a full card per group.
 */

import { fetchAttention, markChecked } from '../api'
import { requestRefresh } from '../lib/freshness'
import { encodeId } from '../lib/paths'
import { useAsync } from '../lib/useAsync'
import { Link } from '../lib/router'
import { EmptyState, ErrorState, Spinner } from './ui'
import type { AttentionGroup, AttentionGroupKey, AttentionItem } from '../types'
import { tr, pick, useT } from '../lib/i18n'
import { ReviewButtons } from './ReviewDate'

/** Cap the representative preview so the section stays scannable; counts above
 *  show the true total. */
const MAX_REPRESENTATIVE = 5

/** Singular form of each group label, for a "1 …" headline. Plural comes from
 *  the backend's group label. */
const SINGULAR: Record<AttentionGroupKey, string> = {
  review_due: 'Due for review',
  grounds_changed: 'Grounds changed: check again',
  rule_errors: "Note that breaks the Brain's rules",
  provisional: 'Provisional insight',
  candidate: 'Candidate insight',
  open_questions: 'Open question',
  contested: 'Contested claim',
  unresolved_derived_from: 'Unresolved derivation',
  unresolved_links: 'Unresolved link',
}

/** Short tag for a representative item, e.g. "Provisional". */
const GROUP_TAG: Record<AttentionGroupKey, string> = {
  review_due: 'Due: review',
  grounds_changed: 'Grounds changed',
  rule_errors: 'Rule problem',
  provisional: 'Provisional',
  candidate: 'Candidate',
  open_questions: 'Open question',
  contested: 'Contested',
  unresolved_derived_from: 'Unresolved derivation',
  unresolved_links: 'Unresolved link',
}

/** Round-robin a few items across groups so the preview shows breadth of
 *  reasons, not the whole first group. Deterministic given group order. */
function pickRepresentative(
  groups: AttentionGroup[],
): Array<{ group: AttentionGroup; item: AttentionItem }> {
  const queues = groups.map((g) => [...g.items])
  const out: Array<{ group: AttentionGroup; item: AttentionItem }> = []
  let progress = true
  while (out.length < MAX_REPRESENTATIVE && progress) {
    progress = false
    for (let i = 0; i < queues.length && out.length < MAX_REPRESENTATIVE; i++) {
      const item = queues[i].shift()
      if (item) {
        out.push({ group: groups[i], item })
        progress = true
      }
    }
  }
  return out
}

/** Notes whose review date has passed, each with one-click "reviewed" actions. */
function DueList({ items }: { items: AttentionItem[] }) {
  const t = useT()
  return (
    <section className="due" aria-label={t('reviewDue')}>
      <h3 className="subsection-title">
        {t('reviewDue')} <span className="due-count">{items.length}</span>
      </h3>
      <ul className="due-list">
        {items.slice(0, 10).map((item) => (
          <li key={item.id} className="due-item">
            <div className="due-main">
              <Link className="attention-item__title" to={`/record/${encodeId(item.id)}`}>
                {item.title}
              </Link>
              <span className="hint">
                {t('reviewDueSince')} {item.detail}
              </span>
            </div>
            <ReviewButtons id={item.id} compact />
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Notes whose grounds changed after them: open to check, or mark checked. */
function GroundsList({ items, count }: { items: AttentionItem[]; count: number }) {
  const t = useT()
  return (
    <section className="due" aria-label={t('groundsChanged')}>
      <h3 className="subsection-title">
        {t('groundsChanged')} <span className="due-count">{count}</span>
      </h3>
      <p className="hint">{t('groundsChangedHint')}</p>
      <ul className="due-list">
        {items.map((item) => (
          <li key={item.id} className="due-item">
            <div className="due-main">
              <Link className="attention-item__title" to={`/record/${encodeId(item.id)}`}>
                {item.title}
              </Link>
              <span className="hint">
                {t('changedGround')} {item.detail}
              </span>
            </div>
            <button
              className="btn btn-small"
              onClick={() => void markChecked(item.id).then(() => requestRefresh(), () => requestRefresh())}
            >
              {t('checked')}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function AttentionSection() {
  const state = useAsync((signal) => fetchAttention(signal), [])

  if (state.kind === 'loading') return <Spinner label={tr('Finding items to review…')} />
  if (state.kind === 'error') return <ErrorState message={state.message} onRetry={state.retry} />

  if (state.data.total === 0 || state.data.groups.length === 0) {
    return (
      <EmptyState title={tr('Nothing needs attention right now')}>
        {tr(
          'No provisional or candidate insights, open questions, contested claims, or unresolved references were found in the Brain.',
        )}
      </EmptyState>
    )
  }

  const due = state.data.groups.find((g) => g.key === 'review_due')
  const changed = state.data.groups.find((g) => g.key === 'grounds_changed')
  const groups = state.data.groups.filter((g) => g.key !== 'review_due' && g.key !== 'grounds_changed')
  const total = state.data.total - (due?.count ?? 0) - (changed?.count ?? 0)
  const preview = pickRepresentative(groups)
  const more = Math.max(0, total - preview.length)

  return (
    <div className="attention">
      {due ? <DueList items={due.items} /> : null}
      {changed ? <GroundsList items={changed.items} count={changed.count} /> : null}
      <ul className="attention-summary" aria-label="Attention summary">
        {groups.map((group) => (
          <li key={group.key} className="attention-summary__item">
            <span className="attention-summary__count">{group.count}</span>
            <span className="attention-summary__label">
              {tr(group.count === 1 ? SINGULAR[group.key] : group.label)}
            </span>
          </li>
        ))}
      </ul>

      <ul className="attention-items" aria-label="Attention items">
        {preview.map(({ group, item }) => (
          <li
            key={`${group.key}:${item.id}:${item.detail ?? ''}`}
            className="attention-item"
          >
            <span className="attention-item__tag">{tr(GROUP_TAG[group.key])}</span>
            <Link className="attention-item__title" to={`/record/${encodeId(item.id)}`}>
              {item.title}
            </Link>
            {item.detail ? (
              <span
                className="attention-item__detail"
                title={group.key === 'rule_errors' ? tr('Rule problem') : tr('Unresolved reference')}
              >
                {item.detail}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
      {more > 0 ? <p className="attention-more">{pick(`+${more} more`, `${more}개 더`)}</p> : null}
    </div>
  )
}
