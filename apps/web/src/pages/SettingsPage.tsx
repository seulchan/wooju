import { useEffect, useState, type FormEvent } from 'react'

import {
  ApiError,
  chooseAi,
  connectClaude,
  disconnectClaude,
  fetchClaude,
  fetchSearchStatus,
  fetchCaptureStatus,
  setIcloud,
  connectTelegram,
  disconnectTelegram,
  type CaptureStatus,
  type SearchStatus,
  type ClaudeStatus,
  chooseBrain,
  chooseLanguage,
  fetchModels,
  fetchSetup,
  openExternal,
  pickFolder,
  pullModel,
  removeSamples,
  type ModelsResponse,
} from '../api'
import { Badge, ErrorState, Spinner } from '../components/ui'
import { requestRefresh } from '../lib/freshness'
import { useLang, useT } from '../lib/i18n'
import { useAsync } from '../lib/useAsync'
import type { AiStatus, LanguageChoice, SetupStatus } from '../types'

const KEY_PAGES = {
  anthropic: 'https://console.anthropic.com/settings/keys',
  openai: 'https://platform.openai.com/api-keys',
} as const

function gb(bytes: number): string {
  return bytes ? `${(bytes / 1e9).toFixed(1)} GB` : ''
}

/** AI provider and model, the Brain folder, and language. */
export function SettingsPage() {
  const t = useT()
  const [nonce, setNonce] = useState(0)
  const state = useAsync(
    async (signal) => {
      const [setup, models, claude] = await Promise.all([
        fetchSetup(signal),
        fetchModels(signal),
        fetchClaude(signal),
      ])
      return { setup, models, claude }
    },
    [nonce],
  )
  const reload = () => {
    setNonce((n) => n + 1)
    requestRefresh()
  }

  if (state.kind === 'loading') return <Spinner />
  if (state.kind === 'error') return <ErrorState message={state.message} onRetry={state.retry} />
  const { setup, models, claude } = state.data

  return (
    <div className="settings">
      <h1 className="page-title">{t('settingsTitle')}</h1>
      <AiSettings setup={setup} models={models} onChange={reload} />
      <PhoneCapture />
      <SmartSearch ollamaRunning={models.running} />
      <ClaudeSettings status={claude} />
      <FolderSettings setup={setup} onChange={() => window.location.reload()} />
      <LanguageSettings setup={setup} />
    </div>
  )
}

const LANGUAGE_CHOICES: ReadonlyArray<{ value: LanguageChoice; label: string }> = [
  { value: 'auto', label: '' },
  { value: 'ko', label: '한국어' },
  { value: 'en', label: 'English' },
]

/** Screen language. Notes keep the language of what they are about. */
function LanguageSettings({ setup }: { setup: SetupStatus }) {
  const t = useT()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const app = setup.language_setting ?? 'auto'

  async function choose(choice: { app: LanguageChoice }) {
    setBusy(true)
    setError(null)
    try {
      await chooseLanguage(choice)
      // Every screen string comes from the language loaded at start.
      window.location.reload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
      setBusy(false)
    }
  }

  const group = (
    label: string,
    current: LanguageChoice,
    autoLabel: string,
    onPick: (v: LanguageChoice) => void,
  ) => (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {LANGUAGE_CHOICES.map((c) => (
        <button
          key={c.value}
          role="radio"
          aria-checked={current === c.value}
          className={`chip ${current === c.value ? 'chip-active' : ''}`}
          disabled={busy}
          onClick={() => current !== c.value && onPick(c.value)}
        >
          {c.value === 'auto' ? autoLabel : c.label}
        </button>
      ))}
    </div>
  )

  return (
    <section className="section" aria-label={t('language')}>
      <h2 className="section-title">{t('language')}</h2>
      {group(t('languageApp'), app, t('languageAuto'), (v) => void choose({ app: v }))}
      <p className="hint">{t('languageNote')}</p>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  )
}

