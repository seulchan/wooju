import type { ReactNode } from 'react'

import type { BrainLink, BrainRecord, ResolvedRef } from '../types'
import { encodeId } from '../lib/paths'
import { formatDate, pluralize, titleCase } from '../lib/format'
import { Link } from '../lib/router'
import { tr } from '../lib/i18n'
import { ReviewPanel } from './ReviewDate'

/** Right-hand panels for a record detail view. */
export function RecordSidebar({ record }: { record: BrainRecord }) {
  return (
    <aside className="detail-aside">
      <Metadata record={record} />
      {record.category !== 'other' ? (
        <ReviewPanel id={record.id} value={record.metadata.review_after} />
      ) : null}
      {record.category === 'insight' ? (
        <Derivation derived={record.derived_from_resolved} />
      ) : null}
      {record.category === 'source' ? <Artifact meta={record.metadata} /> : null}
      <OutgoingLinks links={record.links} />
    </aside>
  )
}

function MetaRow({ label, children }: { label: string; children: ReactNode }) {
  if (children === null || children === undefined || children === '') return null
  return (
    <div className="metarow">
      <dt>{tr(label)}</dt>
      <dd>{children}</dd>
    </div>
  )
}

function Metadata({ record }: { record: BrainRecord }) {
  const tags = Array.isArray(record.metadata.tags)
    ? record.metadata.tags.filter((tag): tag is string => typeof tag === 'string')
    : null
  return (
    <section className="panel meta" aria-label="Record metadata">
      <h2 className="panel-title">{tr('Details')}</h2>
      <dl className="meta-list">
        <MetaRow label="Modified">{formatDate(record.modified_at)}</MetaRow>
        {record.subtype ? <MetaRow label="Type">{titleCase(record.subtype)}</MetaRow> : null}
        {record.kind ? <MetaRow label="Kind">{titleCase(record.kind)}</MetaRow> : null}
        {record.status ? <MetaRow label="Status">{titleCase(record.status)}</MetaRow> : null}
        {record.aliases.length ? <MetaRow label="Aliases">{record.aliases.join(', ')}</MetaRow> : null}
        {tags?.length ? <MetaRow label="Tags">{tags.join(', ')}</MetaRow> : null}
      </dl>
      <details className="meta-path">
        <summary>{tr('File location')}</summary>
        <code>{record.path}</code>
      </details>
    </section>
  )
}

function metaScalar(meta: Record<string, unknown>, keys: ReadonlyArray<string>): string | null {
  for (const key of keys) {
    const value = meta[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
    if (typeof value === 'number') return String(value)
  }
  return null
}

/** Original artifact info for a source note (metadata only, no viewer). */
function Artifact({ meta }: { meta: Record<string, unknown> }) {
  const url = metaScalar(meta, ['url', 'link', 'source_url', 'source-url'])
  const author = metaScalar(meta, ['author', 'authors', 'by'])
  const venue = metaScalar(meta, ['source', 'venue', 'publisher', 'journal'])
  const date = metaScalar(meta, ['date', 'published', 'year', 'accessed'])
  const type = metaScalar(meta, ['type', 'doctype', 'format'])
  const doi = metaScalar(meta, ['doi'])
  const file = metaScalar(meta, ['file', 'filename', 'artifact'])
  if (!url && !author && !venue && !date && !type && !doi && !file) return null
  return (
    <section className="panel meta" aria-label="Original artifact">
      <h2 className="panel-title">{tr('Original artifact')}</h2>
      <dl className="meta-list">
        {url ? (
          <MetaRow label="URL">
            <a href={url} target="_blank" rel="noopener noreferrer nofollow">
              {url}
            </a>
          </MetaRow>
        ) : null}
        <MetaRow label="Author">{author}</MetaRow>
        <MetaRow label="Source">{venue}</MetaRow>
        <MetaRow label="Date">{date}</MetaRow>
        <MetaRow label="Type">{type}</MetaRow>
        <MetaRow label="DOI">{doi}</MetaRow>
        <MetaRow label="File">{file ? <code>{file}</code> : null}</MetaRow>
      </dl>
    </section>
  )
}

/** Derivation provenance — explicitly not proof or evidence. */
function Derivation({ derived }: { derived: ResolvedRef[] }) {
  if (derived.length === 0) return null
  return (
    <section className="panel meta" aria-label="Derivation">
      <h2 className="panel-title">{tr('Derivation')}</h2>
      <p className="meta-note">
        {pluralize(derived.length, 'record')} this insight derives from. Derivation provenance — not proof.
      </p>
      <ul className="ref-list">
        {derived.map((ref, index) => (
          <li key={`${ref.ref}-${index}`} className="ref-item">
            {ref.resolved_id ? (
              <Link to={`/record/${encodeId(ref.resolved_id)}`} title={ref.ref}>
                {ref.title ?? ref.ref}
              </Link>
            ) : (
              <span className="unresolved" title={tr('Unresolved reference')}>
                {ref.ref}
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

function OutgoingLinks({ links }: { links: BrainLink[] }) {
  const seen = new Set<string>()
  const unique: BrainLink[] = []
  for (const link of links) {
    const key = link.resolved_id ?? link.target
    if (seen.has(key)) continue
    seen.add(key)
    unique.push(link)
  }
  if (unique.length === 0) return null
  return (
    <section className="panel meta" aria-label="Outgoing links">
      <h2 className="panel-title">{tr('Links')}</h2>
      <ul className="ref-list">
        {unique.map((link, index) => {
          const label = link.label ?? link.title ?? link.target
          const display = link.anchor ? `${label} › ${link.anchor}` : label
          return (
            <li key={`${link.target}-${index}`} className="ref-item">
              {link.resolved_id ? (
                <Link to={`/record/${encodeId(link.resolved_id)}`}>{display}</Link>
              ) : (
                <span className="unresolved" title={tr('Unresolved link')}>
                  {display}
                </span>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
