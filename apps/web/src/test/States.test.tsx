import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

import { RecordDetailPage } from '../pages/RecordDetailPage'
import { HomePage } from '../pages/HomePage'
import { mockFetch } from './mockApi'
import { stats } from './fixtures'

describe('edge states', () => {
  it('shows a not-found state for an unknown record id', async () => {
    mockFetch([{ match: /^\/api\/records\//, status: 404, body: { detail: 'Record not found' } }])
    render(<RecordDetailPage id="wiki/does-not-exist" />)
    expect(await screen.findByText('Record not found')).toBeInTheDocument()
  })

  it('shows a recoverable error state when the backend is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network down'))))
    render(<HomePage />)
    expect(await screen.findByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByText(/reach the backend/i)).toBeInTheDocument()
    // No raw stack trace leaks to the UI.
    expect(screen.queryByText(/network down/)).not.toBeInTheDocument()
    // Stats tiles still reference the fixture (not rendered in error state).
    expect(stats.total).toBe(3)
  })
})
