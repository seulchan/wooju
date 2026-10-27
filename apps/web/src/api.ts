import type {
  AiStatus,
  AttentionResponse,
  HistoryItem,
  Job,
  ProposalView,
  SetupStatus,
  BrainRecord,
  ChangesResponse,
  GraphResponse,
  HealthResponse,
  ListResponse,
  OverviewResponse,
  RecentResponse,
  SearchResponse,
  StatsResponse,
  UiState,
} from './types'
import { encodeId } from './lib/paths'

// Same-origin in dev (Vite proxies /api -> :8000) and in any same-host deploy.
const API_BASE = '/api'

/** A recoverable API error (network failure, 5xx, etc.). */
export class ApiError extends Error {}

/** A 404 from a record lookup — handled separately as "not found". */
export class NotFoundError extends ApiError {}

/** Resolve an API path relative to the same-origin backend. */
function apiUrl(path: string): string {
  return path.startsWith('/api') ? path : `${API_BASE}${path}`
}

/** Shared HTTP transport with consistent abort and API error handling. */
export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<T> {
  const url = apiUrl(path)
  let res: Response
  try {
    res = await fetch(url, signal ? { ...init, signal } : init)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError('Could not reach the backend. Is the API running on :8000?')
  }
  if (res.status === 404) throw new NotFoundError('Record not found.')
  if (!res.ok) {
    // Action routes return a message written for the user in `detail`.
    let detail: unknown
    try {
      detail = ((await res.json()) as { detail?: unknown }).detail
    } catch {
      detail = undefined
    }
    throw new ApiError(typeof detail === 'string' ? detail : `Request failed (HTTP ${res.status}).`)
  }
  return (await res.json()) as T
}

/** Generic GET helper with friendly error handling. */
export function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  return apiRequest<T>(path, {}, signal)
}

function qs(params: Record<string, string | undefined | null>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  return entries.length ? `?${new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString()}` : ''
}

export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiGet<HealthResponse>('/api/health', signal)
}

export function fetchStats(signal?: AbortSignal): Promise<StatsResponse> {
  return apiGet<StatsResponse>('/api/stats', signal)
}

export function fetchOverview(signal?: AbortSignal): Promise<OverviewResponse> {
  return apiGet<OverviewResponse>('/api/overview', signal)
}

export function fetchChanges(since?: string | null, signal?: AbortSignal): Promise<ChangesResponse> {
  return apiGet<ChangesResponse>(`/api/changes${qs({ since })}`, signal)
}

/**
 * Fetch the relationship projection for the future Brain Map (Phase 2).
 * Debug/developer bridge only — no graph rendering exists yet (Phase 3).
 */
export function fetchGraph(
  params: { limit?: number; focus?: string; depth?: number; since?: string } = {},
  signal?: AbortSignal,
): Promise<GraphResponse> {
  return apiGet<GraphResponse>(
    `/api/graph${qs({ limit: params.limit != null ? String(params.limit) : undefined, focus: params.focus, depth: params.depth != null ? String(params.depth) : undefined, since: params.since })}`,
    signal,
  )
}

/**
 * Review-worthy items for "What needs attention?" (Phase 4). Deterministic and
 * grounded in Brain semantics only — no invented confidence or conflict.
 */
export function fetchAttention(signal?: AbortSignal): Promise<AttentionResponse> {
  return apiGet<AttentionResponse>('/api/attention', signal)
}

export function fetchUiState(signal?: AbortSignal): Promise<UiState> {
  return apiGet<UiState>('/api/ui-state', signal)
}

export function updateUiState(state: UiState, signal?: AbortSignal): Promise<UiState> {
  return apiRequest<UiState>(
    '/api/ui-state',
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        last_seen_at: state.last_seen_at ?? undefined,
        known: state.known,
      }),
    },
    signal,
  )
}

export function fetchKnowledge(subtype?: string, signal?: AbortSignal): Promise<ListResponse> {
  return apiGet<ListResponse>(`/api/knowledge${qs({ subtype })}`, signal)
}

export function fetchInsights(
  status?: string,
  kind?: string,
  signal?: AbortSignal,
): Promise<ListResponse> {
  return apiGet<ListResponse>(`/api/insights${qs({ status, kind })}`, signal)
}

export function fetchSources(signal?: AbortSignal): Promise<ListResponse> {
  return apiGet<ListResponse>('/api/sources', signal)
}

export function fetchRecent(limit = 20, signal?: AbortSignal): Promise<RecentResponse> {
  return apiGet<RecentResponse>(`/api/recent${qs({ limit: String(limit) })}`, signal)
}

export function fetchRecord(id: string, signal?: AbortSignal): Promise<BrainRecord> {
  return apiGet<BrainRecord>(`/api/records/${encodeId(id)}`, signal)
}

export function searchBrain(
  q: string,
  params: Record<string, string | undefined> = {},
  signal?: AbortSignal,
): Promise<SearchResponse> {
  return apiGet<SearchResponse>(`/api/search${qs({ q, ...params })}`, signal)
}

// ------------------------------------------------------------ app actions

