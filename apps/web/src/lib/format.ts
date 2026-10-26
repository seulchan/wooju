/** Display formatting + label/tone helpers (pure, no React). */

/** Format an ISO-8601 timestamp as e.g. "Aug 8, 2026", or "—" when absent. */
export function formatDate(iso?: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

/** Title-case a slug-like value: "mental-model" -> "Mental Model". */
export function titleCase(value?: string | null): string | null {
  if (!value) return null
  return value
    .replace(/[-_]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export interface Tone {
  /** CSS modifier class on a badge/pill, e.g. "tone-warn". */
  tone: string
  /** Human label, always shown (state is never color-only). */
  label: string
}

const STATUS_TONES: Record<string, Tone> = {
  candidate: { tone: 'tone-neutral', label: 'Candidate' },
  provisional: { tone: 'tone-warn', label: 'Provisional' },
  established: { tone: 'tone-ok', label: 'Established' },
}

/** Tone + label for an insight status, or null when status is unknown. */
export function statusMeta(status?: string | null): Tone | null {
  if (!status) return null
  const key = status.trim().toLowerCase()
  return STATUS_TONES[key] ?? { tone: 'tone-neutral', label: titleCase(status) ?? status }
}

export function pluralize(count: number, singular: string, plural?: string): string {
  return count === 1 ? `${count} ${singular}` : `${count} ${plural ?? singular + 's'}`
}
