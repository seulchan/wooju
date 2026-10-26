import { vi } from 'vitest'

export interface MockRoute {
  /** Tested against `pathname + search`. */
  match: RegExp
  status?: number
  /** A static body, or a function of the full URL (for query/param reads). */
  body: unknown | ((url: URL) => unknown)
}

/**
 * Install a global `fetch` mock that maps URL patterns to JSON responses.
 * Returns the mock fn so a test can assert calls.
 */
export function mockFetch(routes: ReadonlyArray<MockRoute>) {
  const fn = vi.fn(async (input: string | URL | Request) => {
    const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const url = new URL(raw, 'http://localhost')
    const key = url.pathname + url.search
    for (const route of routes) {
      if (route.match.test(key)) {
        const body = typeof route.body === 'function' ? route.body(url) : route.body
        return new Response(JSON.stringify(body), {
          status: route.status ?? 200,
          headers: { 'content-type': 'application/json' },
        })
      }
    }
    return new Response(JSON.stringify({ detail: `no mock route for ${key}` }), { status: 404 })
  })
  vi.stubGlobal('fetch', fn)
  return fn
}
