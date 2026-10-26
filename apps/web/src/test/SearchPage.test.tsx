import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import { SearchPage } from '../pages/SearchPage'
import { mockFetch } from './mockApi'
import { emptySearch, searchResponse } from './fixtures'
import type { SearchResponse } from '../types'

describe('SearchPage', () => {
  it('groups hits by semantic category and links to section detail pages', async () => {
    mockFetch([{ match: /^\/api\/search/, body: searchResponse }])
    render(<SearchPage q="memory" />)

    expect(await screen.findByRole('heading', { name: /Knowledge/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Insights/ })).toBeInTheDocument()

    const knowledgeHit = screen.getByRole('link', { name: 'LLM Agent Memory' })
    expect(knowledgeHit).toHaveAttribute('href', '#/knowledge/wiki/concepts/llm-agent-memory')
    const insightHit = screen.getByRole('link', { name: 'Memory Consolidation Pattern' })
    expect(insightHit).toHaveAttribute('href', '#/insights/wiki/insights/pattern')

    // Insight status is preserved in search results (a labelled badge, not color-only).
    expect(document.querySelector('[aria-label="Status: Provisional"]')).not.toBeNull()
    expect(document.querySelector('[aria-label="Kind: Pattern"]')).not.toBeNull()
  })

  it('groups memory/project/area hits together', async () => {
    const memorySearch: SearchResponse = {
      query: 'note',
      total: 1,
      hits: [
        {
          id: 'memory/note',
          path: 'memory/note.md',
          title: 'A Memory',
          category: 'memory',
          subtype: null,
          status: null,
          kind: null,
          score: 5,
          snippet: 'a memory note',
        },
      ],
    }
    mockFetch([{ match: /^\/api\/search/, body: memorySearch }])
    render(<SearchPage q="note" />)
    expect(await screen.findByRole('heading', { name: /Memory \/ Projects \/ Areas/ })).toBeInTheDocument()
  })

  it('shows a prompt before any query is entered', () => {
    mockFetch([{ match: /^\/api\/search/, body: emptySearch }])
    render(<SearchPage q="" />)
    expect(screen.getByText('Search the Brain')).toBeInTheDocument()
  })

  it('shows a no-results state', async () => {
    mockFetch([{ match: /^\/api\/search/, body: emptySearch }])
    render(<SearchPage q="zzznope" />)
    expect(await screen.findByText('No results')).toBeInTheDocument()
  })
})
