import { describe, expect, it, vi } from 'vitest'

import { ApiError, updateUiState } from '../api'

describe('api:updateUiState', () => {
  it('POSTs last_seen_at and known to /api/ui-state as JSON', async () => {
    let captured: { url: string; method?: string; body?: string } | undefined
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        captured = {
          url: typeof input === 'string' ? input : input.toString(),
          method: init?.method,
          body: typeof init?.body === 'string' ? init.body : undefined,
        }
        return new Response(JSON.stringify({ last_seen_at: 'now', known: ['a'] }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        })
      }),
    )

    const result = await updateUiState({ last_seen_at: '2026-08-08T00:00:00Z', known: ['a', 'b'] })

    expect(captured?.url).toBe('/api/ui-state')
    expect(captured?.method).toBe('POST')
    expect(JSON.parse(captured?.body ?? '')).toEqual({
      last_seen_at: '2026-08-08T00:00:00Z',
      known: ['a', 'b'],
    })
    expect(result).toEqual({ last_seen_at: 'now', known: ['a'] })
  })

  it('normalizes network failures through the shared transport', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network down'))))

    await expect(updateUiState({ known: [] })).rejects.toEqual(
      new ApiError('Could not reach the backend. Is the API running on :8000?'),
    )
  })
})
