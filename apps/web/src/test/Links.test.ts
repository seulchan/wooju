import { describe, expect, it } from 'vitest'

import { resolveLink } from '../components/Markdown'

describe('links inside notes', () => {
  const note = 'sources/focus-economics-bok-hike-2026-07.md'

  it('opens other notes inside Wooju', () => {
    expect(resolveLink('../wiki/overviews/bank-of-korea-rate-path-2026.md', note)).toEqual({
      kind: 'note',
      href: '#/record/wiki/overviews/bank-of-korea-rate-path-2026',
    })
    expect(resolveLink('../wiki/concepts/korea%20discount.md#x', note)).toEqual({
      kind: 'note',
      href: '#/record/wiki/concepts/korea%20discount',
    })
  })

  it('opens original files and web pages outside', () => {
    expect(resolveLink('../library/report.pdf', note)).toEqual({ kind: 'file', path: 'library/report.pdf' })
    expect(resolveLink('https://example.com/a', note)).toEqual({ kind: 'web', url: 'https://example.com/a' })
  })

  it('keeps wikilinks and refuses other schemes', () => {
    expect(resolveLink('#/record/wiki/x', note)).toEqual({ kind: 'internal', href: '#/record/wiki/x' })
    expect(resolveLink('javascript:alert(1)', note)).toEqual({ kind: 'none' })
    expect(resolveLink('#unresolved:x', note)).toEqual({ kind: 'unresolved' })
  })
})