function AiSettings({
  setup,
  models,
  onChange,
}: {
  setup: SetupStatus
  models: ModelsResponse
  onChange: () => void
}) {
  const t = useT()
  const [provider, setProvider] = useState<AiStatus['provider']>(setup.ai.provider)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  async function run(fn: () => Promise<unknown>) {
    setError(null)
    setNote(null)
    try {
      const result = await fn()
      if (result && typeof result === 'object' && 'ready' in result) {
        const status = result as AiStatus
        if (!status.ready && status.message) setError(status.message)
        else setNote(t('saved'))
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
    }
    onChange()
  }

  return (
    <section className="section" aria-label={t('aiProvider')}>
      <h2 className="section-title">{t('aiProvider')}</h2>
      <div className="segmented" role="radiogroup" aria-label={t('aiProvider')}>
        {(['ollama', 'anthropic', 'openai'] as const).map((p) => (
          <button
            key={p}
            role="radio"
            aria-checked={provider === p}
            className={`chip ${provider === p ? 'chip-active' : ''}`}
            onClick={() => {
              setProvider(p)
              if (p === 'ollama') void run(() => chooseAi('ollama', undefined, models.current))
            }}
          >
            {p === 'ollama' ? t('providerOllama') : p === 'anthropic' ? 'Claude' : 'OpenAI'}
          </button>
        ))}
      </div>
      <p className="hint">{t('providerNote')}</p>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      {note ? <p className="form-ok">{note}</p> : null}
      {provider === 'ollama' ? (
        <OllamaModels setup={setup} models={models} run={run} />
      ) : (
        <CloudKey provider={provider} current={setup.ai.provider === provider ? setup.ai : null} run={run} />
      )}
    </section>
  )
}

function OllamaModels({
  setup,
  models,
  run,
}: {
  setup: SetupStatus
  models: ModelsResponse
  run: (fn: () => Promise<unknown>) => Promise<void>
}) {
  const t = useT()
  const [custom, setCustom] = useState('')
  const inUse = setup.ai.provider === 'ollama' ? setup.ai.model : null
  const pulling = setup.ai.pulling ? setup.ai.model : null

  if (!models.running) {
    return (
      <div className="settings-block">
        <p>{t('ollamaOff')}</p>
        <button className="btn" onClick={() => void openExternal('https://ollama.com/download')}>
          {t('openOllama')}
        </button>
      </div>
    )
  }

  const notInstalled = models.suggested.filter((s) => !s.installed)
  return (
    <div className="settings-block">
      <h3 className="subsection-title">{t('installedModels')}</h3>
      {models.installed.length ? (
        <ul className="model-list">
          {models.installed.map((m) => (
            <li key={m.name} className="model-item">
              <span className="model-name">{m.name}</span>
              <span className="hint">{gb(m.size)}</span>
              {m.recommended ? <Badge tone="tone-ok">{t('recommended')}</Badge> : null}
              {m.name === inUse ? (
                <Badge tone="tone-neutral">{t('inUse')}</Badge>
              ) : (
                <button className="btn" onClick={() => void run(() => chooseAi('ollama', undefined, m.name))}>
                  {t('use')}
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="hint">{t('noModels')}</p>
      )}
      <p className="hint">{t('modelHint')}</p>

      <h3 className="subsection-title">{t('moreModels')}</h3>
      {notInstalled.length ? (
        <ul className="model-list">
          {notInstalled.map((s) => (
            <li key={s.name} className="model-item">
              <span className="model-name">{s.name}</span>
              <span className="hint">{s.note}</span>
              {s.recommended ? <Badge tone="tone-ok">{t('recommended')}</Badge> : null}
              <button className="btn" disabled={pulling === s.name} onClick={() => void run(() => pullModel(s.name))}>
                {pulling === s.name ? t('downloading') : t('download')}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <form
        className="key-form"
        onSubmit={(e: FormEvent) => {
          e.preventDefault()
          void run(() => pullModel(custom.trim()))
          setCustom('')
        }}
      >
        <input
          className="text-input"
          aria-label={t('modelName')}
          placeholder={t('modelName')}
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
        />
        <button className="btn" type="submit" disabled={!custom.trim()}>
          {t('download')}
        </button>
        <button type="button" className="btn-link" onClick={() => void openExternal('https://ollama.com/search')}>
          {t('browseModels')}
        </button>
      </form>
      {pulling ? <p className="hint">{`${pulling} — ${t('downloading')}`}</p> : null}
    </div>
  )
}

function CloudKey({
  provider,
  current,
  run,
}: {
  provider: 'anthropic' | 'openai'
  current: AiStatus | null
  run: (fn: () => Promise<unknown>) => Promise<void>
}) {
  const t = useT()
  const [key, setKey] = useState('')
  const [model, setModel] = useState(current?.model ?? '')
  return (
    <form
      className="settings-block key-form"
      onSubmit={(e: FormEvent) => {
        e.preventDefault()
        void run(() => chooseAi(provider, key.trim() || undefined, model.trim() || null))
        setKey('')
      }}
    >
      <input
        className="text-input"
        type="password"
        aria-label={t('keyLabel')}
        placeholder={current?.has_key ? '••••••••' : t('keyLabel')}
        value={key}
        onChange={(e) => setKey(e.target.value)}
      />
      <input
        className="text-input"
        aria-label={t('cloudModel')}
        placeholder={t('cloudModel')}
        value={model}
        onChange={(e) => setModel(e.target.value)}
      />
      <button className="btn btn-primary" type="submit" disabled={!key.trim() && !current?.has_key}>
        {t('keySave')}
      </button>
      <button type="button" className="btn-link" onClick={() => void openExternal(KEY_PAGES[provider])}>
        {t('getKey')}
      </button>
      <p className="hint">{t('keyNote')}</p>
    </form>
  )
}

function FolderSettings({ setup, onChange }: { setup: SetupStatus; onChange: () => void }) {
  const t = useT()
  const lang = useLang()
  const [error, setError] = useState<string | null>(null)

  async function change() {
    setError(null)
    const path = await pickFolder()
    if (!path) return
    try {
      await chooseBrain(path)
      onChange()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
    }
  }

  return (
    <section className="section" aria-label={t('brainFolder')}>
      <h2 className="section-title">{t('brainFolder')}</h2>
      <p>
        <code lang={lang}>{setup.brain_path}</code>
      </p>
      <button className="btn" onClick={() => void change()}>
        {t('changeFolder')}
      </button>
      {setup.sample_notes ? (
        <p className="hint">
          {t('samplesInBrain')}{' '}
          <button
            className="btn-link"
            onClick={() =>
              void removeSamples().then(
                () => {
                  requestRefresh()
                  onChange()
                },
                (err: unknown) => setError(err instanceof ApiError ? err.message : String(err)),
              )
            }
          >
            {t('samplesRemove')}
          </button>
        </p>
      ) : null}
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  )
}

const CLAUDE_DOWNLOAD = 'https://claude.ai/download'

/** One-click connection to the Claude desktop app (MCP). */
function ClaudeSettings({ status: initial }: { status: ClaudeStatus }) {
  const t = useT()
  const [status, setStatus] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [changed, setChanged] = useState(false)

  async function run(fn: () => Promise<ClaudeStatus>) {
    setBusy(true)
    setError(null)
    try {
      setStatus(await fn())
      setChanged(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="section" aria-label={t('claudeTitle')}>
      <h2 className="section-title">{t('claudeTitle')}</h2>
      <p className="hint">{t('claudeIntro')}</p>
      <p className="hint">{t('claudePrivacy')}</p>
      <div className="settings-block">
        {!status.installed ? (
          <>
            <p>{t('claudeMissing')}</p>
            <button className="btn" onClick={() => void openExternal(CLAUDE_DOWNLOAD)}>
              {t('claudeDownload')}
            </button>
          </>
        ) : status.connected ? (
          <div className="claude-row">
            <Badge tone={status.outdated ? 'tone-warn' : 'tone-ok'}>{t('claudeConnected')}</Badge>
            {status.outdated ? (
              <button className="btn btn-primary" disabled={busy} onClick={() => void run(connectClaude)}>
                {t('claudeReconnect')}
              </button>
            ) : null}
            <button className="btn" disabled={busy} onClick={() => void run(disconnectClaude)}>
              {t('claudeDisconnect')}
            </button>
          </div>
        ) : (
          <button className="btn btn-primary" disabled={busy} onClick={() => void run(connectClaude)}>
            {t('claudeConnect')}
          </button>
        )}
        {status.outdated ? <p className="hint">{t('claudeOutdated')}</p> : null}
        {changed ? (
          <p className="form-ok" role="status">
            {t('claudeRestart')}
          </p>
        ) : null}
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <details className="claude-code">
          <summary>{t('claudeCode')}</summary>
          <code className="code-line">claude mcp add wooju -- {status.command}</code>
        </details>
      </div>
    </section>
  )
}

/** Meaning search: the local embedding model and indexing progress. */
function SmartSearch({ ollamaRunning }: { ollamaRunning: boolean }) {
  const t = useT()
  const [status, setStatus] = useState<SearchStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    let timer: number | undefined
    const load = async () => {
      try {
        const s = await fetchSearchStatus()
        if (!alive) return
        setStatus(s)
        if (s.pulling || s.state === 'indexing') timer = window.setTimeout(load, 3000)
      } catch {
        // The rest of Settings still works; leave the last status shown.
      }
    }
    void load()
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [])

  async function turnOn() {
    if (!status) return
    setError(null)
    try {
      await pullModel(status.model)
      setStatus({ ...status, pulling: true })
      const poll = async () => {
        const s = await fetchSearchStatus()
        setStatus(s)
        if (s.pulling || s.state === 'indexing') window.setTimeout(poll, 3000)
      }
      window.setTimeout(poll, 3000)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    }
  }

  return (
    <section className="section" aria-label={t('smartTitle')}>
      <h2 className="section-title">{t('smartTitle')}</h2>
      <p className="hint">{t('smartIntro')}</p>
      <div className="settings-block">
        {!status ? (
          <Spinner />
        ) : status.state === 'ready' ? (
          <p>
            <Badge tone="tone-ok">{t('smartOn')}</Badge>{' '}
            <span className="hint">
              {status.model} · {status.total}
            </span>
          </p>
        ) : status.state === 'indexing' ? (
          <p role="status">
            {t('smartIndexing')} {status.done} / {status.total}
          </p>
        ) : status.pulling ? (
          <p role="status">{t('downloading')}</p>
        ) : !ollamaRunning ? (
          <p className="hint">{t('smartNeedsOllama')}</p>
        ) : (
          <>
            <p className="hint">{t('smartOff')}</p>
            <button className="btn btn-primary" onClick={() => void turnOn()}>
              {t('smartGet')}
            </button>
          </>
        )}
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </section>
  )
}

/** iCloud folder and Telegram bot, so things can be sent from the phone. */
function PhoneCapture() {
  const t = useT()
  const [status, setStatus] = useState<CaptureStatus | null>(null)
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    let timer: number | undefined
    const load = async () => {
      try {
        const s = await fetchCaptureStatus()
        if (!alive) return
        setStatus(s)
        // Waiting for the user to press Start in Telegram.
        if (s.telegram.enabled && !s.telegram.paired) timer = window.setTimeout(load, 3000)
      } catch {
        /* the rest of Settings still works */
      }
    }
    void load()
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [status?.telegram.enabled, status?.telegram.paired])

  async function run(fn: () => Promise<CaptureStatus>) {
    setBusy(true)
    setError(null)
    try {
      setStatus(await fn())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  if (!status) return null
  const { icloud, telegram, recent } = status
  return (
    <section className="section" aria-label={t('phoneTitle')}>
      <h2 className="section-title">{t('phoneTitle')}</h2>
      <p className="hint">{t('phoneIntro')}</p>

      <div className="settings-block">
        <h3 className="subsection-title">{t('icloudTitle')}</h3>
        {!icloud.available ? (
          <p className="hint">{t('icloudMissing')}</p>
        ) : icloud.enabled ? (
          <>
            <p>
              <Badge tone="tone-ok">{t('smartOn')}</Badge> <code>{icloud.folder}</code>
            </p>
            <p className="hint">{t('icloudSteps')}</p>
            <button className="btn btn-small btn-quiet" disabled={busy} onClick={() => void run(() => setIcloud(false))}>
              {t('icloudOff')}
            </button>
          </>
        ) : (
          <>
            <p className="hint">{t('icloudSteps')}</p>
            <button className="btn btn-primary" disabled={busy} onClick={() => void run(() => setIcloud(true))}>
              {t('icloudOn')}
            </button>
          </>
        )}
      </div>

      <div className="settings-block">
        <h3 className="subsection-title">{t('telegramTitle')}</h3>
        {telegram.enabled && telegram.paired ? (
          <p className="claude-row">
            <Badge tone="tone-ok">{t('telegramPaired')}</Badge>
            {telegram.bot ? <span>@{telegram.bot}</span> : null}
            <button className="btn btn-small btn-quiet" disabled={busy} onClick={() => void run(disconnectTelegram)}>
              {t('telegramOff')}
            </button>
          </p>
        ) : telegram.enabled ? (
          <>
            <p>{t('telegramPair')}</p>
            <div className="claude-row">
              <button
                className="btn btn-primary"
                disabled={!telegram.pair_link}
                onClick={() => telegram.pair_link && void openExternal(telegram.pair_link)}
              >
                {t('telegramOpen')}
              </button>
              <button className="btn btn-small btn-quiet" disabled={busy} onClick={() => void run(disconnectTelegram)}>
                {t('telegramOff')}
              </button>
            </div>
          </>
        ) : (
          <>
            <ol className="steps">
              <li>
                {t('telegramStep1')}{' '}
                <button className="btn btn-small" onClick={() => void openExternal('https://t.me/BotFather')}>
                  {t('telegramOpenFather')}
                </button>
              </li>
              <li>{t('telegramStep2')}</li>
            </ol>
            <form
              className="key-form"
              onSubmit={(e: FormEvent) => {
                e.preventDefault()
                void run(() => connectTelegram(token)).then(() => setToken(''))
              }}
            >
              <input
                className="text-input"
                type="password"
                autoComplete="off"
                aria-label={t('telegramToken')}
                placeholder="123456789:AA…"
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
              <button className="btn btn-primary" type="submit" disabled={busy || !token.trim()}>
                {t('telegramConnect')}
              </button>
            </form>
          </>
        )}
      </div>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      {recent.length ? (
        <div className="settings-block">
          <h3 className="subsection-title">{t('recentCaptures')}</h3>
          <ul className="job-list">
            {recent.map((r) => (
              <li key={`${r.at}-${r.name}`} className={`job ${r.kind === 'refused' ? 'job-failed' : 'job-done'}`}>
                <span className="job-file">{r.name}</span>
                <span className="job-state">{r.via === 'telegram' ? 'Telegram' : 'iCloud'}</span>
                {r.message ? <span className="job-message">{r.message}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}
