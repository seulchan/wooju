import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { SetupGate, OLLAMA_DOWNLOAD_URL } from '../components/SetupGate'
import { DropZone } from '../components/DropZone'
import { ReviewPage } from '../pages/ReviewPage'
import { HistoryPage } from '../pages/HistoryPage'
import { LangProvider } from '../lib/i18n'
import { mockFetch } from './mockApi'
import type { ProposalView, SetupStatus } from '../types'

const aiReady = { provider: 'ollama', model: 'qwen3.5:9b', ready: true } as const

function setup(over: Partial<SetupStatus> = {}): SetupStatus {
  return { brain_path: null, brain_ready: false, language: 'ko', ai: aiReady, ...over }
}

type Call = [string | Request, RequestInit | undefined]

function calls(fetchMock: ReturnType<typeof mockFetch>, method: string, path: string): Call[] {
  return (fetchMock.mock.calls as unknown as Call[]).filter(([input, init]) => {
    const url = typeof input === 'string' ? input : input.url
    return url.startsWith(path) && (init?.method ?? 'GET') === method
  })
}

describe('First run', () => {
  it('asks only for a folder, then shows the app', async () => {
    let ready = false
    const fetchMock = mockFetch([
      { match: /^\/api\/setup\/brain/, body: () => ((ready = true), { brain_path: '/x', created: true }) },
      { match: /^\/api\/setup$/, body: () => setup({ brain_ready: ready, brain_path: ready ? '/x' : null }) },
    ])
    render(
      <SetupGate>
        <p>the app</p>
      </SetupGate>,
    )
    expect(await screen.findByRole('heading', { name: 'Wooju에 오신 걸 환영해요' })).toBeInTheDocument()
    expect(screen.getByLabelText('저장할 폴더')).toHaveValue('~/Documents/Wooju')
    await userEvent.click(screen.getByRole('button', { name: '시작하기' }))
    expect(await screen.findByText('the app')).toBeInTheDocument()
    const [, init] = calls(fetchMock, 'POST', '/api/setup/brain')[0]
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ path: '~/Documents/Wooju' })
  })

  it('shows the server message when a folder is refused', async () => {
    mockFetch([
      { match: /^\/api\/setup\/brain/, status: 400, body: { detail: '이 폴더에는 이미 다른 파일이 있어요.' } },
      { match: /^\/api\/setup$/, body: setup() },
    ])
    render(
      <SetupGate>
        <p>the app</p>
      </SetupGate>,
    )
    await userEvent.click(await screen.findByRole('button', { name: '시작하기' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('이 폴더에는 이미 다른 파일이 있어요.')
  })

  it('guides Ollama install without blocking the app', async () => {
    const fetchMock = mockFetch([
      { match: /^\/api\/open$/, body: { opened: true } },
      {
        match: /^\/api\/setup$/,
        body: setup({
          brain_ready: true,
          ai: { provider: 'ollama', model: 'qwen3.5:4b', ready: false, ollama_running: false, message: 'Ollama가 꺼져 있어요.' },
        }),
      },
    ])
    render(
      <SetupGate>
        <p>the app</p>
      </SetupGate>,
    )
    expect(await screen.findByText('the app')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Ollama 설치 페이지 열기' }))
    const [, init] = calls(fetchMock, 'POST', '/api/open')[0]
    expect(JSON.parse(String(init?.body))).toEqual({ url: OLLAMA_DOWNLOAD_URL })
    await userEvent.click(screen.getByRole('button', { name: '대신 API 키로 시작' }))
    expect(screen.getByLabelText('API 키')).toHaveAttribute('type', 'password')
  })
})

const card = (over: Partial<ProposalView>): ProposalView => ({
  id: 'p1',
  title: 'PBR 개념 추가',
  summary: '주가순자산비율 설명',
  approval: 'batch',
  status: 'pending',
  agent: 'ingest',
  origin: null,
  created_at: '2026-10-26T00:00:00Z',
  decided_at: null,
  commit: null,
  error: null,
  changes: [{ op: 'write', path: 'wiki/concepts/pbr.md' }],
  preview: '---\ntitle: PBR\n---\n# PBR 본문',
  ...over,
})

describe('Review cards', () => {
  it('applies one card and batches only batchable ones', async () => {
    const fetchMock = mockFetch([
      { match: /^\/api\/proposals\/approve$/, body: { items: [] } },
      { match: /^\/api\/proposals\/p1\/approve/, body: card({ status: 'applied' }) },
      {
        match: /^\/api\/proposals\?status=pending/,
        body: {
          total: 3,
          items: [
            card({}),
            card({ id: 'p2', title: '마진 개요' }),
            card({ id: 'm1', title: '선호 기록', approval: 'individual', preview: null }),
          ],
        },
      },
    ])
    render(
      <LangProvider lang="ko">
        <ReviewPage />
      </LangProvider>,
    )
    expect(await screen.findByText('선호 기록')).toBeInTheDocument()
    expect(screen.getByText('하나씩 확인 필요')).toBeInTheDocument()

    await userEvent.click(screen.getAllByRole('button', { name: '내용 보기' })[0])
    expect(screen.getByText('PBR 본문')).toBeInTheDocument()
    expect(screen.queryByText('title: PBR')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: '모두 반영 (2)' }))
    await waitFor(() => expect(calls(fetchMock, 'POST', '/api/proposals/approve')).toHaveLength(1))
    const [, init] = calls(fetchMock, 'POST', '/api/proposals/approve')[0]
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ ids: ['p1', 'p2'] })

    await userEvent.click(screen.getAllByRole('button', { name: '반영' })[0])
    await waitFor(() => expect(calls(fetchMock, 'POST', '/api/proposals/p1/approve')).toHaveLength(1))
  })
})

