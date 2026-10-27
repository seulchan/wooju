import { useMemo, type MouseEvent } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { openBrainFile, openExternal } from '../api'
import type { BrainLink } from '../types'
import { encodeId } from '../lib/paths'
import { transformWikilinks } from '../lib/wikilinks'

/**
 * Where a link in a note goes.
 *
 * Notes link to each other with relative file paths (`../wiki/x.md`), as any
 * Markdown editor writes them. Those open the note inside Wooju; links to other
 * files in the Brain (an original PDF in `library/`) open on the Mac; web links
 * open in the browser (the desktop window cannot open new windows itself).
 */
export type LinkTarget =
  | { kind: 'internal'; href: string }
  | { kind: 'note'; href: string }
  | { kind: 'file'; path: string }
  | { kind: 'web'; url: string }
  | { kind: 'unresolved' }
  | { kind: 'none' }

export function resolveLink(href: string | undefined, notePath?: string): LinkTarget {
  if (!href) return { kind: 'none' }
  if (href.startsWith('#unresolved:')) return { kind: 'unresolved' }
  if (href.startsWith('#')) return { kind: 'internal', href }
  if (/^https?:\/\//i.test(href)) return { kind: 'web', url: href }
  if (/^[a-z][a-z0-9+.-]*:/i.test(href)) return { kind: 'none' } // mailto:, file:, javascript: …
  // A relative path, resolved against the note's own folder.
  const base = `https://brain.local/${notePath ?? ''}`
  let path: string
  try {
    path = decodeURIComponent(new URL(href.split('#')[0], base).pathname).replace(/^\/+/, '')
  } catch {
    return { kind: 'none' }
  }
  if (!path) return { kind: 'none' }
  if (/\.md$/i.test(path)) return { kind: 'note', href: `#/record/${encodeId(path.replace(/\.md$/i, ''))}` }
  return { kind: 'file', path }
}

function makeComponents(notePath?: string): Components {
  return {
    a({ href, children }) {
      const target = resolveLink(href, notePath)
      switch (target.kind) {
        case 'unresolved':
          return (
            <span className="wl-unresolved" title="Unresolved link">
              {children}?
            </span>
          )
        case 'internal':
        case 'note':
          return (
            <a href={target.href} className="internal-link">
              {children}
            </a>
          )
        case 'file':
          return (
            <a
              href="#"
              className="file-link"
              title={target.path}
              onClick={(e: MouseEvent) => {
                e.preventDefault()
                void openBrainFile(target.path)
              }}
            >
              {children}
            </a>
          )
        case 'web':
          return (
            <a
              href={target.url}
              rel="noopener noreferrer nofollow"
              onClick={(e: MouseEvent) => {
                e.preventDefault()
                void openExternal(target.url)
              }}
            >
              {children}
            </a>
          )
        default:
          return <span>{children}</span>
      }
    },
  }
}

/**
 * Render note Markdown safely. Raw HTML is not executed (react-markdown ignores
 * it by default), and `[[wikilinks]]` are rewritten into internal links or
 * non-navigating "unresolved" spans via {@link transformWikilinks}. Pass the
 * note's `path` so its relative links resolve.
 */
export function Markdown({ content, links, path }: { content: string; links?: BrainLink[]; path?: string }) {
  const transformed = useMemo(() => transformWikilinks(content, links ?? []), [content, links])
  const components = useMemo(() => makeComponents(path), [path])
  return (
    <div className="markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {transformed}
      </ReactMarkdown>
    </div>
  )
}
