import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

import { BrainMap } from '../components/BrainMap'
import { mockFetch } from './mockApi'
import { emptyGraph, graph, graphRecent } from './fixtures'

function nodeEl(container: HTMLElement, id: string): HTMLElement {
  const el = container.querySelector(`[data-node-id="${id}"]`)
  if (!el) throw new Error(`node ${id} not rendered`)
  return el as HTMLElement
}

// React Flow's node selection is bound to onClick. We use fireEvent.click
// (a bare click event) rather than userEvent so d3-zoom's mousedown handler —
// which crashes on jsdom's null event.view — never runs.
describe('BrainMap', () => {
  it('renders the bounded graph from explicit relationships', async () => {
    const fn = mockFetch([{ match: /^\/api\/graph/, body: graph }])
    const { container } = render(<BrainMap since={null} />)

    await waitFor(() => expect(nodeEl(container, 'wiki/concepts/a')).toBeTruthy())
    for (const id of [
      'wiki/concepts/a',
      'wiki/concepts/b',
      'wiki/insights/i',
      'sources/s',
      'wiki/uses',
    ]) {
      expect(nodeEl(container, id)).toBeTruthy()
    }
    expect(fn.mock.calls.some(([u]) => String(u).includes('limit=40'))).toBe(true)
  })

  it('distinguishes Insight (diamond) from Knowledge (circle)', async () => {
    mockFetch([{ match: /^\/api\/graph/, body: graph }])
    const { container } = render(<BrainMap since={null} />)

    await waitFor(() => expect(nodeEl(container, 'wiki/insights/i')).toBeTruthy())
    const insight = nodeEl(container, 'wiki/insights/i')
    const knowledge = nodeEl(container, 'wiki/concepts/a')
    expect(insight.className).toMatch(/map-node--insight/)
    expect(insight.getAttribute('data-insight')).toBe('true')
    expect(knowledge.className).toMatch(/map-node--knowledge/)
    expect(knowledge.getAttribute('data-insight')).toBe(null)
  })

  it('selects a node, highlights its 1-hop neighbors, and dims the rest', async () => {
    mockFetch([{ match: /^\/api\/graph/, body: graph }])
    const { container } = render(<BrainMap since={null} />)

    await screen.findByText('Concept A')
    fireEvent.click(nodeEl(container, 'wiki/concepts/a'))

    // a is selected; undirected neighbors are b (a->b wikilink) and i (i->a derived_from).
    await waitFor(() =>
      expect(nodeEl(container, 'wiki/concepts/a').className).toMatch(/is-selected/),
    )
    expect(nodeEl(container, 'wiki/concepts/b').className).toMatch(/is-neighbor/)
    expect(nodeEl(container, 'wiki/insights/i').className).toMatch(/is-neighbor/)
    expect(nodeEl(container, 'sources/s').className).toMatch(/is-dimmed/)
    expect(nodeEl(container, 'wiki/uses').className).toMatch(/is-dimmed/)
  })

  it('shows title/type/status in a detail chip and links to the record', async () => {
    mockFetch([{ match: /^\/api\/graph/, body: graph }])
    const { container } = render(<BrainMap since={null} />)

    await screen.findByText('Derived Insight')
    fireEvent.click(screen.getByText('Derived Insight').closest('[data-node-id]') as HTMLElement)

    // Scope to the chip (the node label also shows the title, so a global text
    // query would be ambiguous after selection).
    const region = await waitFor(() => {
      const el = container.querySelector('.map-chip')
      if (!el) throw new Error('chip not rendered')
      return el as HTMLElement
    })
    expect(within(region).getByText('Insight')).toBeTruthy()
    expect(within(region).getByText('Provisional')).toBeTruthy() // status label, never color-only
    const open = within(region).getByRole('link', { name: /Open record/ })
    expect(open.getAttribute('href')).toBe('#/record/wiki/insights/i')
  })

  it('clears focus via the chip button', async () => {
    mockFetch([{ match: /^\/api\/graph/, body: graph }])
    const { container } = render(<BrainMap since={null} />)

    await screen.findByText('Concept A')
    fireEvent.click(nodeEl(container, 'wiki/concepts/a'))
    await waitFor(() => expect(nodeEl(container, 'wiki/concepts/a').className).toMatch(/is-selected/))

    fireEvent.click(screen.getByRole('button', { name: 'Clear selection' }))
    await waitFor(() =>
      expect(nodeEl(container, 'wiki/concepts/a').className).not.toMatch(/is-selected/),
    )
    expect(screen.queryByRole('link', { name: /Open record/ })).not.toBeInTheDocument()
  })

  it('renders the empty-connections state', async () => {
    mockFetch([{ match: /^\/api\/graph/, body: emptyGraph }])
    render(<BrainMap since={null} />)

    expect(await screen.findByText('No connections yet')).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Brain map' })).not.toBeInTheDocument()
  })

  it('renders a recoverable error state on API failure', async () => {
    mockFetch([{ match: /^\/api\/graph/, body: { detail: 'boom' }, status: 500 }])
    render(<BrainMap since={null} />)

    expect(await screen.findByText('Something went wrong')).toBeInTheDocument()
  })

  it('highlights recently changed nodes for the selected period (node-level only)', async () => {
    const fn = mockFetch([{ match: /^\/api\/graph/, body: graphRecent }])
    const { container } = render(<BrainMap since={'2026-08-01T00:00:00Z'} />)

    await screen.findByText('Derived Insight')
    const insight = nodeEl(container, 'wiki/insights/i')
    expect(insight.className).toMatch(/is-recent/)
    expect(insight.getAttribute('data-recent')).toBe('true')
    expect(nodeEl(container, 'wiki/concepts/a').className).not.toMatch(/is-recent/)
    // Unchanged nodes are quietly de-emphasized so the changed ones stand out.
    expect(nodeEl(container, 'wiki/concepts/a').className).toMatch(/is-quiet/)
    expect(insight.className).not.toMatch(/is-quiet/)
    expect(fn.mock.calls.some(([u]) => String(u).includes('since=2026-08-01'))).toBe(true)
    // Home uses a user-facing summary and does not foreground an implementation
    // limitation about edge timestamps.
    expect(screen.getByLabelText('Brain map summary')).toHaveTextContent(
      '5 records · 4 explicit relationships',
    )
    expect(screen.queryByText(/edge timing unknown/)).not.toBeInTheDocument()
  })

  it('never mutates the Brain — graph requests are read-only GETs only', async () => {
    const fn = mockFetch([{ match: /^\/api\/graph/, body: graph }])
    render(<BrainMap since={null} />)

    await screen.findByText('Concept A')
    const calls = fn.mock.calls as unknown as Array<
      [string | URL | Request, RequestInit | undefined]
    >
    expect(calls.length).toBeGreaterThan(0)
    for (const [input, init] of calls) {
      const url = String(input)
      expect(url).toContain('/api/graph')
      expect(init?.method ?? 'GET').not.toBe('POST')
      expect(url).not.toMatch(/\/api\/(records|ui-state|knowledge|insights|sources)/)
    }
  })
})
