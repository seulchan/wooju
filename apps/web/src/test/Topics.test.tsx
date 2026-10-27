import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { TopicMembers, TopicRow, TopicSuggestions } from '../components/Topics'
import { mockFetch } from './mockApi'

type Call = [string | Request, RequestInit | undefined]

function posted(fetchMock: ReturnType<typeof mockFetch>, path: string): unknown[] {
  return (fetchMock.mock.calls as unknown as Call[])
    .filter(([u, init]) => String(u) === path && init?.method === 'POST')
    .map(([, init]) => JSON.parse(String(init?.body)))
}

const suggestion = {
  key: 'a|b|c|d',
  label: '환율 기사',
  members: ['a', 'b', 'c', 'd'].map((x) => ({ id: `sources/${x}`, title: `기사 ${x}`, category: 'source' })),
}

describe('Topics', () => {
  it('lists topics on Home', async () => {
    mockFetch([{ match: /^\/api\/topics$/, body: { items: [{ id: 'wiki/overviews/rates', title: '기준금리', count: 3 }] } }])
    render(<TopicRow />)
    expect(await screen.findByRole('link', { name: /기준금리/ })).toHaveAttribute('href', '#/record/wiki/overviews/rates')
  })

  it('makes a suggested group a topic with one tap', async () => {
    const fetchMock = mockFetch([
      { match: /^\/api\/topics\/suggestions$/, body: { items: [suggestion] } },
      { match: /^\/api\/topics\/create$/, body: { status: 'applied' } },
    ])
    render(<TopicSuggestions />)
    expect(await screen.findByText(/and 3 notes close to it/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Make it a topic' }))
    await waitFor(() =>
      expect(posted(fetchMock, '/api/topics/create')).toEqual([{ members: suggestion.members.map((m) => m.id) }]),
    )
    await waitFor(() => expect(screen.queryByText(/and 3 notes close to it/)).toBeNull())
  })

  it('can wave a suggestion off', async () => {
    const fetchMock = mockFetch([
      { match: /^\/api\/topics\/suggestions$/, body: { items: [suggestion] } },
      { match: /^\/api\/topics\/dismiss$/, body: { ok: true } },
    ])
    render(<TopicSuggestions />)
    await userEvent.click(await screen.findByRole('button', { name: 'Not now' }))
    await waitFor(() => expect(posted(fetchMock, '/api/topics/dismiss')).toHaveLength(1))
  })

  it('shows a topic’s notes by kind; AI-filed ones can be taken out, close ones added', async () => {
    const fetchMock = mockFetch([
      {
        match: /^\/api\/topics\/view\//,
        body: {
          id: 'wiki/overviews/rates',
          title: '기준금리',
          members: [
            { id: 'sources/r1', title: '첫 인상', category: 'source', by_agent: false },
            { id: 'sources/r3', title: '세 번째', category: 'source', by_agent: true },
            { id: 'wiki/questions/q', title: '왜 올렸나', category: 'knowledge', by_agent: false },
          ],
          candidates: [{ id: 'sources/r4', title: '네 번째', category: 'source', score: 0.7 }],
        },
      },
      { match: /^\/api\/topics\/remove$/, body: { status: 'applied' } },
      { match: /^\/api\/topics\/add$/, body: { added: true } },
    ])
    render(<TopicMembers id="wiki/overviews/rates" />)
    expect(await screen.findByRole('heading', { name: /Notes on this topic/ })).toBeInTheDocument()
    expect(screen.getByText('Sources')).toBeInTheDocument()
    expect(screen.getByText('Knowledge')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Take out' })).toHaveLength(1)
    await userEvent.click(screen.getByRole('button', { name: 'Take out' }))
    await waitFor(() =>
      expect(posted(fetchMock, '/api/topics/remove')).toEqual([{ topic: 'wiki/overviews/rates', member: 'sources/r3' }]),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() =>
      expect(posted(fetchMock, '/api/topics/add')).toEqual([{ topic: 'wiki/overviews/rates', member: 'sources/r4' }]),
    )
  })
})
