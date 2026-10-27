import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { RecallPage } from '../pages/RecallPage'
import { mockFetch } from './mockApi'

type Call = [string | Request, RequestInit | undefined]

const note = {
  id: 'wiki/concepts/compound',
  path: 'wiki/concepts/compound.md',
  title: '복리',
  category: 'knowledge',
  content: '# 복리\n\n## 무엇인가\n\n이자에 이자가 붙는 것.\n',
  metadata: {},
  links: [],
  derived_from: [],
  derived_from_resolved: [],
  aliases: [],
}

describe('Recall', () => {
  it('hides the note until the user tries, then schedules by rating', async () => {
    const fetchMock = mockFetch([
      { match: /^\/api\/records\//, body: note },
      { match: /^\/api\/recall$/, body: { next: '2026-12-01' } },
      {
        match: /^\/api\/attention/,
        body: {
          total: 1,
          groups: [
            {
              key: 'review_due',
              label: 'Due',
              count: 2,
              items: [
                { id: note.id, path: note.path, title: '복리', category: 'knowledge', detail: '2026-10-01' },
                { id: 'wiki/concepts/next', path: 'x', title: '다음', category: 'knowledge', detail: '2026-10-02' },
              ],
            },
          ],
        },
      },
    ])
    render(<RecallPage id={note.id} />)
    expect(await screen.findByRole('heading', { name: '복리' })).toBeInTheDocument()
    expect(screen.queryByText('이자에 이자가 붙는 것.')).toBeNull()

    await userEvent.type(screen.getByLabelText('What I recalled'), '이자가 불어남')
    await userEvent.click(screen.getByRole('button', { name: 'Open the note' }))
    expect(screen.getByText('이자에 이자가 붙는 것.')).toBeInTheDocument()
    expect(screen.getByText('이자가 불어남')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Remembered well' }))
    expect(await screen.findByText('2026-12-01')).toBeInTheDocument()
    await waitFor(() => {
      const sent = (fetchMock.mock.calls as unknown as Call[])
        .filter(([u, init]) => String(u) === '/api/recall' && init?.method === 'POST')
        .map(([, init]) => JSON.parse(String(init?.body)))
      expect(sent).toEqual([{ id: note.id, rating: 'good' }])
    })
    expect(await screen.findByRole('button', { name: 'Next note' })).toBeInTheDocument()
  })

  it("lets the user say they don't remember", async () => {
    mockFetch([{ match: /^\/api\/records\//, body: note }])
    render(<RecallPage id={note.id} />)
    await userEvent.click(await screen.findByRole('button', { name: "I don't remember" }))
    expect(screen.getByText('이자에 이자가 붙는 것.')).toBeInTheDocument()
  })
})
