import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { AskPage } from '../pages/AskPage'
import { RecordDetailPage } from '../pages/RecordDetailPage'
import { SettingsPage } from '../pages/SettingsPage'
import { mockFetch } from './mockApi'

type Call = [string | Request, RequestInit | undefined]

function posted(fetchMock: ReturnType<typeof mockFetch>, path: string): unknown[] {
  return (fetchMock.mock.calls as unknown as Call[])
    .filter(([input, init]) => String(input) === path && init?.method === 'POST')
    .map(([, init]) => (init?.body ? JSON.parse(String(init.body)) : undefined))
}

const answer = {
  question: '밸류업 지수에는 몇 개 기업이 있어?',
  answer: '100개 기업이에요 [1].\n- 삼성전자가 포함됐어요 [2].',
  found: true,
  citations: [
    { n: 1, id: 'sources/value-up', title: '코리아 밸류업 지수 발표', heading: '핵심 내용', category: 'source', excerpt: '구성종목 100개' },
    { n: 2, id: 'wiki/overviews/value-up', title: '밸류업 프로그램', heading: null, category: 'knowledge', excerpt: '삼성전자' },
  ],
  model: 'qwen3.5:9b',
  seconds: 12.3,
}

describe('Ask', () => {
  it('asks and shows the answer with linked sources', async () => {
    const fetchMock = mockFetch([{ match: /^\/api\/ask$/, body: answer }])
    render(<AskPage />)
    await userEvent.type(screen.getByRole('textbox'), '밸류업 지수에는 몇 개 기업이 있어?')
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))

    expect(await screen.findByRole('heading', { name: answer.question })).toBeInTheDocument()
    expect(posted(fetchMock, '/api/ask')).toEqual([{ question: '밸류업 지수에는 몇 개 기업이 있어?' }])
    const cites = screen.getAllByRole('link', { name: '1' })
    expect(cites[0]).toHaveAttribute('href', '#/record/sources/value-up')
    expect(screen.getByRole('link', { name: '밸류업 프로그램' })).toHaveAttribute(
      'href',
      '#/record/wiki/overviews/value-up',
    )
    expect(screen.getByText(/• 삼성전자가 포함됐어요/)).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toHaveValue('')
  })

  it('says plainly when the Brain has nothing on it', async () => {
    mockFetch([{ match: /^\/api\/ask$/, body: { ...answer, answer: '', found: false, citations: [] } }])
    render(<AskPage initial="bitcoin mining" />)
    expect(await screen.findByText(/Your Brain has nothing that answers this yet/)).toBeInTheDocument()
  })

  it('shows the notes read when the AI cited none', async () => {
    mockFetch([
      {
        match: /^\/api\/ask$/,
        body: { ...answer, answer: '100개예요.', found: false, related_only: true },
      },
    ])
    render(<AskPage initial="밸류업 몇 개" />)
    expect(await screen.findByText(/isn’t tied to specific notes/)).toBeInTheDocument()
    expect(screen.getByText(/These are the notes it read/)).toBeInTheDocument()
  })

  it('shows why the AI could not answer', async () => {
    mockFetch([{ match: /^\/api\/ask$/, status: 503, body: { detail: 'Ollama is not running.' } }])
    render(<AskPage initial="anything" />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Ollama is not running.')
  })
})

const insight = {
  id: 'wiki/questions/rerating',
  path: 'wiki/questions/rerating.md',
  title: '자사주 많은 기업의 재평가',
  category: 'insight',
  subtype: null,
  content: '# 자사주 많은 기업의 재평가\n\n## Insight\n\n가설.\n',
  metadata: {},
  links: [],
  status: 'candidate',
  kind: 'hypothesis',
  derived_from: [],
  derived_from_resolved: [],
  aliases: [],
}

describe('Challenger', () => {
  it('creates a review card for an insight', async () => {
    const fetchMock = mockFetch([
      { match: /^\/api\/records\//, body: insight },
      {
        match: /^\/api\/challenge$/,
        body: {
          id: 'p1',
          title: '반론 검토',
          summary: '보완 필요. 범위를 좁혀야 한다.',
          approval: 'batch',
          status: 'pending',
          agent: 'challenger',
          origin: insight.path,
          created_at: '',
          decided_at: null,
          commit: null,
          error: null,
          changes: [],
        },
      },
    ])
    render(<RecordDetailPage id={insight.id} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Challenge this insight' }))
    expect(await screen.findByText('보완 필요. 범위를 좁혀야 한다.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open Review' })).toHaveAttribute('href', '#/review')
    expect(posted(fetchMock, '/api/challenge')).toEqual([{ id: insight.id }])
  })

  it('is not offered on other notes', async () => {
    mockFetch([{ match: /^\/api\/records\//, body: { ...insight, category: 'source', status: null } }])
    render(<RecordDetailPage id={insight.id} />)
    await screen.findByRole('heading', { name: insight.title })
    expect(screen.queryByRole('button', { name: 'Challenge this insight' })).toBeNull()
  })
})

const setup = {
  brain_path: '/Users/me/Documents/Wooju',
  brain_ready: true,
  language: 'en',
  ai: { provider: 'ollama', model: 'qwen3.5:9b', ready: true },
}
const models = { running: true, provider: 'ollama', current: 'qwen3.5:9b', recommended: 'qwen3.5:9b', installed: [], suggested: [] }
const claudeOff = {
  installed: true,
  connected: false,
  outdated: false,
  config_readable: true,
  command: '/Applications/Wooju.app/Contents/MacOS/wooju-server --mcp',
}

describe('Claude connection', () => {
  it('connects in one click and explains the restart', async () => {
    const fetchMock = mockFetch([
      { match: /^\/api\/setup$/, body: setup },
      { match: /^\/api\/setup\/ai\/models/, body: models },
      { match: /^\/api\/claude$/, body: claudeOff },
      { match: /^\/api\/claude\/connect$/, body: { ...claudeOff, connected: true } },
    ])
    render(<SettingsPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Connect to Claude' }))
    expect(await screen.findByText(/Quit Claude completely/)).toBeInTheDocument()
    expect(screen.getByText('Connected')).toBeInTheDocument()
    expect(posted(fetchMock, '/api/claude/connect')).toHaveLength(1)
    expect(screen.getByText(/claude mcp add wooju --/)).toBeInTheDocument()
  })

  it('offers the download when Claude is missing', async () => {
    mockFetch([
      { match: /^\/api\/setup$/, body: setup },
      { match: /^\/api\/setup\/ai\/models/, body: models },
      { match: /^\/api\/claude$/, body: { ...claudeOff, installed: false } },
    ])
    render(<SettingsPage />)
    expect(await screen.findByRole('button', { name: 'Get Claude' })).toBeInTheDocument()
  })

  it('asks to reconnect when the app moved', async () => {
    mockFetch([
      { match: /^\/api\/setup$/, body: setup },
      { match: /^\/api\/setup\/ai\/models/, body: models },
      { match: /^\/api\/claude$/, body: { ...claudeOff, connected: true, outdated: true } },
    ])
    render(<SettingsPage />)
    expect(await screen.findByRole('button', { name: 'Reconnect' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(/another location/)).toBeInTheDocument())
  })
})
