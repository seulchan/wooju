export type HealthStatus = 'ok' | 'misconfigured'

/** Shape of GET /api/health — mirrors backend app.api.models.HealthResponse. */
export interface HealthResponse {
  status: HealthStatus
  api: 'ok'
  brain_path: string | null
  brain_configured: boolean
  brain_exists: boolean
  brain_is_directory: boolean
  brain_valid: boolean
  message: string
  /** Last in-memory (re)scan time; advances when the watcher refreshes the index. */
  indexed_at?: string | null
}

export type Category =
  | 'knowledge'
  | 'insight'
  | 'source'
  | 'memory'
  | 'project'
  | 'area'
  | 'other'

/** Lightweight record view used by list endpoints. */
export interface RecordSummary {
  id: string
  path: string
  title: string
  category: Category
  subtype?: string | null
  status?: string | null
  kind?: string | null
  modified_at?: string | null
  excerpt?: string | null
  derived_from_count?: number
  /** Retired by the user as wrong or obsolete. */
  retired?: boolean
}

export interface ListResponse {
  total: number
  items: RecordSummary[]
}

export interface RecentResponse {
  total: number
  items: RecordSummary[]
}

export interface BrainLink {
  target: string
  label?: string | null
  anchor?: string | null
  resolved_id?: string | null
  /** Title of the linked note, shown instead of its path. */
  title?: string | null
}

export interface ResolvedRef {
  ref: string
  resolved_id?: string | null
  /** Title of the resolved record, for readable derivation links. */
  title?: string | null
}

/** Full record returned by GET /api/records/{id}. */
export interface BrainRecord {
  id: string
  path: string
  title: string
  /** The frontmatter title when the note's heading differs (e.g. a source's original title). */
  original_title?: string | null
  /** Retired by the user as wrong or obsolete (reason and date in metadata). */
  retired?: boolean
  category: Category
  subtype?: string | null
  content: string
  metadata: Record<string, unknown>
  links: BrainLink[]
  modified_at?: string | null
  status?: string | null
  kind?: string | null
  derived_from: string[]
  derived_from_resolved: ResolvedRef[]
  aliases: string[]
}

export interface SearchHit {
  id: string
  path: string
  title: string
  category: Category
  subtype?: string | null
  /** Insight lifecycle status (not surfaced for non-insights). */
  status?: string | null
  kind?: string | null
  score: number
  snippet: string
}

export interface SearchResponse {
  query: string
  total: number
  hits: SearchHit[]
}

export interface StatsResponse {
  total: number
  by_category: Record<string, number>
  by_subtype: Record<string, number>
  by_status: Record<string, number>
  modified_range: { earliest: string | null; latest: string | null }
  indexed_at?: string | null
}

/** One deterministic knowledge grouping (wiki subdirectory). */
export interface MainArea {
  label: string
  count: number
}

/** Current Brain totals for the Home overview — mirrors backend OverviewResponse. */
export interface OverviewResponse {
  knowledge: number
  insight: number
  source: number
  provisional_insights: number
  total: number
  /** Deterministic major knowledge areas; empty when fewer than two exist. */
  main_areas: MainArea[]
  indexed_at?: string | null
}

/**
 * How a record changed. Phase 1 emits only 'added'/'modified' (see backend
 * app.api.models.ChangeItem). The vocabulary is intentionally extensible for later
 * phases (relationships/status changes).
 */
export type ChangeType = 'added' | 'modified'

export interface ChangeItem {
  id: string
  path: string
  title: string
  category: Category
  change_type: ChangeType
  modified_at?: string | null
}

export interface ChangesResponse {
  total: number
  since?: string | null
  items: ChangeItem[]
}

/** UI-only presentation state persisted outside the Brain. */
export interface UiState {
  last_seen_at?: string | null
  known?: string[]
}

/**
 * Relationship projection for the future Brain Map — mirrors backend
 * app.api.models.GraphNode / GraphEdge / GraphMeta / GraphResponse (Phase 2).
 * Not yet rendered; these types exist for the developer/debug bridge to Phase 3.
 */
export type GraphMode = 'overview' | 'focus'
export type GraphEdgeType = 'wikilink' | 'derived_from'

export interface GraphNode {
  id: string
  title: string
  category: Category
  subtype?: string | null
  /** Insight lifecycle status (absent for non-insights). */
  status?: string | null
  modified_at?: string | null
  /** Whether the record was modified within the requested `since` window; null when no window. */
  recent?: boolean | null
}

export interface GraphEdge {
  source: string
  target: string
  /** Only explicit relationships the Brain models. Never evidence/supports/proves. */
  type: GraphEdgeType
}

export interface GraphMeta {
  mode: GraphMode
  focus?: string | null
  depth?: number | null
  limit: number
  since?: string | null
  total_nodes: number
  node_count: number
  edge_count: number
  /** Always false — edge creation times are not knowable from the index. */
  edge_creation_known: boolean
}

export interface GraphResponse {
  nodes: GraphNode[]
  edges: GraphEdge[]
  meta: GraphMeta
}

/**
 * "What needs attention?" — mirrors backend app.api.models.Attention* (Phase 4).
 *
 * The UI surfaces only uncertainty the Brain already represents; it invents no
 * confidence, quality, or conflict. `detail` is the grounded reason (e.g. an
 * unresolved target), never an inference.
 */
export type AttentionGroupKey =
  | 'review_due'
  | 'conflicts'
  | 'grounds_changed'
  | 'rule_errors'
  | 'provisional'
  | 'candidate'
  | 'open_questions'
  | 'contested'
  | 'unresolved_derived_from'
  | 'unresolved_links'

export interface AttentionItem {
  id: string
  path: string
  title: string
  category: Category
  status?: string | null
  /** Grounded reason (e.g. unresolved target/ref); never an inferred judgment. */
  detail?: string | null
}

export interface AttentionGroup {
  key: AttentionGroupKey
  label: string
  /** True total found; `items` may be trimmed for unresolved groups. */
  count: number
  items: AttentionItem[]
}

export interface AttentionResponse {
  groups: AttentionGroup[]
  total: number
}

// ------------------------------------------------------------ app actions

export interface AiStatus {
  provider: 'ollama' | 'openai' | 'anthropic'
  model: string
  ready: boolean
  pulling?: boolean
  ollama_running?: boolean | null
  model_downloaded?: boolean | null
  has_key?: boolean | null
  message?: string | null
}

export interface SetupStatus {
  brain_path: string | null
  brain_ready: boolean
  language: string
  ai: AiStatus
}

export type JobState = 'queued' | 'working' | 'waiting' | 'done' | 'failed'

export interface Job {
  id: string
  file: string
  state: JobState
  message: string | null
  proposal_id: string | null
  created_at: string
  /** The source note it became, once saved. */
  note_id?: string | null
  conflicts?: number
  title?: string | null
}

export interface ProposalView {
  id: string
  title: string
  summary: string
  approval: 'auto' | 'batch' | 'individual'
  status: 'pending' | 'applied' | 'rejected' | 'failed'
  agent: string
  origin: string | null
  created_at: string
  decided_at: string | null
  commit: string | null
  error: string | null
  changes: { op: string; path: string }[]
  preview: string | null
}

export interface HistoryItem {
  id: string
  title: string
  committed_at: string
  paths: string[]
  undoes: string | null
  undone: boolean
}
