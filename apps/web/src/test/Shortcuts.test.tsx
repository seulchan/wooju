import { afterEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { Layout } from '../components/Layout'
import { mockFetch } from './mockApi'

function renderLayout(children: React.ReactNode = null) {
  mockFetch([{ match: /^\/api\/health/, body: { status: 'ok', message: 'ok' } }])
  return render(<Layout route={{ name: 'home' }}>{children}</Layout>)
}

describe('Keyboard shortcuts', () => {
  afterEach(() => {
    window.location.hash = ''
  })

  it('⌘K jumps to search', async () => {
    renderLayout()
    await userEvent.keyboard('{Meta>}k{/Meta}')
    expect(screen.getByRole('searchbox', { name: 'Search the Brain' })).toHaveFocus()
  })

  it('⌘N starts a new note', async () => {
    renderLayout()
    await userEvent.keyboard('{Meta>}n{/Meta}')
    expect(window.location.hash).toBe('#/new')
  })

  it('⌘N does nothing while typing a note', async () => {
    renderLayout(<textarea aria-label="draft" />)
    await userEvent.click(screen.getByRole('textbox', { name: 'draft' }))
    await userEvent.keyboard('{Meta>}n{/Meta}')
    expect(window.location.hash).toBe('')
  })
})
