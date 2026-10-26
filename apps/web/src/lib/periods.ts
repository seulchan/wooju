/**
 * Home "What changed?" period selection.
 *
 * Periods are presentation concerns only: they map to a `since` timestamp (or
 * none for "All time") sent to `/api/changes`. "Since last visit" uses the
 * UI-local `last_seen_at`; when there is no previous visit it falls back to
 * all-time so the first run is still useful (a "First visit" state is shown).
 */

export type PeriodId = 'sinceLastVisit' | '7d' | '30d' | 'all'

export const PERIODS: ReadonlyArray<{ id: PeriodId; label: string }> = [
  { id: 'sinceLastVisit', label: 'Since last visit' },
  { id: '7d', label: '7 days' },
  { id: '30d', label: '30 days' },
  { id: 'all', label: 'All time' },
]

const DAY_MS = 24 * 3600 * 1000

/** ISO-8601 UTC cutoff for a fixed window, or null for Since-last-visit / All-time. */
export function periodCutoff(id: PeriodId, now: Date = new Date()): string | null {
  if (id === '7d') return new Date(now.getTime() - 7 * DAY_MS).toISOString()
  if (id === '30d') return new Date(now.getTime() - 30 * DAY_MS).toISOString()
  return null
}

/**
 * Resolve the `since` value to send to `/api/changes` for a period.
 * For "Since last visit": the previous `last_seen_at`, or null on first visit.
 */
export function changesSince(
  id: PeriodId,
  lastSeenAt: string | null,
  now: Date = new Date(),
): string | null {
  if (id === 'sinceLastVisit') return lastSeenAt
  return periodCutoff(id, now)
}

/** True when the given period is "Since last visit" and there's no prior visit. */
export function isFirstVisit(period: PeriodId, lastSeenAt: string | null): boolean {
  return period === 'sinceLastVisit' && lastSeenAt === null
}
