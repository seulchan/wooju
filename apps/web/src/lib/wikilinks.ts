import type { BrainLink } from '../types'

import { encodeId } from './paths'

/**
 * Obsidian-style wikilink parser, mirroring the backend's extraction.
 *
 * Form: `[[target#anchor^block|Label]]`. Embeds (`![[...]]`) are left alone.
 * Used to turn raw `[[x]]` text in a note body into navigable links for the
 * Markdown renderer, resolving targets against the record's pre-parsed links.
 */
const WIKILINK_RE = /(?<!\!)\[\[([^\]\[|^#]+)(?:[#^]([^\]\[|]*))?(?:\|([^\]\[]*))?\]\]/g

/** Map raw link target -> resolved record id (empty string when unresolved). */
export function buildResolvedMap(links: BrainLink[]): Map<string, string> {
  const m = new Map<string, string>()
  for (const link of links) {
    if (link.target) m.set(link.target, link.resolved_id ?? '')
  }
  return m
}

function escapeMd(text: string): string {
  return text.replace(/\\/g, '\\\\').replace(/([[\]])/g, '\\$1')
}

/**
 * Rewrite a note's Markdown so each `[[wikilink]]` becomes either:
 *  - a real internal link `[label](#/record/<id>)` when resolved, or
 *  - `[label](#unresolved:<target>)` when not, which the Markdown renderer
 *    turns into a non-navigating "unresolved" span.
 */
export function transformWikilinks(content: string, links: BrainLink[]): string {
  const resolved = buildResolvedMap(links)
  return content.replace(WIKILINK_RE, (full, targetRaw: string, _anchor: string | null, label: string | null) => {
    const target = (targetRaw ?? '').trim()
    if (!target) return full
    const display = label && label.trim() ? label.trim() : target
    const rid = resolved.get(target)
    if (rid) return `[${escapeMd(display)}](#/record/${encodeId(rid)})`
    return `[${escapeMd(display)}](#unresolved:${encodeURIComponent(target)})`
  })
}
