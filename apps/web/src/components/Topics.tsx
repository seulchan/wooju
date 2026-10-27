import { useState } from 'react'

import {
  ApiError,
  addToTopic,
  createTopic,
  dismissTopic,
  fetchTopicSuggestions,
  fetchTopicView,
  fetchTopics,
  removeFromTopic,
  type TopicSuggestion,
} from '../api'
import { requestRefresh } from '../lib/freshness'
import { pick, tr, useT } from '../lib/i18n'
import { encodeId } from '../lib/paths'
import { Link } from '../lib/router'
import { useAsync } from '../lib/useAsync'

const KIND_ORDER = ['source', 'knowledge', 'insight'] as const
const KIND_LABEL: Record<string, string> = { source: 'Sources', knowledge: 'Knowledge', insight: 'Insights' }

/** Home: the Brain's topics, as a row of links. Nothing when there are none. */
export function TopicRow() {
  const t = useT()
  const state = useAsync((signal) => fetchTopics(signal), [])
  if (state.kind !== 'ready' || !Array.isArray(state.data?.items) || !state.data.items.length) return null
  return (
    <p className="main-areas topic-row">
      <span className="main-areas__label">{t('topics')}</span>
      {state.data.items.map((topic) => (
        <Link key={topic.id} to={`/record/${encodeId(topic.id)}`} className="main-areas__area">
          {topic.title} <span className="hint">{topic.count}</span>
        </Link>
      ))}
    </p>
  )
}

/** Home: groups of notes the topics agent found outside every topic. */
export function TopicSuggestions() {
  const t = useT()
  const state = useAsync((signal) => fetchTopicSuggestions(signal), [])
  const [gone, setGone] = useState<Set<string>>(new Set())
  if (state.kind !== 'ready' || !Array.isArray(state.data?.items)) return null
  const items = state.data.items.filter((s) => !gone.has(s.key))
  if (!items.length) return null
  return (
    <section className="section topic-suggestions" aria-label={t('topicSuggestions')}>
      <h2 className="section-title">{t('topicSuggestions')}</h2>
      <p className="hint">{t('topicSuggestionsHint')}</p>
      {items.map((s) => (
        <SuggestionCard key={s.key} suggestion={s} onDone={() => setGone((g) => new Set(g).add(s.key))} />
      ))}
    </section>
  )
}

function SuggestionCard({ suggestion, onDone }: { suggestion: TopicSuggestion; onDone: () => void }) {
  const t = useT()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const ids = suggestion.members.map((m) => m.id)

  async function run(fn: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await fn()
      onDone()
      requestRefresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card topic-card">
      <p>
        <strong>{suggestion.label}</strong>{' '}
        {pick(`and ${suggestion.members.length - 1} notes close to it`, `주변 노트 ${suggestion.members.length}개`)}
      </p>
      <ul className="ref-list">
        {suggestion.members.map((m) => (
          <li key={m.id} className="ref-item">
            <Link to={`/record/${encodeId(m.id)}`}>{m.title}</Link>
          </li>
        ))}
      </ul>
      <div className="row-actions">
        <button className="btn btn-primary btn-small" disabled={busy} onClick={() => void run(() => createTopic(ids))}>
          {busy ? t('topicCreating') : t('topicCreate')}
        </button>
        <button className="btn btn-small btn-quiet" disabled={busy} onClick={() => void run(() => dismissTopic(ids))}>
          {t('topicDismiss')}
        </button>
      </div>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  )
}

/** A topic's page: its notes by kind, and close notes not in it yet. */
export function TopicMembers({ id }: { id: string }) {
  const t = useT()
  const [nonce, setNonce] = useState(0)
  const view = useAsync((signal) => fetchTopicView(id, signal), [id, nonce])
  const [error, setError] = useState<string | null>(null)
  if (view.kind !== 'ready') return null
  const { members, candidates } = view.data

  async function act(fn: () => Promise<unknown>) {
    setError(null)
    try {
      await fn()
      setNonce((n) => n + 1)
      requestRefresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    }
  }

  return (
    <section className="topic-members" aria-label={t('topicMembers')}>
      <h2 className="section-title">
        {t('topicMembers')} <span className="count">({members.length})</span>
      </h2>
      {KIND_ORDER.map((kind) => {
        const group = members.filter((m) => m.category === kind)
        if (!group.length) return null
        return (
          <div key={kind} className="topic-group">
            <h3 className="related-title">{tr(KIND_LABEL[kind])}</h3>
            <ul className="ref-list">
              {group.map((m) => (
                <li key={m.id} className="ref-item">
                  <Link to={`/record/${encodeId(m.id)}`}>{m.title}</Link>
                  {m.retired ? <span className="hint"> · {t('retiredShort')}</span> : null}
                  {m.by_agent ? (
                    <>
                      {' '}
                      <span className="related-kind">{t('topicByAgent')}</span>{' '}
                      <button className="btn-link" onClick={() => void act(() => removeFromTopic(id, m.id))}>
                        {t('topicRemove')}
                      </button>
                    </>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        )
      })}
      {candidates.length ? (
        <div className="topic-group">
          <h3 className="related-title">{t('topicCandidates')}</h3>
          <ul className="ref-list">
            {candidates.map((c) => (
              <li key={c.id} className="ref-item">
                <Link to={`/record/${encodeId(c.id)}`}>{c.title}</Link>{' '}
                <button className="btn-link" onClick={() => void act(() => addToTopic(id, c.id))}>
                  {t('topicAdd')}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  )
}
