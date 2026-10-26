import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { SettingsPage } from '../pages/SettingsPage'
import { SetupGate } from '../components/SetupGate'
import { Layout } from '../components/Layout'
import { LangProvider } from '../lib/i18n'
import { mockFetch } from './mockApi'

type Call = [string | Request, RequestInit | undefined]

function posted(fetchMock: ReturnType<typeof mockFetch>, path: string): unknown[] {
  return (fetchMock.mock.calls as unknown as Call[])
    .filter(([input, init]) => String(input).startsWith(path) && init?.method === 'POST')
    .map(([, init]) => (init?.body ? JSON.parse(String(init.body)) : undefined))
}

const setup = {
  brain_path: '/Users/me/Documents/Wooju',
  brain_ready: true,
  language: 'en',
  ai: { provider: 'ollama', model: 'qwen3.5:9b', ready: true },
}

const models = {
  running: true,
  provider: 'ollama',
  current: 'qwen3.5:9b',
  recommended: 'qwen3.5:9b',
  installed: [
    { name: 'llama3.2:3b', size: 2_000_000_000, recommended: false },
    { name: 'qwen3.5:9b', size: 6_600_000_000, recommended: true },
  ],
  suggested: [
    { name: 'qwen3.5:4b', recommended: false, installed: false, note: '8 GB' },
    { name: 'qwen3.5:9b', recommended: true, installed: true, note: '16 GB+' },
  ],
}

const claude = {
  installed: true,
  connected: false,
  outdated: false,
  config_readable: true,
  command: '/Applications/Wooju.app/Contents/MacOS/wooju-server --mcp',
}

describe('Settings', () => {
  it('lists installed models and switches the model in use', async () => {
    const fetchMock = mockFetch([
      { match: /^\/api\/setup\/ai\/models/, body: models },
      { match: /^\/api\/claude$/, body: claude },
      { match: /^\/api\/setup\/ai\/pull/, body: { model: 'qwen3.5:4b', state: 'pulling' } },
      { match: /^\/api\/setup\/ai$/, body: { ...setup.ai, model: 'llama3.2:3b' } },
      { match: /^\/api\/setup$/, body: setup },
    ])
    render(<SettingsPage />)
    expect(await screen.findByText('llama3.2:3b')).toBeInTheDocument()
    expect(screen.getByText('In use')).toBeInTheDocument()
    expect(screen.getByText('2.0 GB')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Use this model' }))
    await waitFor(() =>
      expect(posted(fetchMock, '/api/setup/ai')).toContainEqual({ provider: 'ollama', model: 'llama3.2:3b' }),
    )

    await userEvent.click(screen.getAllByRole('button', { name: 'Download' })[0])
    await waitFor(() => expect(posted(fetchMock, '/api/setup/ai/pull')).toContainEqual({ model: 'qwen3.5:4b' }))
  })

  it('downloads a model by name', async () => {
    const fetchMock = mockFetch([
      { match: /^\/api\/setup\/ai\/models/, body: models },
      { match: /^\/api\/claude$/, body: claude },
      { match: /^\/api\/setup\/ai\/pull/, body: { model: 'gemma4:e4b', state: 'pulling' } },
      { match: /^\/api\/setup$/, body: setup },
    ])
    render(<SettingsPage />)
    await userEvent.type(await screen.findByLabelText('Model name (e.g. qwen3.5:9b)'), 'gemma4:e4b')
    await userEvent.click(screen.getAllByRole('button', { name: 'Download' }).at(-1)!)
    await waitFor(() => expect(posted(fetchMock, '/api/setup/ai/pull')).toContainEqual({ model: 'gemma4:e4b' }))
  })

  it('explains when Ollama is off', async () => {
    mockFetch([
      { match: /^\/api\/setup\/ai\/models/, body: { ...models, running: false, installed: [] } },
      { match: /^\/api\/claude$/, body: claude },
      { match: /^\/api\/setup$/, body: setup },
    ])
    render(<SettingsPage />)
    expect(await screen.findByText('Ollama is not running. Open the Ollama app to see your models.')).toBeInTheDocument()
  })

  it('switches to Claude with a key', async () => {
    const fetchMock = mockFetch([
      { match: /^\/api\/setup\/ai\/models/, body: models },
      { match: /^\/api\/claude$/, body: claude },
      { match: /^\/api\/setup\/ai$/, body: { provider: 'anthropic', model: 'claude-haiku-5-5', ready: true, has_key: true } },
      { match: /^\/api\/setup$/, body: setup },
    ])
    render(<SettingsPage />)
    await userEvent.click(await screen.findByRole('radio', { name: 'Claude' }))
    await userEvent.type(screen.getByLabelText('API key'), 'sk-ant-test')
    await userEvent.click(screen.getByRole('button', { name: 'Connect' }))
    await waitFor(() =>
      expect(posted(fetchMock, '/api/setup/ai')).toContainEqual({ provider: 'anthropic', api_key: 'sk-ant-test' }),
    )
  })
})

describe('Folder chooser', () => {
  it('fills the first-run folder from the Mac folder dialog', async () => {
    mockFetch([
      { match: /^\/api\/setup\/pick-folder/, body: { path: '/Users/me/Notes/Wooju' } },
      { match: /^\/api\/setup$/, body: { ...setup, brain_ready: false, brain_path: null } },
    ])
    render(
      <SetupGate>
        <p>app</p>
      </SetupGate>,
    )
    await userEvent.click(await screen.findByRole('button', { name: 'Choose folder…' }))
    await waitFor(() => expect(screen.getByLabelText('Folder to keep everything in')).toHaveValue('/Users/me/Notes/Wooju'))
  })
})

describe('Korean screens', () => {
  it('translates the navigation of older screens', async () => {
    mockFetch([{ match: /^\/api\/health/, body: { status: 'ok', message: 'ok' } }])
    render(
      <LangProvider lang="ko">
        <Layout route={{ name: 'home' }}>
          <p>page</p>
        </Layout>
      </LangProvider>,
    )
    for (const label of ['홈', '알게 된 것', '발견한 연결', '자료', '확인', '변경 기록', '설정']) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument()
    }
    expect(await screen.findByText('준비됨')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Brain에서 찾기…')).toBeInTheDocument()
  })
})
