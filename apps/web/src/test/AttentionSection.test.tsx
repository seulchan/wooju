import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'

import { AttentionSection } from '../components/AttentionSection'
import { mockFetch } from './mockApi'
import { attention, emptyAttention } from './fixtures'

const manyProvisional: typeof attention = {
  groups: [
    {
      key: 'provisional',
      label: 'Provisional insights',
      count: 8,
      items: Array.from({ length: 8 }, (_, i) => ({
        id: `wiki/insights/prov-${i}`,
        path: `wiki/insights/prov-${i}.md`,
        title: `Provisional Insight ${i}`,
        category: 'insight' as const,
        status: 'provisional',
        detail: null,
      })),
    },
  ],
  total: 8,
}

describe('AttentionSection', () => {
  it('renders each non-empty group with its count and item links', async () => {
    mockFetch([{ match: /^\/api\/attention/, body: attention }])
    render(<AttentionSection />)

    // Group labels + counts are shown.
    const summary = await screen.findByRole('list', { name: 'Attention summary' })
    expect(within(summary).getByText('Provisional insight')).toBeInTheDocument()
    expect(within(summary).getByText('Candidate insight')).toBeInTheDocument()
    expect(within(summary).getByText('Open question')).toBeInTheDocument()
    expect(within(summary).getByText('Unresolved derivation')).toBeInTheDocument()

    // The provisional count headline reads "1".
    const provGroup = within(summary).getByText('Provisional insight').closest('li') as HTMLElement
    expect(within(provGroup).getByText('1')).toBeInTheDocument()

    // Items link into record detail (navigation integration). encodeId keeps
    // the structural slashes literal and percent-encodes each segment.
    expect(
      screen.getByRole('link', { name: 'A Provisional Insight' }),
    ).toHaveAttribute('href', '#/record/wiki/insights/prov')
  })

  it('shows the unresolved reference as the grounded detail, not an inference', async () => {
    mockFetch([{ match: /^\/api\/attention/, body: attention }])
    render(<AttentionSection />)
    expect(await screen.findByText('[[concepts/ghost]]')).toBeInTheDocument()
  })

  it('shows a calm empty state when there is nothing to review', async () => {
    mockFetch([{ match: /^\/api\/attention/, body: emptyAttention }])
    render(<AttentionSection />)
    expect(await screen.findByText('Nothing needs attention right now')).toBeInTheDocument()
  })

  it('keeps the representative attention preview compact while preserving the true count', async () => {
    mockFetch([{ match: /^\/api\/attention/, body: manyProvisional }])
    render(<AttentionSection />)

    const list = await screen.findByRole('list', { name: 'Attention summary' })
    expect(within(list).getByText('8')).toBeInTheDocument()
    const items = screen.getByRole('list', { name: 'Attention items' })
    expect(within(items).getAllByRole('link')).toHaveLength(5)
    expect(screen.getByText('+3 more')).toBeInTheDocument()
  })

  it('shows a recoverable error state (no raw stack trace) when the backend is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network down'))))
    render(<AttentionSection />)
    expect(await screen.findByText('Something went wrong')).toBeInTheDocument()
    expect(screen.queryByText(/network down/)).not.toBeInTheDocument()
  })
})