function postJson<T>(path: string, body?: unknown): Promise<T> {
  return apiRequest<T>(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

export function fetchSetup(signal?: AbortSignal): Promise<SetupStatus> {
  return apiGet<SetupStatus>('/api/setup', signal)
}

export function chooseBrain(path: string): Promise<{ brain_path: string; created: boolean }> {
  return postJson('/api/setup/brain', { path })
}

export function chooseAi(
  provider: AiStatus['provider'],
  apiKey?: string,
  model?: string | null,
): Promise<AiStatus> {
  return postJson('/api/setup/ai', { provider, api_key: apiKey, model: model ?? undefined })
}

export interface ModelsResponse {
  running: boolean
  provider: AiStatus['provider']
  current: string | null
  recommended: string
  installed: { name: string; size: number; recommended: boolean }[]
  suggested: { name: string; recommended: boolean; installed: boolean; note: string }[]
}

export function fetchModels(signal?: AbortSignal): Promise<ModelsResponse> {
  return apiGet('/api/setup/ai/models', signal)
}

/** Show the Mac's folder chooser; resolves to null when cancelled. */
export async function pickFolder(): Promise<string | null> {
  return (await postJson<{ path: string | null }>('/api/setup/pick-folder')).path
}

export function uploadFiles(
  files: File[],
): Promise<{ added: Job[]; refused: { file: string; message: string }[] }> {
  const form = new FormData()
  for (const f of files) form.append('files', f, f.name)
  return apiRequest('/api/inbox', { method: 'POST', body: form })
}

export function fetchJobs(signal?: AbortSignal): Promise<{ items: Job[] }> {
  return apiGet('/api/jobs', signal)
}

export function fetchProposals(
  status?: ProposalView['status'],
  signal?: AbortSignal,
): Promise<{ total: number; items: ProposalView[] }> {
  return apiGet(`/api/proposals${qs({ status })}`, signal)
}

export function approveProposal(id: string): Promise<ProposalView> {
  return postJson(`/api/proposals/${encodeURIComponent(id)}/approve`)
}

export function rejectProposal(id: string): Promise<ProposalView> {
  return postJson(`/api/proposals/${encodeURIComponent(id)}/reject`)
}

export function approveProposals(ids: string[]): Promise<{ items: ProposalView[] }> {
  return postJson('/api/proposals/approve', { ids })
}

export function fetchHistory(signal?: AbortSignal): Promise<{ items: HistoryItem[] }> {
  return apiGet('/api/history', signal)
}

export function undoChange(id: string): Promise<{ commit: string }> {
  return postJson(`/api/history/${encodeURIComponent(id)}/undo`)
}

export function pullModel(model?: string): Promise<{ model: string | null; state: string | null }> {
  return postJson('/api/setup/ai/pull', model ? { model } : undefined)
}

/** Open a file inside the Brain (e.g. an original PDF in library/) with the Mac's app for it. */
export async function openBrainFile(path: string): Promise<void> {
  await postJson('/api/open-file', { path })
}

/** Open an allowed web page in the user's browser (works inside the desktop app). */
export async function openExternal(url: string): Promise<void> {
  try {
    await postJson('/api/open', { url })
  } catch {
    window.open(url, '_blank', 'noreferrer')
  }
}

// ------------------------------------------------------------ ask, challenge

export interface AskCitation {
  n: number
  id: string
  title: string
  heading: string | null
  category: string
  excerpt: string
}

export interface AskAnswer {
  question: string
  answer: string
  found: boolean
  citations: AskCitation[]
  /** The AI cited nothing; these are the notes it read. */
  related_only?: boolean
  /** What the notes don't cover; empty when they answer fully. */
  missing?: string
  model: string | null
  seconds: number
}

export function askBrain(question: string): Promise<AskAnswer> {
  return postJson('/api/ask', { question })
}

export function challengeInsight(id: string): Promise<ProposalView> {
  return postJson('/api/challenge', { id })
}

// --------------------------------------------------------- Claude connection

export interface ClaudeStatus {
  installed: boolean
  connected: boolean
  outdated: boolean
  config_readable: boolean
  command: string
}

export function fetchClaude(signal?: AbortSignal): Promise<ClaudeStatus> {
  return apiGet('/api/claude', signal)
}

export function connectClaude(): Promise<ClaudeStatus> {
  return postJson('/api/claude/connect')
}

export function disconnectClaude(): Promise<ClaudeStatus> {
  return postJson('/api/claude/disconnect')
}

// ---------------------------------------------------------------- maintainer

/** Set a note's next review date (YYYY-MM-DD), or clear it with null. */
export function setReviewDate(id: string, until: string | null): Promise<ProposalView> {
  return postJson('/api/review-date', { id, until })
}

// ------------------------------------------------------------ meaning search

export interface SearchStatus {
  model: string
  state: 'off' | 'indexing' | 'ready'
  done: number
  total: number
  pulling: boolean
}

export function fetchSearchStatus(signal?: AbortSignal): Promise<SearchStatus> {
  return apiGet('/api/search/status', signal)
}

/** A pasted link (fetched and organized) or a memo (kept as written). */
export function captureText(
  text: string,
): Promise<{ kind: 'link' | 'memo'; file?: string; url?: string; job?: Job; duplicate?: boolean; title?: string }> {
  return postJson('/api/capture', { text })
}

// ------------------------------------------------------------ phone capture

export interface CaptureStatus {
  icloud: { available: boolean; enabled: boolean; folder: string }
  telegram: { enabled: boolean; bot: string | null; paired: boolean; pair_link: string | null }
  recent: { via: string; kind: string; name: string; message: string | null; at: string }[]
}

export function fetchCaptureStatus(signal?: AbortSignal): Promise<CaptureStatus> {
  return apiGet('/api/capture/status', signal)
}

export function setIcloud(enabled: boolean): Promise<CaptureStatus> {
  return postJson('/api/capture/icloud', { enabled })
}

export function connectTelegram(token: string): Promise<CaptureStatus> {
  return postJson('/api/capture/telegram', { token })
}

export function disconnectTelegram(): Promise<CaptureStatus> {
  return postJson('/api/capture/telegram/off')
}

export function retryJob(id: string): Promise<Job> {
  return postJson(`/api/jobs/${encodeURIComponent(id)}/retry`)
}

export function removeJob(id: string): Promise<Job & { message: string }> {
  return postJson(`/api/jobs/${encodeURIComponent(id)}/remove`)
}
