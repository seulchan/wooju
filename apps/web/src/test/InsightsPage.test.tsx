import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import { InsightsPage } from '../pages/InsightsPage'
import { RecordDetailPage } from '../pages/RecordDetailPage'
import { mockFetch } from './mockApi'
import { insightRecord, insightsList } from './fixtures'

/** The status badge carries an aria-label and always shows its text (not color-only). */
function statusBadge() {
  return document.querySelector('[aria-label="Status: Provisional"]')
}

describe('InsightsPage', () => {
  it('renders insight status, kind, and derivation count on the card', async () => {
    mockFetch([{ match: /^\/api\/insights/, body: insightsList }])
    render(<InsightsPage />)

    await screen.findByRole('link', { name: 'Memory Consolidation Pattern' })
    // Status is shown as a labelled badge (not color-only).
    expect(statusBadge()?.textContent).toBe('Provisional')
    expect(document.querySelector('[aria-label="Kind: Pattern"]')).not.toBeNull()
    expect(screen.getByText(/derives from 1/)).toBeInTheDocument()
  })

  it('offers status and kind filters derived from the data', async () => {
    mockFetch([{ match: /^\/api\/insights/, body: insightsList }])
    render(<InsightsPage />)
    await screen.findByRole('link', { name: 'Memory Consolidation Pattern' })
    expect(screen.getByRole('button', { name: 'Provisional' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pattern' })).toBeInTheDocument()
  })
})

describe('Insight detail', () => {
  it('shows status, derivation (not proof), and featured epistemic sections', async () => {
    mockFetch([{ match: /^\/api\/records\//, body: insightRecord }])
    render(<RecordDetailPage id="wiki/insights/pattern" />)

    await screen.findByRole('heading', { name: 'Memory Consolidation Pattern', level: 1 })
    expect(statusBadge()).not.toBeNull()

    // Derivation is labeled as derivation, not proof/evidence.
    expect(screen.getByText(/derives from/i)).toBeInTheDocument()
    expect(screen.getByText(/not proof/i)).toBeInTheDocument()
    // The derivation record is a followable internal link, shown by its title
    // (the raw ref is kept as the hover tooltip).
    const derived = screen.getByRole('link', { name: 'LLM Agent Memory' })
    expect(derived).toHaveAttribute('href', '#/record/wiki/concepts/llm-agent-memory')
    expect(derived).toHaveAttribute('title', 'wiki/concepts/llm-agent-memory')

    // Evidence/Challenge/Boundaries surfaced as distinct callouts…
    expect(screen.getByText('Agents persist context across turns.')).toBeInTheDocument()
    expect(screen.getByText('Context windows are bounded.')).toBeInTheDocument()
    expect(screen.getByText('Applies only to text agents.')).toBeInTheDocument()
    // …while a non-epistemic section stays in the body.
    expect(screen.getByText('related work')).toBeInTheDocument()
  })
})
