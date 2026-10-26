import { useEffect, useRef, useState } from 'react'

import { ApiError } from '../api'
import { subscribeRefresh } from './freshness'

export type LoadState<T> =
  | { kind: 'loading' }
  | { kind: 'error'; message: string; retry: () => void }
  | { kind: 'ready'; data: T }

/**
 * Run an async fetcher and track its loading/error/ready state.
 *
 * The fetcher receives an AbortSignal so in-flight requests are cancelled when
 * `deps` change or the component unmounts (avoids stale updates / races). Only
 * `deps` trigger a re-run; the fetcher closure may change between renders.
 */
export function useAsync<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: ReadonlyArray<unknown>,
): LoadState<T> {
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher
  const [state, setState] = useState<LoadState<T>>({ kind: 'loading' })
  // Bumped to force a re-run from the retry() callback or the app refresh signal.
  const [nonce, setNonce] = useState(0)

  // Re-fetch when the app refresh signal fires (focus, visibility, or a watcher
  // refresh detected via the health poll). Subscribed once.
  useEffect(() => subscribeRefresh(() => setNonce((n) => n + 1)), [])

  useEffect(() => {
    const controller = new AbortController()
    setState({ kind: 'loading' })
    fetcherRef
      .current(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ kind: 'ready', data })
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        if (err instanceof DOMException && err.name === 'AbortError') return
        const message = err instanceof ApiError ? err.message : 'Something went wrong.'
        setState({ kind: 'error', message, retry: () => setNonce((n) => n + 1) })
      })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce])

  return state
}
