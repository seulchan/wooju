import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { RecordDetailPage } from '../pages/RecordDetailPage'
import { mockFetch } from './mockApi'

type Call = [string | Request, RequestInit | undefined]

const insight = {
  id: 'insights/idea',
  path: 'insights/idea.md',
  title: 'An idea',
  category: 'insight',
  status: 'candidate',
  content: '# An idea\n\n## Claim\n\nSomething.\n',
  metadata: {},
  links: [],
  derived_from: [],
  derived_from_resolved: [],
  aliases: [],
}

describe('Insight status', () => {
  it('needs a Challenge section before moving a candidate up', async () => {
    mockFetch([{ match: /^\/api\/records\//, body: insight }])
    render(<RecordDetailPage id={insight.id} />)
    const up = await screen.findByRole('button', { name: /Move up to Provisional/ })
    expect(up).toBeDisabled()
    expect(screen.getByText(/run a challenge first/)).toBeInTheDocument()
  })

  it('moves a provisional insight one step', async () => {
    const fetchMock = mockFetch([
      {
        match: /^\/api\/records\//,
        body: { ...insight, status: 'provisional', content: insight.content + '\n## Challenge\n\nMaybe not.\n' },
      },
      { match: /^\/api\/notes\/status$/, body: { status: 'applied' } },
    ])
    render(<RecordDetailPage id={insight.id} />)
    await userEvent.click(await screen.findByRole('button', { name: /Move up to Established/ }))
    await waitFor(() => {
      const sent = (fetchMock.mock.calls as unknown as Call[])
        .filter(([u, init]) => String(u) === '/api/notes/status' && init?.method === 'POST')
        .map(([, init]) => JSON.parse(String(init?.body)))
      expect(sent).toEqual([{ id: 'insights/idea', status: 'established' }])
    })
  })
})
