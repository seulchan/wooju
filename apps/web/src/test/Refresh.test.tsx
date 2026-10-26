import { describe, expect, it } from 'vitest'
import { act, render, screen } from '@testing-library/react'

import { requestRefresh } from '../lib/freshness'
import { useAsync } from '../lib/useAsync'

function Probe({ fetcher }: { fetcher: () => Promise<string> }) {
  const state = useAsync(() => fetcher(), [])
  return <p>{state.kind === 'ready' ? state.data : state.kind}</p>
}

describe('background refresh', () => {
  it('keeps the data on screen while reloading', async () => {
    let n = 0
    let release: (() => void) | null = null
    const fetcher = () =>
      new Promise<string>((resolve) => {
        n += 1
        const value = `data ${n}`
        if (n === 1) resolve(value)
        else release = () => resolve(value)
      })
    render(<Probe fetcher={fetcher} />)
    expect(await screen.findByText('data 1')).toBeInTheDocument()

    act(() => requestRefresh())
    // Still the old data, never "loading", while the reload is in flight.
    expect(screen.getByText('data 1')).toBeInTheDocument()
    expect(screen.queryByText('loading')).toBeNull()
    await act(async () => release?.())
    expect(await screen.findByText('data 2')).toBeInTheDocument()
  })

  it('keeps the data if a background reload fails', async () => {
    let n = 0
    const fetcher = () => {
      n += 1
      return n === 1 ? Promise.resolve('data 1') : Promise.reject(new Error('offline'))
    }
    render(<Probe fetcher={fetcher} />)
    expect(await screen.findByText('data 1')).toBeInTheDocument()
    await act(async () => requestRefresh())
    expect(screen.getByText('data 1')).toBeInTheDocument()
  })
})
