import { useMemo } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

import type { BrainLink } from '../types'
import { transformWikilinks } from '../lib/wikilinks'

const components: Components = {
  a({ href, children }) {
    if (!href) return <a>{children}</a>
    if (href.startsWith('#unresolved:')) {
      return (
        <span className="wl-unresolved" title="Unresolved link">
          {children}?
        </span>
      )
    }
    if (href.startsWith('#/')) {
      return (
        <a href={href} className="internal-link">
          {children}
        </a>
      )
    }
    return (
      <a href={href} target="_blank" rel="noopener noreferrer nofollow">
        {children}
      </a>
    )
  },
}

/**
 * Render note Markdown safely. Raw HTML is not executed (react-markdown ignores
 * it by default), and `[[wikilinks]]` are rewritten into internal links or
 * non-navigating "unresolved" spans via {@link transformWikilinks}.
 */
export function Markdown({ content, links }: { content: string; links?: BrainLink[] }) {
  const transformed = useMemo(
    () => transformWikilinks(content, links ?? []),
    [content, links],
  )
  return (
    <div className="markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {transformed}
      </ReactMarkdown>
    </div>
  )
}
