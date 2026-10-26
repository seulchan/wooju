/**
 * Encode/decode a record id for use in URL path segments.
 *
 * Record ids are relative paths (e.g. "wiki/concepts/llm-agent-memory") where
 * the "/" separators are structurally meaningful. We keep those slashes literal
 * and percent-encode every other segment so spaces/CJK/etc. are safe in a URL.
 */
export function encodeId(id: string): string {
  return id
    .split('/')
    .map((seg) => encodeURIComponent(seg))
    .join('/')
}

/** Inverse of {@link encodeId}: decode each segment, tolerating malformed input. */
export function decodeId(raw: string): string {
  return raw
    .split('/')
    .map((seg) => {
      try {
        return decodeURIComponent(seg)
      } catch {
        return seg
      }
    })
    .join('/')
}
