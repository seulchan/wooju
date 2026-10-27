import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'

import { RecordSidebar } from '../components/RecordSidebar'
import { mockFetch } from './mockApi'
import type { BrainRecord } from '../types'

const record = {
  id: 'wiki/concepts/spacing-effect',
  path: 'wiki/concepts/spacing-effect.md',
  title: 'Spacing effect',
  category: 'knowledge',
  content: '',
  metadata: {},
  links: [],
  derived_from: [],
  derived_from_resolved: [],
  aliases: [],
} as unknown as BrainRecord

describe('Related notes', () => {
  it('shows links both ways and notes close in meaning, with their kind', async () => {
    mockFetch([
      {
        match: /^\/api\/related\//,
        body: {
          links_out: [{ id: 'sources/forgetting-curve', title: 'Forgetting curve', category: 'source' }],
          links_in: [{ id: 'wiki/how-tos/review', title: 'Review a note so it stays', category: 'knowledge' }],
          similar: [
            { id: 'sources/spaced', title: 'Spaced repetition', category: 'source', score: 0.93, duplicate: true },
          ],
        },
      },
    ])
    render(<RecordSidebar record={record} />)
    const panel = await screen.findByRole('region', { name: 'Related' })
    expect(within(panel).getByRole('link', { name: 'Forgetting curve' })).toHaveAttribute(
      'href',
      '#/record/sources/forgetting-curve',
    )
    expect(within(panel).getByText('Linked from')).toBeInTheDocument()
    expect(within(panel).getByRole('link', { name: 'Review a note so it stays' })).toBeInTheDocument()
    expect(within(panel).getByText('May say the same thing')).toBeInTheDocument()
  })

  it('shows nothing when there is nothing related', async () => {
    mockFetch([{ match: /^\/api\/related\//, body: { links_out: [], links_in: [], similar: [] } }])
    render(<RecordSidebar record={record} />)
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByRole('region', { name: 'Related' })).toBeNull()
  })
})

describe('AI work in Details', () => {
  it('lists what an AI wrote, newest first, and nothing for your own notes', async () => {
    mockFetch([{ match: /^\/api\/related\//, body: { links_out: [], links_in: [], similar: [] } }])
    const made = {
      ...record,
      metadata: {
        made_by: [
          { agent: 'ingest', did: 'created', on: '2026-10-27', model: 'qwen3.5:9b' },
          { agent: 'challenger', did: 'challenge', on: '2026-10-28', model: 'qwen3.5:9b' },
        ],
      },
    } as unknown as BrainRecord
    const { unmount } = render(<RecordSidebar record={made} />)
    const items = screen.getByText('AI work').parentElement!.querySelectorAll('li')
    expect([...items].map((li) => li.textContent)).toEqual([
      'Challenge · qwen3.5:9b · 2026-10-28',
      'Organized · qwen3.5:9b · 2026-10-27',
    ])
    unmount()
    render(<RecordSidebar record={record} />)
    expect(screen.queryByText('AI work')).toBeNull()
  })
})
