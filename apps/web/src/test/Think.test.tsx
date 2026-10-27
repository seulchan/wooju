import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { ThinkPanel } from '../components/ThinkPanel'
import { mockFetch } from './mockApi'

type Call = [string | Request, RequestInit | undefined]

function bodies(fetchMock: ReturnType<typeof mockFetch>, path: string): unknown[] {
  return (fetchMock.mock.calls as unknown as Call[])
    .filter(([u, init]) => String(u) === path && init?.method === 'POST')
    .map(([, init]) => JSON.parse(String(init?.body)))
}

const questions = {
  questions: [
    { kind: 'why', text: 'Why does it grow faster over time?', related: null },
    { kind: 'connect', text: 'How is this like', related: { id: 'wiki/concepts/habit', title: 'Habits' } },
  ],
}

describe('Questions to think with', () => {
  it('keeps an answer in the note', async () => {
    const fetchMock = mockFetch([
      { match: /^\/api\/notes\/questions$/, body: questions },
      { match: /^\/api\/notes\/reflect$/, body: { ok: true } },
    ])
    render(<ThinkPanel id="wiki/concepts/compound" />)
    await userEvent.click(screen.getByRole('button', { name: 'Get questions' }))
    expect(await screen.findByText('Why does it grow faster over time?')).toBeInTheDocument()
    await userEvent.click(screen.getAllByRole('button', { name: 'Answer' })[0])
    await userEvent.type(screen.getByLabelText('My answer'), 'The base keeps growing.')
    await userEvent.click(screen.getByRole('button', { name: 'Add to this note' }))
    await waitFor(() =>
      expect(bodies(fetchMock, '/api/notes/reflect')).toEqual([
        { id: 'wiki/concepts/compound', question: 'Why does it grow faster over time?', answer: 'The base keeps growing.' },
      ]),
    )
    expect(await screen.findByText('Saved.')).toBeInTheDocument()
    expect(screen.queryByText('Why does it grow faster over time?')).toBeNull()
  })

  it('turns an answer to a connection into a thought resting on both notes', async () => {
    const fetchMock = mockFetch([
      { match: /^\/api\/notes\/questions$/, body: questions },
      { match: /^\/api\/notes\/new$/, body: { id: 'wiki/questions/thought-1' } },
    ])
    render(<ThinkPanel id="wiki/concepts/compound" />)
    await userEvent.click(screen.getByRole('button', { name: 'Get questions' }))
    expect(await screen.findByRole('link', { name: 'Habits' })).toBeInTheDocument()
    await userEvent.click(screen.getAllByRole('button', { name: 'Answer' })[1])
    await userEvent.type(screen.getByLabelText('My answer'), 'Small steps compound.')
    await userEvent.type(screen.getByLabelText('Title of the thought'), 'Habits compound')
    await userEvent.click(screen.getByRole('button', { name: 'Save as my thought' }))
    await waitFor(() =>
      expect(bodies(fetchMock, '/api/notes/new')).toEqual([
        {
          kind: 'thought',
          title: 'Habits compound',
          body: '## Insight\n\nSmall steps compound.\n',
          grounds: ['wiki/concepts/compound', 'wiki/concepts/habit'],
          insight_kind: 'connection',
        },
      ]),
    )
  })

  it('explains when the AI is not ready', async () => {
    mockFetch([{ match: /^\/api\/notes\/questions$/, status: 503, body: { detail: 'Ollama is not running.' } }])
    render(<ThinkPanel id="x" />)
    await userEvent.click(screen.getByRole('button', { name: 'Get questions' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Ollama is not running.')
  })
})
