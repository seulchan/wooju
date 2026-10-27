import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { RecordDetailPage } from '../pages/RecordDetailPage'
import { ReviewPage } from '../pages/ReviewPage'
import { mockFetch } from './mockApi'

type Call = [string | Request, RequestInit | undefined]

function bodies(fetchMock: ReturnType<typeof mockFetch>, path: string): unknown[] {
  return (fetchMock.mock.calls as unknown as Call[])
    .filter(([u, init]) => String(u) === path && init?.method === 'POST')
    .map(([, init]) => JSON.parse(String(init?.body)))
}

const note = {
  id: 'sources/fx',
  path: 'sources/fx.md',
  title: '환율 기사',
  category: 'source',
  content: '# 환율 기사\n\n## 핵심 내용\n\n- 발행일 10월 5일\n',
  metadata: {},
  links: [],
  derived_from: [],
  derived_from_resolved: [],
  aliases: [],
}

describe('Editing notes', () => {
  it('saves an edit with the body it started from', async () => {
    const fetchMock = mockFetch([
      { match: /^\/api\/records\//, body: note },
      { match: /^\/api\/notes\/edit$/, body: { status: 'applied' } },
    ])
    render(<RecordDetailPage id={note.id} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    expect(screen.getByText(/Fix only what was copied wrong/)).toBeInTheDocument()
    const box = screen.getByRole('textbox', { name: 'Edit' })
    await userEvent.clear(box)
    await userEvent.type(box, '# 환율 기사{enter}{enter}- 발행일 10월 15일')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(bodies(fetchMock, '/api/notes/edit')).toEqual([
        { id: 'sources/fx', body: '# 환율 기사\n\n- 발행일 10월 15일', base: note.content },
      ]),
    )
  })

  it('shows why an edit was not saved', async () => {
    mockFetch([
      { match: /^\/api\/records\//, body: { ...note, category: 'knowledge' } },
      { match: /^\/api\/notes\/edit$/, status: 409, body: { detail: 'This note changed elsewhere.' } },
    ])
    render(<RecordDetailPage id={note.id} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Edit' }), ' 추가')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('This note changed elsewhere.')
  })

  it('fixes a proposal before approving it', async () => {
    const proposal = {
      id: 'p1',
      title: 'Saved source: 환율 기사',
      summary: '요약',
      approval: 'batch',
      status: 'pending',
      agent: 'ingest',
      origin: null,
      created_at: '',
      decided_at: null,
      commit: null,
      error: null,
      changes: [{ op: 'write', path: 'sources/fx.md' }],
      preview: '---\ntitle: 환율 기사\n---\n\n# 환율 기사\n\n- 발행일 10월 5일\n',
    }
    const fetchMock = mockFetch([
      { match: /^\/api\/proposals\?/, body: { total: 1, items: [proposal] } },
      { match: /^\/api\/proposals\/p1\/edit$/, body: proposal },
    ])
    render(<ReviewPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    const box = screen.getByRole('textbox', { name: 'Edit' })
    expect(box).toHaveValue('# 환율 기사\n\n- 발행일 10월 5일\n')
    await userEvent.type(box, '- 추가')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(bodies(fetchMock, '/api/proposals/p1/edit')).toEqual([
        { body: '# 환율 기사\n\n- 발행일 10월 5일\n- 추가' },
      ]),
    )
  })
})
