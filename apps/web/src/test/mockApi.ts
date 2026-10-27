import { vi } from 'vitest'

export interface MockRoute {
  /** Tested against `pathname + search`. */
  match: RegExp
  status?: number
  /** A static body, or a function of the full URL (for query/param reads). */
  body?: unknown | ((url: URL) => unknown)
  /** Server-sent events instead of a JSON body (an `event:` + `data:` block each). */
  sse?: Array<{ event: string; data: unknown }>
  /** Hold the response until this settles (to observe an in-flight state). */
  wait?: Promise<unknown>
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
        if (route.wait) await route.wait
        if (route.sse) {
          const text = route.sse
            .map((e) => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`)
            .join('')
          return new Response(text, {
            status: route.status ?? 200,
            headers: { 'content-type': 'text/event-stream' },
          })
        }
        const body = await (typeof route.body === 'function' ? route.body(url) : route.body)
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
