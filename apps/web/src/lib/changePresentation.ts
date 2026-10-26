import type { Category, ChangeItem } from '../types'

/** Semantic record categories that belong in Home's change summary. */
export const CONTENT_CATEGORIES: ReadonlyArray<Category> = [
  'knowledge',
  'insight',
  'source',
  'memory',
  'project',
  'area',
]

/** Stable display labels for the categories supported by the Home summary. */
export const CATEGORY_LABEL: Record<string, string> = {
  knowledge: 'Knowledge',
  insight: 'Insights',
  source: 'Sources',
  memory: 'Memory',
  project: 'Projects',
  area: 'Areas',
}

function categoryNoun(category: string): string {
  switch (category) {
    case 'insight':
      return 'insight'
    case 'source':
      return 'source'
    case 'memory':
      return 'memory'
    case 'project':
      return 'project'
    case 'area':
      return 'area'
    default:
      return 'knowledge'
  }
}

/** Honest per-item label; added/modified comes from the UI-local known set. */
export function changeLabel(item: ChangeItem): string {
  const verb = item.change_type === 'added' ? 'New' : 'Updated'
  return `${verb} ${categoryNoun(item.category)}`
}

/** Summarize changed content in the stable category order used by Home. */
export function summarizeChanges(
  items: ChangeItem[],
): Array<{ category: string; count: number }> {
  const counts = new Map<string, number>()
  for (const item of items) {
    if (!CONTENT_CATEGORIES.includes(item.category)) continue
    counts.set(item.category, (counts.get(item.category) ?? 0) + 1)
  }
  return CONTENT_CATEGORIES.filter((category) => counts.has(category)).map((category) => ({
    category,
    count: counts.get(category) ?? 0,
  }))
}

/** Keep repository/meta-document changes out of the user-facing Home summary. */
export function contentChanges(items: ChangeItem[]): ChangeItem[] {
  return items.filter((item) => CONTENT_CATEGORIES.includes(item.category))
}