describe('History', () => {
  it('offers undo except for the first entry and undo entries', async () => {
    const fetchMock = mockFetch([
      { match: /^\/api\/history\/c2\/undo/, body: { commit: 'c4' } },
      {
        match: /^\/api\/history/,
        body: {
          items: [
            { id: 'c3', title: 'Undo: 자료 B', committed_at: '2026-10-26T03:00:00Z', paths: [], undoes: 'cX', undone: false },
            { id: 'c2', title: '자료를 저장했어요: A', committed_at: '2026-10-26T02:00:00Z', paths: [], undoes: null, undone: false },
            { id: 'c1', title: 'Start this Brain', committed_at: '2026-10-26T01:00:00Z', paths: [], undoes: null, undone: false },
          ],
        },
      },
    ])
    render(
      <LangProvider lang="ko">
        <HistoryPage />
      </LangProvider>,
    )
    expect(await screen.findByText('자료를 저장했어요: A')).toBeInTheDocument()
    const buttons = screen.getAllByRole('button', { name: '되돌리기' })
    expect(buttons).toHaveLength(1)
    await userEvent.click(buttons[0])
    await waitFor(() => expect(calls(fetchMock, 'POST', '/api/history/c2/undo')).toHaveLength(1))
  })
})

describe('Drop zone', () => {
  it('uploads picked files and shows progress and refusals', async () => {
    let uploaded = false
    const fetchMock = mockFetch([
      {
        match: /^\/api\/inbox$/,
        body: () => (
          (uploaded = true),
          { added: [], refused: [{ file: 'a.heic', message: "'a.heic'은(는) 아직 읽을 수 없는 형식이에요." }] }
        ),
      },
      {
        match: /^\/api\/jobs/,
        body: () => ({
          items: uploaded
            ? [{ id: 'j1', file: 'inbox/report.pdf', state: 'done', message: null, proposal_id: 'p', created_at: '' }]
            : [],
        }),
      },
    ])
    render(
      <LangProvider lang="ko">
        <DropZone />
      </LangProvider>,
    )
    const input = screen.getByTestId('file-input')
    fireEvent.change(input, {
      target: { files: [new File(['x'], 'report.pdf', { type: 'application/pdf' }), new File(['x'], 'a.heic')] },
    })
    expect(await screen.findByText('report.pdf')).toBeInTheDocument()
    expect(screen.getByText('저장했어요')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('a.heic')
    const [, init] = calls(fetchMock, 'POST', '/api/inbox')[0]
    expect((init as RequestInit).body).toBeInstanceOf(FormData)
  })

  it('shows how far a long file has been read', async () => {
    mockFetch([
      {
        match: /^\/api\/jobs/,
        body: {
          items: [
            {
              id: 'j1',
              file: 'inbox/book.pdf',
              state: 'working',
              message: null,
              proposal_id: null,
              created_at: '',
              progress: { done: 3, total: 8 },
            },
          ],
        },
      },
    ])
    render(
      <LangProvider lang="ko">
        <DropZone />
      </LangProvider>,
    )
    expect(await screen.findByText('긴 글을 나눠 읽는 중 · 38%')).toBeInTheDocument()
  })
})
