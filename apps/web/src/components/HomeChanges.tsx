import type { ChangesResponse, ChangeItem } from '../types'
import { encodeId } from '../lib/paths'
import { Link } from '../lib/router'
import { PERIODS, type PeriodId } from '../lib/periods'
import {
  CATEGORY_LABEL,
  changeLabel,
  contentChanges,
  summarizeChanges,
} from '../lib/changePresentation'
import type { LoadState } from '../lib/useAsync'
import { ErrorState, Spinner } from './ui'
import { tr, pick } from '../lib/i18n'

const MAX_CHANGE_ITEMS = 5

interface HomeChangesProps {
  period: PeriodId
  changes: LoadState<ChangesResponse>
  firstVisit: boolean
  onPeriodChange: (period: PeriodId) => void
}

/** Presentation boundary for Home's "What changed?" feature. */
export function HomeChanges({ period, changes, firstVisit, onPeriodChange }: HomeChangesProps) {
  const visibleChanges = changes.kind === 'ready' ? contentChanges(changes.data.items) : []

  return (
    <section className="section" aria-labelledby="changed-heading">
      <div className="section-head">
        <h2 id="changed-heading" className="section-title">
          {tr('What changed?')}
        </h2>
        <div className="filters period-selector" role="group" aria-label="Period">
          <span className="filter-label">{tr('Period')}</span>
          {PERIODS.map((option) => (
            <button
              key={option.id}
              type="button"
              className={`chip ${period === option.id ? 'chip-active' : ''}`}
              aria-pressed={period === option.id}
              onClick={() => onPeriodChange(option.id)}
            >
              {tr(option.label)}
            </button>
          ))}
        </div>
      </div>

      {changes.kind === 'loading' ? (
        <Spinner />
      ) : changes.kind === 'error' ? (
        <ErrorState message={changes.message} onRetry={changes.retry} />
      ) : visibleChanges.length === 0 ? (
        <p className="subtitle">{tr('No changes in this period.')}</p>
      ) : (
        <>
          {firstVisit ? (
            <p className="first-visit">
              {tr(
                "This is your first visit — showing the Brain's current changes. Your next visit will compare against this session.",
              )}
            </p>
          ) : null}
          <ChangeSummary items={changes.data.items} />
          <ChangeList items={changes.data.items} />
        </>
      )}
    </section>
  )
}

function ChangeSummary({ items }: { items: ChangeItem[] }) {
  const summary = summarizeChanges(items)
  if (summary.length === 0) return null
  return (
    <ul className="change-summary" aria-label="Change summary">
      {summary.map(({ category, count }) => (
        <li key={category}>
          <span className="change-count change-add">+{count}</span>
          <span className="change-cat">{tr(CATEGORY_LABEL[category] ?? category)}</span>
        </li>
      ))}
    </ul>
  )
}

function ChangeList({ items }: { items: ChangeItem[] }) {
  const visible = contentChanges(items)
  const shown = visible.slice(0, MAX_CHANGE_ITEMS)
  const more = visible.length - shown.length
  return (
    <div className="card-list change-list" aria-label="Changed records">
      {shown.map((item) => (
        <div key={item.id} className="change-item">
          <span className="change-kind">{changeLabel(item)}</span>
          <Link to={`/record/${encodeId(item.id)}`} className="change-title">
            {item.title}
          </Link>
        </div>
      ))}
      {more > 0 ? (
        <p className="change-more">{pick(`+${more} more changes this period`, `이 기간에 ${more}개 더 바뀌었어요`)}</p>
      ) : null}
    </div>
  )
}
