import type {
  AttentionResponse,
  BrainRecord,
  ChangesResponse,
  GraphResponse,
  ListResponse,
  OverviewResponse,
  RecordSummary,
  SearchResponse,
  StatsResponse,
  UiState,
} from '../types'

export const knowledgeSummary: RecordSummary = {
  id: 'wiki/concepts/llm-agent-memory',
  path: 'wiki/concepts/llm-agent-memory.md',
  title: 'LLM Agent Memory',
  category: 'knowledge',
  subtype: 'concept',
  status: null,
  kind: null,
  modified_at: '2026-08-01T00:00:00Z',
  excerpt: 'Notes on agent memory systems.',
  derived_from_count: 0,
}

export const insightSummary: RecordSummary = {
  id: 'wiki/insights/pattern',
  path: 'wiki/insights/pattern.md',
  title: 'Memory Consolidation Pattern',
  category: 'insight',
  subtype: 'synthesis',
  status: 'provisional',
  kind: 'pattern',
  modified_at: '2026-08-02T00:00:00Z',
  excerpt: 'A derived pattern about memory.',
  derived_from_count: 1,
}

export const sourceSummary: RecordSummary = {
  id: 'sources/paper',
  path: 'sources/paper.md',
  title: 'A Paper',
  category: 'source',
  subtype: 'paper',
  status: null,
  kind: null,
  modified_at: '2026-08-03T00:00:00Z',
  excerpt: 'Source note text.',
  derived_from_count: 0,
}

export const stats: StatsResponse = {
  total: 3,
  by_category: { knowledge: 1, insight: 1, source: 1 },
  by_subtype: { concept: 1, synthesis: 1, paper: 1 },
  by_status: { provisional: 1 },
  modified_range: { earliest: '2026-08-01T00:00:00Z', latest: '2026-08-03T00:00:00Z' },
  indexed_at: '2026-08-03T00:00:00Z',
}

export const emptyStats: StatsResponse = {
  total: 0,
  by_category: {},
  by_subtype: {},
  by_status: {},
  modified_range: { earliest: null, latest: null },
}

export const overview: OverviewResponse = {
  knowledge: 1,
  insight: 1,
  source: 1,
  provisional_insights: 1,
  total: 3,
  main_areas: [],
  indexed_at: '2026-08-03T00:00:00Z',
}

export const overviewWithAreas: OverviewResponse = {
  ...overview,
  main_areas: [
    { label: 'Concepts', count: 5 },
    { label: 'Overviews', count: 1 },
  ],
}

export const emptyOverview: OverviewResponse = {
  knowledge: 0,
  insight: 0,
  source: 0,
  provisional_insights: 0,
  total: 11, // the template's own docs count here; the user's notes are the three above
  main_areas: [],
}

export const changes: ChangesResponse = {
  total: 3,
  since: '2026-08-01T00:00:00Z',
  items: [
    {
      id: 'wiki/concepts/llm-agent-memory',
      path: 'wiki/concepts/llm-agent-memory.md',
      title: 'LLM Agent Memory',
      category: 'knowledge',
      change_type: 'modified',
      modified_at: '2026-08-01T00:00:00Z',
    },
    {
      id: 'wiki/insights/pattern',
      path: 'wiki/insights/pattern.md',
      title: 'Memory Consolidation Pattern',
      category: 'insight',
      change_type: 'added',
      modified_at: '2026-08-02T00:00:00Z',
    },
    // An "other" record (docs/logs/meta) must NOT appear in Home's change view.
    {
      id: 'docs/KNOWLEDGE',
      path: 'docs/KNOWLEDGE.md',
      title: 'Knowledge Layer',
      category: 'other',
      change_type: 'modified',
      modified_at: '2026-08-02T00:00:00Z',
    },
  ],
}

/** Seven content changes to exercise Home's 5-item cap and the "+N more" note. */
export const manyChanges: ChangesResponse = {
  total: 7,
  since: '2026-08-01T00:00:00Z',
  items: Array.from({ length: 7 }, (_, i) => ({
    id: `wiki/concepts/c${i}`,
    path: `wiki/concepts/c${i}.md`,
    title: `Concept Number ${i}`,
    category: 'knowledge' as const,
    change_type: (i % 2 === 0 ? 'added' : 'modified') as 'added' | 'modified',
    modified_at: `2026-08-0${(i % 9) + 1}T00:00:00Z`,
  })),
}

