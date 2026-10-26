import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import { SourcesPage } from '../pages/SourcesPage'
import { RecordDetailPage } from '../pages/RecordDetailPage'
import { mockFetch } from './mockApi'
import { sourceRecord, sourcesList } from './fixtures'

describe('SourcesPage', () => {
  it('lists source notes', async () => {
    mockFetch([{ match: /^\/api\/sources/, body: sourcesList }])
    render(<SourcesPage />)
    const link = await screen.findByRole('link', { name: 'A Paper' })
    expect(link).toHaveAttribute('href', '#/sources/sources/paper')
  })

  it('renders an empty state when there are no sources', async () => {
    mockFetch([{ match: /^\/api\/sources/, body: { total: 0, items: [] } }])
    render(<SourcesPage />)
    expect(await screen.findByText('No sources')).toBeInTheDocument()
  })
})

describe('Source detail', () => {
  it('shows original artifact metadata without a viewer, and unresolved links', async () => {
    mockFetch([{ match: /^\/api\/records\//, body: sourceRecord }])
    render(<RecordDetailPage id="sources/paper" />)

    expect(await screen.findByRole('heading', { name: 'A Paper', level: 1 })).toBeInTheDocument()
    // Artifact metadata surfaced (URL + author)…
    expect(screen.getByRole('link', { name: 'https://example.com/paper.pdf' })).toBeInTheDocument()
    expect(screen.getByText('J. Doe')).toBeInTheDocument()
    // …but no PDF viewer is embedded.
    expect(document.querySelector('iframe, embed, object')).toBeNull()
    // Unresolved wikilink to the original artifact is preserved (not navigable).
    expect(screen.getByText('library/paper.pdf?')).toBeInTheDocument()
  })
})
