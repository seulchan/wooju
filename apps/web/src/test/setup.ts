import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

import '@testing-library/jest-dom/vitest'

// React Flow measures its canvas/nodes via ResizeObserver, which jsdom lacks.
// Provide a no-op implementation so the Brain Map renders in unit tests.
class ResizeObserverMock {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
if (!('ResizeObserver' in globalThis)) {
  globalThis.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver
}

afterEach(() => {
  cleanup()
  // Remove any fetch mock installed by a test.
  vi.unstubAllGlobals()
})
