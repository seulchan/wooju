import { useEffect, useState, type FormEvent, type ReactNode } from 'react'

import { ApiError, chooseAi, chooseBrain, fetchSetup, pullModel } from '../api'
import { LangProvider, useT } from '../lib/i18n'
import type { AiStatus, SetupStatus } from '../types'
import { ErrorState, Spinner } from './ui'

export const OLLAMA_DOWNLOAD_URL = 'https://ollama.com/download'
const DEFAULT_FOLDER = '~/Documents/Wooju'

/**
 * Shows the first-run screen until a Brain folder is chosen, then the app.
 * The only required question is the folder; AI setup never blocks adding files.
 */
export function SetupGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SetupStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    fetchSetup(controller.signal)
      .then((s) => {
        setStatus(s)
        setError(null)
      })
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setError(e instanceof ApiError ? e.message : 'Something went wrong.')
      })
    return () => controller.abort()
  }, [nonce])

  if (error) return <ErrorState message={error} onRetry={() => setNonce((n) => n + 1)} />
  if (!status) return <Spinner />
  return (
    <LangProvider lang={status.language}>
      {status.brain_ready ? (
        <>
          <AiBanner ai={status.ai} onChange={() => setNonce((n) => n + 1)} />
          {children}
        </>
      ) : (
        <FirstRun onDone={() => setNonce((n) => n + 1)} />
      )}
    </LangProvider>
  )
}

function FirstRun({ onDone }: { onDone: () => void }) {
  const t = useT()
  const [folder, setFolder] = useState(DEFAULT_FOLDER)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await chooseBrain(folder)
      onDone()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
      setBusy(false)
    }
  }

  return (
    <main className="first-run">
      <h1 className="page-title">{t('welcomeTitle')}</h1>
      <p className="first-run-lead">{t('welcomeBody')}</p>
      <form onSubmit={onSubmit} className="first-run-form">
        <label htmlFor="brain-folder">{t('folderLabel')}</label>
        <input
          id="brain-folder"
          className="text-input"
          value={folder}
          onChange={(e) => setFolder(e.target.value)}
          autoComplete="off"
        />
        <p className="hint">{t('folderHint')}</p>
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <button className="btn btn-primary" type="submit" disabled={busy || !folder.trim()}>
          {busy ? t('starting') : t('start')}
        </button>
      </form>
    </main>
  )
}

/** Non-blocking AI status: guides Ollama install, model download, or an API key. */
export function AiBanner({ ai, onChange }: { ai: AiStatus; onChange: () => void }) {
  const t = useT()
  const [showKey, setShowKey] = useState(false)
  const [provider, setProvider] = useState<'openai' | 'anthropic'>('anthropic')
  const [key, setKey] = useState('')
  const [error, setError] = useState<string | null>(null)

  // While Ollama is missing or a model is downloading, check again every few seconds.
  const waiting = ai.provider === 'ollama' && !ai.ready
  useEffect(() => {
    if (!waiting) return
    const timer = window.setInterval(onChange, 4000)
    return () => window.clearInterval(timer)
  }, [waiting, onChange])

  if (ai.ready) return null

  async function onKey(e: FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      const result = await chooseAi(provider, key)
      if (!result.ready) setError(result.message ?? null)
      else onChange()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
    }
  }

  return (
    <section className="ai-banner" aria-label={t('aiTitle')}>
      <strong>{t('aiTitle')}</strong>
      <p>{ai.message}</p>
      {ai.provider === 'ollama' && !ai.ollama_running ? (
        <p>
          <a className="btn" href={OLLAMA_DOWNLOAD_URL} target="_blank" rel="noreferrer">
            {t('openOllama')}
          </a>{' '}
          <span className="hint">{t('ollamaAfter')}</span>
        </p>
      ) : null}
      {ai.provider === 'ollama' && ai.ollama_running && !ai.model_downloaded ? (
        <p>
          <button className="btn btn-primary" disabled={ai.pulling} onClick={() => pullModel().then(onChange)}>
            {ai.pulling ? `${ai.model} …` : `${ai.model} ${t('pullModel')}`}
          </button>
        </p>
      ) : null}
      {showKey ? (
        <form onSubmit={onKey} className="key-form">
          <select value={provider} onChange={(e) => setProvider(e.target.value as 'openai' | 'anthropic')}>
            <option value="anthropic">Claude</option>
            <option value="openai">OpenAI</option>
          </select>
          <input
            className="text-input"
            type="password"
            aria-label={t('keyLabel')}
            placeholder={t('keyLabel')}
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
          <button className="btn" type="submit" disabled={!key.trim()}>
            {t('keySave')}
          </button>
          <p className="hint">{t('keyNote')}</p>
          {error ? (
            <p className="form-error" role="alert">
              {error}
            </p>
          ) : null}
        </form>
      ) : (
        <button className="btn-link" onClick={() => setShowKey(true)}>
          {t('useKey')}
        </button>
      )}
    </section>
  )
}
