import { useEffect, useRef } from 'react'

import { fetchHealth } from '../api'

/**
 * App-wide "refresh" signal.
 *
 * The refresh controller (window focus/visibility + a light health poll that
 * watches `indexed_at`) calls {@link requestRefresh}; every active
 * {@link useAsync} subscribes and re-runs its fetcher when the signal fires.
 * This makes external Brain changes — picked up by the backend watcher — and
 * tab focus eventually visible in the UI without WebSockets.
 *
 * The signal is module-global on purpose: there is one source of freshness, and
 * only mounted pages react to it.
 */
type Listener = () => void
const listeners = new Set<Listener>()
let version = 0

export function subscribeRefresh(fn: Listener): () => void {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}

export function requestRefresh(): void {
  version += 1
  // Copy to a list first: a listener that unmounts during dispatch mutates the set.
  for (const fn of [...listeners]) fn()
}

export function refreshVersion(): number {
  return version
}

// Poll cadence and a minimum gap between focus-triggered refreshes.
const POLL_MS = 8000
const FOCUS_MIN_GAP_MS = 1500

/**
 * Mount once (in App) to drive refreshes from (a) window focus/visibility and
 * (b) a polled `/api/health` whose `indexed_at` advances when the backend
 * watcher rescans. No-op when the backend is briefly unavailable.
 */
export function useRefreshController(): void {
  const lastIndexedAt = useRef<string | null | undefined>(undefined)
  const lastFocusAt = useRef(0)

  useEffect(() => {
    let cancelled = false

    async function poll(): Promise<void> {
      try {
        const health = await fetchHealth()
        if (cancelled) return
        const prev = lastIndexedAt.current
        lastIndexedAt.current = health.indexed_at ?? null
        // Skip the very first sample (the page already fetches on mount); only
        // refresh when indexed_at actually changes thereafter.
        if (prev !== undefined && prev !== lastIndexedAt.current) requestRefresh()
      } catch {
        // Backend temporarily unavailable: the visible page's error state covers it.
      }
    }

    const onFocus = () => {
      const now = Date.now()
      if (now - lastFocusAt.current >= FOCUS_MIN_GAP_MS) {
        lastFocusAt.current = now
        requestRefresh()
      }
    }
    const onVisibility = () => {
      if (document.visibilityState === 'visible') onFocus()
    }

    const id = window.setInterval(poll, POLL_MS)
    void poll()
    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      cancelled = true
      window.clearInterval(id)
      window.removeEventListener('focus', onFocus)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])
}
