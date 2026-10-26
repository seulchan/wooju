import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { KnowledgePage } from '../pages/KnowledgePage'
import { RecordDetailPage } from '../pages/RecordDetailPage'
import { mockFetch } from './mockApi'
import { knowledgeList, knowledgeRecord } from './fixtures'

describe('KnowledgePage', () => {
  it('lists knowledge notes with subtype filter chips', async () => {
    mockFetch([{ match: /^\/api\/knowledge/, body: knowledgeList }])

    render(<KnowledgePage />)

    const link = await screen.findByRole('link', { name: 'LLM Agent Memory' })
    expect(link).toHaveAttribute('href', '#/knowledge/wiki/concepts/llm-agent-memory')
    expect(screen.getByText('Notes on agent memory systems.')).toBeInTheDocument()

    // Subtype-derived chips, with the "Concept" one matching the present subtype.
    const allChip = screen.getByRole('button', { name: 'All' })
    const conceptChip = screen.getByRole('button', { name: 'Concept' })
    expect(allChip).toHaveAttribute('aria-pressed', 'true')

    // Filtering by Concept keeps the item (and toggles aria-pressed).
    fireEvent.click(conceptChip)
    expect(conceptChip).toHaveAttribute('aria-pressed', 'true')
    expect(allChip).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('link', { name: 'LLM Agent Memory' })).toBeInTheDocument()
  })

  it('renders an empty state when there is no knowledge', async () => {
    mockFetch([{ match: /^\/api\/knowledge/, body: { total: 0, items: [] } }])
    render(<KnowledgePage />)
    expect(await screen.findByText('No knowledge notes')).toBeInTheDocument()
  })
})

describe('Knowledge detail', () => {
  it('renders the note, resolves internal wikilinks, and preserves unresolved ones', async () => {
    mockFetch([{ match: /^\/api\/records\//, body: knowledgeRecord }])

    render(<RecordDetailPage id="wiki/concepts/llm-agent-memory" />)

    expect(await screen.findByRole('heading', { name: 'LLM Agent Memory', level: 1 })).toBeInTheDocument()
    // Resolved wikilink becomes an internal link to the resolved record. It
    // appears both in the rendered prose and in the aside links index.
    const retrievalLinks = await screen.findAllByRole('link', { name: 'retrieval' })
    expect(retrievalLinks.some((l) => l.getAttribute('href') === '#/record/wiki/concepts/retrieval')).toBe(true)
    // Unresolved wikilink renders as a non-navigating marker.
    expect(screen.getByText('concepts/missing?')).toBeInTheDocument()
    // Leading H1 duplicating the title is stripped from the rendered body.
    expect(screen.getByText(/Notes on agent memory systems/)).toBeInTheDocument()
  })
})
