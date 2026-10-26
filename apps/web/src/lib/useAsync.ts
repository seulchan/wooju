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
 *
 * A background refresh (the app refresh signal) keeps showing the current data
 * while it reloads, and keeps it if the reload fails: the page must not flash
 * "loading" every time something changes in the Brain.
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
  const [background, setBackground] = useState(0)
  useEffect(() => subscribeRefresh(() => setBackground((n) => n + 1)), [])

  const stateRef = useRef(state)
  stateRef.current = state
  const lastKey = useRef<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const key = JSON.stringify([...deps, nonce])
    // Same inputs and data on screen: this is a background refresh.
    const quiet = key === lastKey.current && stateRef.current.kind === 'ready'
    lastKey.current = key
    if (!quiet) setState({ kind: 'loading' })
    fetcherRef
      .current(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ kind: 'ready', data })
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        if (err instanceof DOMException && err.name === 'AbortError') return
        if (quiet) return // keep what is on screen; the next refresh tries again
        const message = err instanceof ApiError ? err.message : 'Something went wrong.'
        setState({ kind: 'error', message, retry: () => setNonce((n) => n + 1) })
      })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce, background])

  return state
}
