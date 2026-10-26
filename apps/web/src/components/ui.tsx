import type { HTMLAttributes, ReactNode } from 'react'

import { statusMeta } from '../lib/format'
import { tr } from '../lib/i18n'

/** Centered "Loading…" placeholder. */
export function Spinner({ label }: { label?: string }) {
  label = label ?? tr('Loading…')
  return (
    <div className="state state-loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  )
}

/** Recoverable error with an optional retry. */
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state state-error" role="alert">
      <strong>{tr('Something went wrong')}</strong>
      <p className="state-message">{message}</p>
      {onRetry ? (
        <button className="btn" onClick={onRetry}>
          {tr('Try again')}
        </button>
      ) : null}
    </div>
  )
}

/** Friendly empty/zero state. */
export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state state-empty">
      <strong>{title}</strong>
      {children ? <p className="state-message">{children}</p> : null}
    </div>
  )
}

/** Small pill. Tone is supplementary; a label is always shown. */
export function Badge({
  tone = 'tone-neutral',
  children,
  ...rest
}: { tone?: string; children: ReactNode } & HTMLAttributes<HTMLSpanElement>) {
  return (
    <span className={`badge ${tone}`} {...rest}>
      {children}
    </span>
  )
}

/** Insight status pill (label + supplementary color — never color-only). */
export function StatusBadge({ status }: { status?: string | null }) {
  const meta = statusMeta(status)
  if (!meta) return null
  return (
    <Badge tone={meta.tone} aria-label={`Status: ${meta.label}`}>
      {meta.label}
    </Badge>
  )
}

/** Generic metadata pill for kind/subtype. */
export function MetaBadge({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null
  return (
    <span className="badge tone-muted" aria-label={`${tr(label)}: ${value}`}>
      {value}
    </span>
  )
}
