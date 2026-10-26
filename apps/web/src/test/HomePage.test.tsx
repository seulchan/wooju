import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { HomePage } from '../pages/HomePage'
import { mockFetch } from './mockApi'
import {
  attention,
  changes,
  emptyAttention,
  emptyOverview,
  existingUiState,
  firstRunUiState,
  graph,
  manyChanges,
  overview,
  overviewWithAreas,
} from './fixtures'

const baseRoutes = [
  { match: /^\/api\/overview/, body: overview },
  { match: /^\/api\/graph/, body: graph },
  { match: /^\/api\/attention/, body: attention },
  { match: /^\/api\/ui-state/, body: firstRunUiState },
  { match: /^\/api\/changes/, body: changes },
]

/** URLs of all /api/changes fetches, as recorded by the mock (path + search). */
function changesCalls(fn: ReturnType<typeof mockFetch>): string[] {
  return (fn.mock.calls as string[][])
    .filter(([input]) => String(input || '').includes('/api/changes'))
    .map(([input]) => String(input))
}

describe('HomePage', () => {
  it('shows What do I know? counts and defaults to Since last visit', async () => {
    mockFetch(baseRoutes)

    render(<HomePage />)

    expect(await screen.findByText('What do I know?')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Knowledge/ }).textContent).toMatch(/1/)
    expect(screen.getByRole('link', { name: /Insights/ }).textContent).toMatch(/1/)
    expect(screen.getByRole('link', { name: /Sources/ }).textContent).toMatch(/1/)

    const knowSection = screen.getByRole('heading', { name: 'What do I know?' }).closest('section')
    expect(knowSection).not.toBeNull()
    expect(within(knowSection as HTMLElement).queryByText(/Provisional/i)).not.toBeInTheDocument()
    expect(await screen.findByText('Provisional insight')).toBeInTheDocument()
    expect(screen.queryByText(/notes? indexed|read-only/i)).not.toBeInTheDocument()

    // Period selector defaults to "Since last visit".
    const sinceBtn = screen.getByRole('button', { name: 'Since last visit' })
    expect(sinceBtn).toHaveAttribute('aria-pressed', 'true')
  })

  it('shows a first-visit state when no previous last_seen_at exists', async () => {
    const fn = mockFetch([
      { match: /^\/api\/overview/, body: overview },
      { match: /^\/api\/attention/, body: attention },
      { match: /^\/api\/ui-state/, body: firstRunUiState },
      { match: /^\/api\/changes/, body: changes },
    ])
    render(<HomePage />)

    expect(await screen.findByText(/first visit/i)).toBeInTheDocument()
    // First visit fetches all-time ("since" absent), not a previous timestamp.
    const calls = changesCalls(fn)
    expect(calls.some((url) => !url.includes('since='))).toBe(true)
  })

  it('uses the persisted last_seen_at for "Since last visit"', async () => {
    const fn = mockFetch([
      { match: /^\/api\/overview/, body: overview },
      { match: /^\/api\/attention/, body: attention },
      { match: /^\/api\/ui-state/, body: existingUiState },
      { match: /^\/api\/changes/, body: changes },
    ])
    render(<HomePage />)

    await screen.findByText('What changed?')
    // A changes request was issued with since=<last_seen_at>.
    const calls = changesCalls(fn)
    const sinceCall = calls.find((url) => url.includes('since='))
    expect(sinceCall).toBeDefined()
    const sinceValue = decodeURIComponent(new URL('http://x' + sinceCall).searchParams.get('since') || '')
    expect(sinceValue).toBe('2026-08-01T00:00:00Z')
  })
  it('switches periods: 7d / 30d use a cutoff, All time sends no since', async () => {
    const user = userEvent.setup()
    const fn = mockFetch([
      { match: /^\/api\/overview/, body: overview },
      { match: /^\/api\/attention/, body: attention },
      { match: /^\/api\/ui-state/, body: existingUiState },
      { match: /^\/api\/changes/, body: changes },
    ])
    render(<HomePage />)

    // Wait for the initial "Since last visit" load (persisted last_seen_at).
    await waitFor(() => {
      const sinceCall = changesCalls(fn).find((url) => url.includes('since='))
      expect(sinceCall).toBeDefined()
    })
    const before7d = changesCalls(fn).length

    // 7 days → a fresh cutoff-based since (not the persisted last_seen_at).
    await user.click(screen.getByRole('button', { name: '7 days' }))
    await waitFor(() => {
      const cutoff = changesCalls(fn)
        .slice(before7d)
        .map((u) => decodeURIComponent(new URL('http://x' + u).searchParams.get('since') || ''))
        .find((since) => since && since !== '2026-08-01T00:00:00Z')
      expect(cutoff).toBeDefined()
    })

    // All time → a changes request with no since parameter.
    const beforeAll = changesCalls(fn).length
    await user.click(screen.getByRole('button', { name: 'All time' }))
    await waitFor(() => {
      const allTime = changesCalls(fn).slice(beforeAll).find((url) => !url.includes('since='))
      expect(allTime).toBeDefined()
    })
  })

  it('renders the empty-brain state when nothing is indexed', async () => {
    mockFetch([
      { match: /^\/api\/overview/, body: emptyOverview },
      { match: /^\/api\/ui-state/, body: firstRunUiState },
      { match: /^\/api\/changes/, body: changes },
    ])

    render(<HomePage />)

    expect(await screen.findByText('Your Brain is empty')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Knowledge/ })).not.toBeInTheDocument()
  })

  it('keeps the Home change preview to five semantic records and excludes Other', async () => {
    mockFetch([
      { match: /^\/api\/overview/, body: overview },
      { match: /^\/api\/attention/, body: emptyAttention },
      { match: /^\/api\/ui-state/, body: existingUiState },
      { match: /^\/api\/changes/, body: manyChanges },
    ])
    render(<HomePage />)

    const changed = await screen.findByRole('region', { name: 'What changed?' })
    const list = await within(changed).findByLabelText('Changed records')
    expect(within(list).getAllByRole('link')).toHaveLength(5)
    expect(within(list).getByText('+2 more changes this period')).toBeInTheDocument()
    expect(within(changed).queryByText('Other')).not.toBeInTheDocument()
  })

  it('shows deterministic main areas as a quiet supplement to the primary counts', async () => {
    mockFetch([
      { match: /^\/api\/overview/, body: overviewWithAreas },
      { match: /^\/api\/attention/, body: emptyAttention },
      { match: /^\/api\/ui-state/, body: existingUiState },
      { match: /^\/api\/changes/, body: changes },
    ])
    render(<HomePage />)

    expect(await screen.findByText('Main areas')).toBeInTheDocument()
    expect(screen.getByText('Concepts')).toBeInTheDocument()
    expect(screen.getByText('Overviews')).toBeInTheDocument()
  })

  it('records last_seen_at + a known snapshot only after state loads', async () => {
    const posts: { url: string; body: Record<string, unknown> }[] = []
    const json = (body: unknown) =>
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })

    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
        if (init?.method === 'POST' && url.includes('/api/ui-state')) {
          posts.push({ url, body: JSON.parse(String(init.body)) as Record<string, unknown> })
          return json(firstRunUiState)
        }
        if (url.includes('/api/overview')) return json(overview)
        if (url.includes('/api/graph')) return json(graph)
        if (url.includes('/api/attention')) return json(attention)
        if (url.includes('/api/ui-state')) return json(firstRunUiState)
        if (url.includes('/api/changes')) return json(changes)
        return json({})
      }),
    )

    render(<HomePage />)
    await screen.findAllByText('LLM Agent Memory') // overview + changes have rendered

    await waitFor(() => {
      expect(posts.length).toBeGreaterThanOrEqual(1)
      const last = posts[posts.length - 1]
      expect(String(last.body.last_seen_at).length).toBeGreaterThan(0)
      // The current record-id universe is captured as the disposable snapshot.
      expect(Array.isArray(last.body.known)).toBe(true)
      expect((last.body.known as string[]).length).toBe(changes.items.length)
    })
  })

  it('shows the four-question structure: attention section present, Recently updated gone', async () => {
    mockFetch(baseRoutes)
    render(<HomePage />)

    // The four questions are all present and in order.
    const headings = await screen.findAllByRole('heading', { level: 2 })
    const titles = headings.map((h) => h.textContent)
    expect(titles).toEqual([
      'What do I know?',
      'What changed?',
      'What is connected?',
      'What needs attention?',
    ])
    // The redundant "Recently updated" section is gone.
    expect(screen.queryByText('Recently updated')).not.toBeInTheDocument()

    // An attention group renders with its count and a link into record detail.
    expect(await screen.findByText('Provisional insight')).toBeInTheDocument()
    expect(
      await screen.findByRole('link', { name: 'A Provisional Insight' }),
    ).toHaveAttribute('href', '#/record/wiki/insights/prov')
  })

  it('shows a calm empty state when nothing needs attention', async () => {
    mockFetch([
      { match: /^\/api\/overview/, body: overview },
      { match: /^\/api\/graph/, body: graph },
      { match: /^\/api\/attention/, body: emptyAttention },
      { match: /^\/api\/ui-state/, body: firstRunUiState },
      { match: /^\/api\/changes/, body: changes },
    ])
    render(<HomePage />)

    expect(await screen.findByText('Nothing needs attention right now')).toBeInTheDocument()
  })
})
