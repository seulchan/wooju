import type { RecordSummary } from '../types'
import { formatDate, titleCase } from '../lib/format'
import { Link } from '../lib/router'
import { useT } from '../lib/i18n'
import { Badge, MetaBadge, StatusBadge } from './ui'

/**
 * A list/search card. `to` is the detail path (e.g. "/knowledge/<id>"); the
 * caller picks the section route or the generic "/record/<id>".
 */
export function RecordListItem({ item, to }: { item: RecordSummary; to: string }) {
  const t = useT()
  const isInsight = item.category === 'insight'
  return (
    <article className={`card${item.retired ? ' card-retired' : ''}`}>
      <h3 className="card-title">
        <Link to={to}>{item.title}</Link>
      </h3>
      <div className="card-meta">
        {item.retired ? <Badge tone="tone-warn">{t('retired')}</Badge> : null}
        <StatusBadge status={item.status} />
        {isInsight ? <MetaBadge label="Kind" value={titleCase(item.kind)} /> : null}
        {!isInsight ? <MetaBadge label="Type" value={titleCase(item.subtype)} /> : null}
        {item.modified_at ? (
          <span className="card-date" title={item.modified_at}>
            {formatDate(item.modified_at)}
          </span>
        ) : null}
        {isInsight && item.derived_from_count ? (
          <span className="card-derived" title="Number of records this insight derives from">
            derives from {item.derived_from_count}
          </span>
        ) : null}
      </div>
      {item.excerpt ? <p className="card-excerpt">{item.excerpt}</p> : null}
    </article>
  )
}