export const emptyChanges: ChangesResponse = { total: 0, since: null, items: [] }

export const firstRunUiState: UiState = { last_seen_at: null, known: [] }
export const existingUiState: UiState = {
  last_seen_at: '2026-08-01T00:00:00Z',
  known: ['wiki/concepts/llm-agent-memory'],
}

export const knowledgeList: ListResponse = { total: 1, items: [knowledgeSummary] }
export const insightsList: ListResponse = { total: 1, items: [insightSummary] }
export const sourcesList: ListResponse = { total: 1, items: [sourceSummary] }
export const emptyList: ListResponse = { total: 0, items: [] }

export const knowledgeRecord: BrainRecord = {
  id: 'wiki/concepts/llm-agent-memory',
  path: 'wiki/concepts/llm-agent-memory.md',
  title: 'LLM Agent Memory',
  category: 'knowledge',
  subtype: 'concept',
  content:
    '# LLM Agent Memory\n\nNotes on agent memory systems. See [[concepts/retrieval|retrieval]] and [[concepts/missing]].',
  metadata: { title: 'LLM Agent Memory', type: 'concept' },
  links: [
    { target: 'concepts/retrieval', label: 'retrieval', anchor: null, resolved_id: 'wiki/concepts/retrieval' },
    { target: 'concepts/missing', label: null, anchor: null, resolved_id: null },
  ],
  modified_at: '2026-08-01T00:00:00Z',
  status: null,
  kind: null,
  derived_from: [],
  derived_from_resolved: [],
  aliases: ['Agent Memory'],
}

export const insightRecord: BrainRecord = {
  id: 'wiki/insights/pattern',
  path: 'wiki/insights/pattern.md',
  title: 'Memory Consolidation Pattern',
  category: 'insight',
  subtype: 'synthesis',
  content:
    'Intro about a derived pattern.\n\n' +
    '## Evidence\n\nAgents persist context across turns.\n\n' +
    '## Challenge\n\nContext windows are bounded.\n\n' +
    '## Boundaries\n\nApplies only to text agents.\n\n' +
    '## References\n\n- related work',
  metadata: { origin: 'synthesis', kind: 'pattern', status: 'provisional' },
  links: [],
  modified_at: '2026-08-02T00:00:00Z',
  status: 'provisional',
  kind: 'pattern',
  derived_from: ['wiki/concepts/llm-agent-memory'],
  derived_from_resolved: [
    { ref: 'wiki/concepts/llm-agent-memory', resolved_id: 'wiki/concepts/llm-agent-memory', title: 'LLM Agent Memory' },
  ],
  aliases: [],
}

export const sourceRecord: BrainRecord = {
  id: 'sources/paper',
  path: 'sources/paper.md',
  title: 'A Paper',
  category: 'source',
  subtype: 'paper',
  content: 'Source note text. Original artifact in [[library/paper.pdf]].',
  metadata: { title: 'A Paper', url: 'https://example.com/paper.pdf', author: 'J. Doe', year: 2024 },
  links: [{ target: 'library/paper.pdf', label: null, anchor: null, resolved_id: null }],
  modified_at: '2026-08-03T00:00:00Z',
  status: null,
  kind: null,
  derived_from: [],
  derived_from_resolved: [],
  aliases: [],
}

export const searchResponse: SearchResponse = {
  query: 'memory',
  total: 2,
  hits: [
    {
      id: 'wiki/concepts/llm-agent-memory',
      path: 'wiki/concepts/llm-agent-memory.md',
      title: 'LLM Agent Memory',
      category: 'knowledge',
      subtype: 'concept',
      status: null,
      kind: null,
      score: 100,
      snippet: '…agent memory systems…',
    },
    {
      id: 'wiki/insights/pattern',
      path: 'wiki/insights/pattern.md',
      title: 'Memory Consolidation Pattern',
      category: 'insight',
      subtype: 'synthesis',
      status: 'provisional',
      kind: 'pattern',
      score: 10,
      snippet: '…derived pattern about memory…',
    },
  ],
}

export const emptySearch: SearchResponse = { query: 'zzznope', total: 0, hits: [] }

