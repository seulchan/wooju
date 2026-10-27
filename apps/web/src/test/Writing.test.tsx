import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { DropZone } from '../components/DropZone'
import { NewNotePage } from '../pages/NewNotePage'
import { mockFetch } from './mockApi'

type Call = [string | Request, RequestInit | undefined]

function bodies(fetchMock: ReturnType<typeof mockFetch>, path: string): unknown[] {
  return (fetchMock.mock.calls as unknown as Call[])
    .filter(([u, init]) => String(u) === path && init?.method === 'POST')
    .map(([, init]) => JSON.parse(String(init?.body)))
}

describe('New note', () => {
  it('starts from the headings and saves a concept', async () => {
    const fetchMock = mockFetch([
      { match: /^\/api\/notes\/skeleton\?kind=concept/, body: { body: '## What it is\n\n\n\n' } },
      { match: /^\/api\/notes\/skeleton/, body: { body: '## Insight\n\n' } },
      { match: /^\/api\/notes\/new$/, body: { id: 'wiki/concepts/compound-interest' } },
    ])
    render(<NewNotePage kind="concept" />)
    const box = screen.getByRole('textbox', { name: 'Edit' })
    await waitFor(() => expect(box).toHaveValue('## What it is\n\n\n\n'))
    await userEvent.type(screen.getByLabelText('Title'), 'Compound interest')
    await userEvent.type(box, 'Interest on interest.')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(bodies(fetchMock, '/api/notes/new')).toEqual([
        { kind: 'concept', title: 'Compound interest', body: '## What it is\n\n\n\nInterest on interest.', grounds: [], recall: true },
      ]),
    )
    await waitFor(() => expect(window.location.hash).toBe('#/record/wiki/concepts/compound-interest'))
  })

  it('a thought needs a ground; the note it was opened from is the first', async () => {
    const fetchMock = mockFetch([
      { match: /^\/api\/notes\/skeleton/, body: { body: '## Insight\n\n' } },
      { match: /^\/api\/records\//, body: { id: 'wiki/concepts/korea-discount', title: 'Korea discount' } },
      { match: /^\/api\/search/, body: { query: 'pbr', total: 1, hits: [{ id: 'wiki/concepts/pbr', title: 'PBR', path: '', category: 'knowledge' }] } },
      { match: /^\/api\/notes\/new$/, body: { id: 'wiki/questions/thought-1' } },
    ])
    render(<NewNotePage kind="thought" ground="wiki/concepts/korea-discount" />)
    expect(await screen.findByText(/Korea discount/)).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Find notes to rest it on'), 'pbr')
    await userEvent.click(await screen.findByRole('button', { name: 'Add' }))
    await userEvent.type(screen.getByLabelText('Title'), 'Low PBR is not enough')
    await userEvent.selectOptions(screen.getByLabelText('Kind of idea'), 'connection')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => {
      const [sent] = bodies(fetchMock, '/api/notes/new') as { grounds: string[]; insight_kind: string; kind: string }[]
      expect(sent.kind).toBe('thought')
      expect(sent.grounds).toEqual(['wiki/concepts/korea-discount', 'wiki/concepts/pbr'])
      expect(sent.insight_kind).toBe('connection')
    })
  })
})

describe('Takeaway after saving a source', () => {
  it('asks for one line and can be skipped', async () => {
    const done = {
      id: 'j1',
      file: 'inbox/a.txt',
      state: 'done',
      message: null,
      proposal_id: 'p1',
      created_at: '',
      note_id: 'sources/a',
      title: 'Value-up index launch',
    }
    const fetchMock = mockFetch([
      { match: /^\/api\/jobs/, body: { items: [done] } },
      { match: /^\/api\/notes\/takeaway$/, body: { ok: true } },
    ])
    render(<DropZone />)
    await userEvent.type(await screen.findByLabelText('My takeaway'), 'Joining an index is not a re-rating.')
    await userEvent.click(screen.getAllByRole('button', { name: 'Save' }).at(-1)!)
    await waitFor(() =>
      expect(bodies(fetchMock, '/api/notes/takeaway')).toEqual([
        { id: 'sources/a', text: 'Joining an index is not a re-rating.' },
      ]),
    )
    expect(await screen.findByText(/Saved. Ask can find it too./)).toBeInTheDocument()
  })
})

describe('Recent memos', () => {
  it('lists the latest memos with links', async () => {
    const { RecentMemos } = await import('../components/RecentMemos')
    mockFetch([
      {
        match: /^\/api\/memos/,
        body: {
          total: 3,
          items: [{ id: 'inbox/memos/2026-10-27-093000', title: 'HBM 비중 다시 보기', captured_at: '2026-10-27T09:30:00+07:00', via: 'telegram' }],
        },
      },
    ])
    render(<RecentMemos />)
    expect(await screen.findByRole('link', { name: 'HBM 비중 다시 보기' })).toHaveAttribute(
      'href',
      '#/record/inbox/memos/2026-10-27-093000',
    )
    expect(screen.getByText(/2026-10-27 · Telegram/)).toBeInTheDocument()
  })
})
