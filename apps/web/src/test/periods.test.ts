import { describe, expect, it } from 'vitest'

import { changesSince, isFirstVisit, periodCutoff } from '../lib/periods'

describe('periods', () => {
  const now = new Date('2026-08-08T12:00:00Z')

  it('fixed windows compute 7-day and 30-day cutoffs', () => {
    expect(periodCutoff('7d', now)).toBe(new Date(now.getTime() - 7 * 86400000).toISOString())
    expect(periodCutoff('30d', now)).toBe(new Date(now.getTime() - 30 * 86400000).toISOString())
    expect(periodCutoff('all', now)).toBeNull()
    expect(periodCutoff('sinceLastVisit', now)).toBeNull()
  })

  it('changesSince maps Since-last-visit to last_seen_at, All-time to null', () => {
    expect(changesSince('sinceLastVisit', '2026-08-01T00:00:00Z', now)).toBe('2026-08-01T00:00:00Z')
    expect(changesSince('sinceLastVisit', null, now)).toBeNull()
    expect(changesSince('all', '2026-08-01T00:00:00Z', now)).toBeNull()
    expect(changesSince('7d', '2026-08-01T00:00:00Z', now)).not.toBe('2026-08-01T00:00:00Z')
  })

  it('isFirstVisit reflects a Since-last-visit period with no prior visit', () => {
    expect(isFirstVisit('sinceLastVisit', null)).toBe(true)
    expect(isFirstVisit('sinceLastVisit', '2026-08-01T00:00:00Z')).toBe(false)
    expect(isFirstVisit('all', null)).toBe(false)
  })
})