// Graph projection mirrors backend/tests/test_graph.py BRAIN: explicit edges only.
//   a --wikilink--> b        i --derived_from--> a
//   i --wikilink--> s        uses --wikilink--> s
// `recent` is null (no window). graphRecent marks the insight + source changed.
const graphNodes = [
  {
    id: 'wiki/concepts/a',
    title: 'Concept A',
    category: 'knowledge' as const,
    subtype: 'concept',
    status: null,
    modified_at: '2026-07-09T00:00:00Z',
    recent: null,
  },
  {
    id: 'wiki/concepts/b',
    title: 'Concept B',
    category: 'knowledge' as const,
    subtype: 'concept',
    status: null,
    modified_at: '2026-07-09T00:00:00Z',
    recent: null,
  },
  {
    id: 'wiki/insights/i',
    title: 'Derived Insight',
    category: 'insight' as const,
    subtype: 'synthesis',
    status: 'provisional',
    modified_at: '2026-08-07T00:00:00Z',
    recent: null,
  },
  {
    id: 'sources/s',
    title: 'A Source',
    category: 'source' as const,
    subtype: 'paper',
    status: null,
    modified_at: '2026-08-08T00:00:00Z',
    recent: null,
  },
  {
    id: 'wiki/uses',
    title: 'Uses Note',
    category: 'knowledge' as const,
    subtype: 'concept',
    status: null,
    modified_at: '2026-07-20T00:00:00Z',
    recent: null,
  },
]

const graphEdges = [
  { source: 'wiki/concepts/a', target: 'wiki/concepts/b', type: 'wikilink' as const },
  { source: 'wiki/insights/i', target: 'wiki/concepts/a', type: 'derived_from' as const },
  { source: 'wiki/insights/i', target: 'sources/s', type: 'wikilink' as const },
  { source: 'wiki/uses', target: 'sources/s', type: 'wikilink' as const },
]

export const graph: GraphResponse = {
  nodes: graphNodes,
  edges: graphEdges,
  meta: {
    mode: 'overview',
    focus: null,
    depth: null,
    limit: 40,
    since: null,
    total_nodes: 5,
    node_count: 5,
    edge_count: 4,
    edge_creation_known: false,
  },
}

export const graphRecent: GraphResponse = {
  nodes: graphNodes.map((n) =>
    n.id === 'wiki/insights/i' || n.id === 'sources/s'
      ? { ...n, recent: true }
      : { ...n, recent: false },
  ),
  edges: graphEdges,
  meta: { ...graph.meta, since: '2026-08-01T00:00:00Z' },
}

export const emptyGraph: GraphResponse = {
  nodes: [],
  edges: [],
  meta: {
    mode: 'overview',
    focus: null,
    depth: null,
    limit: 40,
    since: null,
    total_nodes: 0,
    node_count: 0,
    edge_count: 0,
    edge_creation_known: false,
  },
}

// Attention mirrors backend/tests/test_attention.py: provisional + candidate
// insights, an open question, and an unresolved derivation. No invented scores.
export const attention: AttentionResponse = {
  groups: [
    {
      key: 'provisional',
      label: 'Provisional insights',
      count: 1,
      items: [
        {
          id: 'wiki/insights/prov',
          path: 'wiki/insights/prov.md',
          title: 'A Provisional Insight',
          category: 'insight',
          status: 'provisional',
          detail: null,
        },
      ],
    },
    {
      key: 'candidate',
      label: 'Candidate insights',
      count: 1,
      items: [
        {
          id: 'wiki/insights/cand',
          path: 'wiki/insights/cand.md',
          title: 'A Candidate Insight',
          category: 'insight',
          status: 'candidate',
          detail: null,
        },
      ],
    },
    {
      key: 'open_questions',
      label: 'Open questions',
      count: 1,
      items: [
        {
          id: 'wiki/questions/q',
          path: 'wiki/questions/q.md',
          title: 'Open Question',
          category: 'knowledge',
          status: null,
          detail: null,
        },
      ],
    },
    {
      key: 'unresolved_derived_from',
      label: 'Unresolved derivations',
      count: 1,
      items: [
        {
          id: 'wiki/insights/baddf',
          path: 'wiki/insights/baddf.md',
          title: 'Insight With Broken Derivation',
          category: 'insight',
          status: 'candidate',
          detail: '[[concepts/ghost]]',
        },
      ],
    },
  ],
  total: 4,
}

export const emptyAttention: AttentionResponse = { groups: [], total: 0 }
