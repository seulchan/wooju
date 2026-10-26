import { useEffect, useState, type AnchorHTMLAttributes, type ReactNode } from 'react'

import { decodeId } from './paths'

/**
 * Minimal hash-based router.
 *
 * Hash routing needs no server SPA fallback and works identically in `vite dev`
 * and a static production build. Routes look like `#/knowledge`, `#/knowledge/<id>`,
 * `#/search?q=...`. Record ids (which contain "/") are captured as the rest of
 * the path after a section segment.
 */

export type Route =
  | { name: 'home' }
  | { name: 'ask'; q: string }
  | { name: 'knowledge' }
  | { name: 'knowledgeDetail'; id: string }
  | { name: 'insights' }
  | { name: 'insightDetail'; id: string }
  | { name: 'sources' }
  | { name: 'sourceDetail'; id: string }
  | { name: 'recordDetail'; id: string }
  | { name: 'search'; q: string }
  | { name: 'review' }
  | { name: 'history' }
  | { name: 'settings' }
  | { name: 'notFound'; path: string }

function decodeSafe(part: string): string {
  try {
    return decodeURIComponent(part)
  } catch {
    return part
  }
}

export function parseHash(hash: string): Route {
  let h = hash.replace(/^#/, '')
  if (h.startsWith('/')) h = h.slice(1)
  const [pathPart, queryPart = ''] = h.split('?')
  const segs = pathPart ? pathPart.split('/').map(decodeSafe) : []
  const head = segs[0] ?? ''
  const rest = segs.slice(1).join('/')
  const q = new URLSearchParams(queryPart).get('q') ?? ''

  switch (head) {
    case '':
      return { name: 'home' }
    case 'knowledge':
      return rest ? { name: 'knowledgeDetail', id: rest } : { name: 'knowledge' }
    case 'insights':
      return rest ? { name: 'insightDetail', id: rest } : { name: 'insights' }
    case 'sources':
      return rest ? { name: 'sourceDetail', id: rest } : { name: 'sources' }
    case 'record':
      return rest ? { name: 'recordDetail', id: rest } : { name: 'notFound', path: h }
    case 'search':
      return { name: 'search', q }
    case 'ask':
      return { name: 'ask', q }
    case 'review':
      return { name: 'review' }
    case 'history':
      return { name: 'history' }
    case 'settings':
      return { name: 'settings' }
    default:
      return { name: 'notFound', path: h }
  }
}

/** Stable string key for a route (used to remount/scroll on navigation). */
export function routeKey(route: Route): string {
  if (route.name === 'search') return `search::${route.q}`
  if (route.name === 'ask') return 'ask'
  if ('id' in route) return `${route.name}::${route.id}`
  return route.name
}

/** Section a route belongs to, for nav highlighting ("home" on the home page). */
export type Section = 'home' | 'ask' | 'knowledge' | 'insights' | 'sources' | 'review' | 'history' | 'settings'

export function routeSection(route: Route): Section | null {
  switch (route.name) {
    case 'home':
      return 'home'
    case 'ask':
      return 'ask'
    case 'knowledge':
    case 'knowledgeDetail':
      return 'knowledge'
    case 'insights':
    case 'insightDetail':
      return 'insights'
    case 'sources':
    case 'sourceDetail':
      return 'sources'
    case 'review':
      return 'review'
    case 'history':
      return 'history'
    case 'settings':
      return 'settings'
    default:
      return null
  }
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash))
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}

/** Navigate to a path like "/knowledge" or "/search?q=...". */
export function navigate(to: string): void {
  const target = to.startsWith('/') ? to : `/${to}`
  if (`#${target}` === window.location.hash) return
  window.location.hash = target
}

type LinkProps = {
  to: string
  className?: string
  children: ReactNode
} & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href' | 'className'>

/** Anchor that performs hash-based SPA navigation. */
export function Link({ to, className, children, ...rest }: LinkProps) {
  return (
    <a href={`#${to.startsWith('/') ? to : `/${to}`}`} className={className} {...rest}>
      {children}
    </a>
  )
}

export { decodeId }
