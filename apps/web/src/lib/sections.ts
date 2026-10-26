/**
 * Best-effort extraction of well-known epistemic sections from a note body.
 *
 * Insight notes sometimes carry `## Evidence`, `## Challenge`, and `## Boundaries`
 * (or synonym) sections. Surfacing them as distinct, scannable blocks makes the
 * epistemic structure legible. This is presentation only: section text is moved
 * verbatim into callouts, never reinterpreted or relabeled.
 */

export type EpistemicKey = 'evidence' | 'challenge' | 'boundaries'

export interface EpistemicSections {
  evidence?: string
  challenge?: string
  boundaries?: string
  /** Everything else (preamble + non-epistemic sections), for the main body. */
  rest: string
}

const RULES: ReadonlyArray<{ key: EpistemicKey; re: RegExp }> = [
  { key: 'evidence', re: /^(supporting\s+)?evidence$|^grounds$|^support$/i },
  { key: 'challenge', re: /^challenges?$|^counter[- ]?evidence$|^counter-?arguments?$|^contradict(ion|ions|ory)?$/i },
  { key: 'boundaries', re: /^boundar(y|ies)$|^limitations?$|^limits?$|^scope$|^caveats?$|^assumptions?$/i },
]

export function classifyHeading(text: string): EpistemicKey | null {
  const t = text.trim()
  for (const rule of RULES) if (rule.re.test(t)) return rule.key
  return null
}

const H2_RE = /^##[ \t]+(.+?)[ \t]*$/

/**
 * Split a Markdown body into featured epistemic sections + the remaining body.
 * Only level-2 headings are considered (so a note's structure is respected).
 */
export function extractEpistemicSections(content: string): EpistemicSections {
  const out: EpistemicSections = { rest: '' }
  let restBuf: string[] = []
  let curKey: EpistemicKey | null = null
  let curBuf: string[] = []

  const flushRest = () => {
    if (restBuf.length) {
      out.rest += restBuf.join('\n') + '\n'
      restBuf = []
    }
  }
  const flushEpistemic = () => {
    if (!curKey) return
    // Section body excludes its own `##` heading — the callout supplies a label.
    const body = curBuf.join('\n').trim()
    if (body) {
      out[curKey] = out[curKey] ? `${out[curKey]}\n\n${body}` : body
    }
    curKey = null
    curBuf = []
  }

  for (const line of content.split('\n')) {
    const m = H2_RE.exec(line)
    if (m) {
      flushEpistemic()
      const key = classifyHeading(m[1])
      if (key) {
        flushRest()
        curKey = key
        curBuf = []
      } else {
        flushRest()
        restBuf.push(line)
      }
    } else if (curKey) {
      curBuf.push(line)
    } else {
      restBuf.push(line)
    }
  }
  flushEpistemic()
  flushRest()
  out.rest = out.rest.trim()
  return out
}

/**
 * Drop a leading H1 that duplicates the record title (the page header already
 * shows the title) so it isn't rendered twice. Leaves any other H1 intact.
 */
export function stripLeadingH1(content: string, title: string): string {
  const m = /^#[ \t]+(.+?)[ \t]*$/m.exec(content)
  if (m && m.index !== undefined && m.index <= 1 && m[1].trim() === title.trim()) {
    return content.slice(m.index + m[0].length).replace(/^\n+/, '')
  }
  return content
}
