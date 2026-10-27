import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { AttentionSection } from '../components/AttentionSection'
import { monthsFromToday } from '../components/ReviewDate'
import { mockFetch } from './mockApi'

type Call = [string | Request, RequestInit | undefined]

const attention = {
  total: 2,
  groups: [
    {
      key: 'review_due',
      label: 'Due for review',
      count: 1,
      items: [
        { id: 'wiki/overviews/samsung', path: 'wiki/overviews/samsung.md', title: '삼성전자 실적 가설', category: 'knowledge', detail: '2026-07-31' },
      ],
    },
    {
      key: 'rule_errors',
      label: "Notes that break the Brain's rules",
      count: 1,
      items: [
        { id: 'sources/broken', path: 'sources/broken.md', title: '깨진 자료', category: 'source', detail: 'source_type: Input should be ...' },
      ],
    },
  ],
}

describe('Maintainer on Home', () => {
  it('lists notes due for review and moves the date in one click', async () => {
    const fetchMock = mockFetch([
      { match: /^\/api\/attention/, body: attention },
      { match: /^\/api\/review-date$/, body: { status: 'applied' } },
    ])
    render(<AttentionSection />)
    expect(await screen.findByText('삼성전자 실적 가설')).toBeInTheDocument()
    expect(screen.getByText(/2026-07-31/)).toBeInTheDocument()
    expect(screen.getByText('깨진 자료')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'In 3 months' }))
    await waitFor(() => {
      const bodies = (fetchMock.mock.calls as unknown as Call[])
        .filter(([u, init]) => String(u) === '/api/review-date' && init?.method === 'POST')
        .map(([, init]) => JSON.parse(String(init?.body)))
      expect(bodies).toEqual([{ id: 'wiki/overviews/samsung', until: monthsFromToday(3) }])
    })
  })
})

describe('monthsFromToday', () => {
  it('handles month ends', () => {
    expect(monthsFromToday(1, new Date(2027, 0, 31))).toBe('2027-02-28')
    expect(monthsFromToday(12, new Date(2026, 9, 27))).toBe('2027-10-27')
  })
})

describe('Capture box', () => {
  it('saves a memo', async () => {
    const { DropZone } = await import('../components/DropZone')
    const fetchMock = mockFetch([
      { match: /^\/api\/jobs/, body: { items: [] } },
      { match: /^\/api\/capture$/, body: { kind: 'memo', file: 'inbox/memos/x.md' } },
    ])
    render(<DropZone />)
    await userEvent.type(screen.getByRole('textbox', { name: 'Link or memo' }), 'HBM 비중 확인')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Memo saved. Ask can find it.')).toBeInTheDocument()
    const bodies = (fetchMock.mock.calls as unknown as Call[])
      .filter(([u, init]) => String(u) === '/api/capture' && init?.method === 'POST')
      .map(([, init]) => JSON.parse(String(init?.body)))
    expect(bodies).toEqual([{ text: 'HBM 비중 확인' }])
  })

  it('shows why a link failed', async () => {
    const { DropZone } = await import('../components/DropZone')
    mockFetch([
      { match: /^\/api\/jobs/, body: { items: [] } },
      { match: /^\/api\/capture$/, status: 400, body: { detail: "Couldn't fetch the page." } },
    ])
    render(<DropZone />)
    await userEvent.type(screen.getByRole('textbox', { name: 'Link or memo' }), 'https://example.com')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't fetch the page.")
  })
})

describe('Failed files', () => {
  it('can be retried or removed', async () => {
    const { DropZone } = await import('../components/DropZone')
    const failed = {
      id: 'j1',
      file: 'inbox/en-wikipedia-org-kospi.html',
      state: 'failed',
      message: 'Tried three times without success.',
      proposal_id: null,
      created_at: '',
    }
    const fetchMock = mockFetch([
      { match: /^\/api\/jobs$/, body: { items: [failed] } },
      { match: /^\/api\/jobs\/j1\/retry$/, body: { ...failed, state: 'queued' } },
      { match: /^\/api\/jobs\/j1\/remove$/, body: { ...failed, message: 'Removed from the inbox.' } },
    ])
    render(<DropZone />)
    await userEvent.click(await screen.findByRole('button', { name: 'Try again' }))
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }))
    const posts = (fetchMock.mock.calls as unknown as Call[])
      .filter(([, init]) => init?.method === 'POST')
      .map(([u]) => String(u))
    expect(posts).toEqual(['/api/jobs/j1/retry', '/api/jobs/j1/remove'])
  })

  it('says when a link is already saved', async () => {
    const { DropZone } = await import('../components/DropZone')
    mockFetch([
      { match: /^\/api\/jobs/, body: { items: [] } },
      { match: /^\/api\/capture$/, body: { kind: 'link', duplicate: true, title: 'KOSPI' } },
    ])
    render(<DropZone />)
    await userEvent.type(screen.getByRole('textbox', { name: 'Link or memo' }), 'https://en.wikipedia.org/wiki/KOSPI')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Already saved: KOSPI')).toBeInTheDocument()
  })
})
