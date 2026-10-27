import { fetchMemos } from '../api'
import { useT } from '../lib/i18n'
import { encodeId } from '../lib/paths'
import { Link } from '../lib/router'
import { useAsync } from '../lib/useAsync'

/** The user's latest memos, so they can be found and grown into notes. */
export function RecentMemos() {
  const t = useT()
  const state = useAsync((signal) => fetchMemos(signal), [])
  // A missing or odd response must never break Home: show nothing instead.
  if (state.kind !== 'ready' || !Array.isArray(state.data?.items) || !state.data.items.length) return null
  return (
    <section className="section" aria-label={t('recentMemos')}>
      <h2 className="section-title">
        {t('recentMemos')} <span className="due-count">{state.data.total}</span>
      </h2>
      <ul className="memo-list">
        {state.data.items.map((m) => (
          <li key={m.id}>
            <Link to={`/record/${encodeId(m.id)}`}>{m.title}</Link>
            <span className="hint">
              {m.captured_at.slice(0, 10)}
              {m.via && m.via !== 'app' ? ` · ${m.via === 'telegram' ? 'Telegram' : 'iCloud'}` : ''}
            </span>
          </li>
        ))}
      </ul>
      <p className="hint">{t('memosHint')}</p>
    </section>
  )
}
