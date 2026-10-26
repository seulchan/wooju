/**
 * 2D Brain Map — the Home "What is connected?" section.
 *
 * Renders the Phase 2 relationship projection (`GET /api/graph`, overview mode)
 * as a compact, calm, mostly-static graph. Data comes only from explicit Brain
 * relationships (resolved wikilinks, `derived_from`); nothing is invented.
 *
 * Visual semantics are deliberately restrained:
 *  - Knowledge = filled circle, Insight = diamond (distinct shape, never size,
 *    brightness, or centrality used to imply truth or authority).
 *  - Node size reflects connectivity (degree) purely as a readability cue.
 *  - Insight status shows as a restrained stroke color (label always shown in
 *    the detail chip too — never color-only).
 *  - Recent-change highlighting is **node-level only** (the index has no edge
 *    timestamps; `meta.edge_creation_known` is always false). We never invent
 *    edge recency.
 *
 * Motion: a short fade-in on load and subtle opacity transitions on selection /
 * period change. No continuous animation. `prefers-reduced-motion` is honored.
 */

import { useMemo, useState } from 'react'
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { fetchGraph } from '../api'
import { useAsync } from '../lib/useAsync'
import { adjacency, computeLayout, degrees, nodeRadius } from '../lib/graphLayout'
import { encodeId } from '../lib/paths'
import { Link, navigate } from '../lib/router'
import { statusMeta, titleCase } from '../lib/format'
import { EmptyState, ErrorState, MetaBadge, Spinner, StatusBadge } from './ui'
import type { GraphEdge, GraphNode } from '../types'
import { tr } from '../lib/i18n'

/** Compact overview cap. Readability > completeness; the API bounds the rest. */
const NODE_LIMIT = 40
/** How many of the most-connected nodes keep a label when the map is idle. */
const HUB_LABEL_COUNT = 6
/** Ellipsis limit for on-map node labels. */
const LABEL_MAX = 18

/** Per-node view model passed into the custom React Flow node. */
export type MapNodeData = {
  id: string
  title: string
  category: string
  subtype?: string | null
  status?: string | null
  /** Insight status tone (e.g. "tone-warn") — null for non-insights. */
  statusTone: string | null
  isInsight: boolean
  radius: number
  recent: boolean | null
  selected: boolean
  neighbor: boolean
  hovered: boolean
  dimmed: boolean
  /** Quietly de-emphasized during a recent-change window (no selection, unchanged). */
  quieted: boolean
  /** Whether this node shows its label under the current state (decluttered). */
  showLabel: boolean
}

type MapNodeType = Node<MapNodeData, 'map'>

/** Invisible, centered handles so edges bind to the node center. The opaque
 *  node shape renders above the edge path, so endpoints appear to touch the
 *  border without per-edge geometry math. */
const HANDLE_STYLE = {
  opacity: 0,
  top: '50%',
  left: '50%',
  transform: 'translate(-50%, -50%)',
  width: 1,
  height: 1,
  border: 'none',
  background: 'transparent',
} as const

function BrainMapNode({ data }: NodeProps<MapNodeType>) {
  const r = data.radius
  const size = r * 2
  const cls = [
    'map-node',
    `map-node--${data.category}`,
    data.isInsight ? 'map-node--insight' : 'map-node--knowledge',
    data.statusTone ? `map-node--${data.statusTone}` : '',
    data.selected ? 'is-selected' : '',
    data.neighbor ? 'is-neighbor' : '',
    data.hovered ? 'is-hover' : '',
    data.dimmed ? 'is-dimmed' : '',
    data.quieted ? 'is-quiet' : '',
    data.recent === true ? 'is-recent' : '',
    data.showLabel ? 'has-label' : 'no-label',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div
      className={cls}
      style={{ width: size, height: size }}
      title={`${data.title}${data.status ? ` · ${data.status}` : ''}`}
      data-node-id={data.id}
      data-category={data.category}
      data-insight={data.isInsight ? 'true' : undefined}
      data-recent={data.recent === true ? 'true' : undefined}
    >
      <Handle type="target" position={Position.Left} style={HANDLE_STYLE} />
      <Handle type="source" position={Position.Left} style={HANDLE_STYLE} />
      <svg
        className="map-shape"
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        aria-hidden="true"
      >
        {data.recent === true ? (
          <circle className="map-recent-ring" cx={r} cy={r} r={r - 1} />
        ) : null}
        {data.isInsight ? (
          // Diamond — visually distinct from the Knowledge circle.
          <polygon
            className="map-shape__fill"
            points={`${r},2 ${size - 2},${r} ${r},${size - 2} 2,${r}`}
          />
        ) : (
          <circle className="map-shape__fill" cx={r} cy={r} r={r - 3} />
        )}
      </svg>
      {data.showLabel ? (
        <span className="map-node__label">{truncate(data.title, LABEL_MAX)}</span>
      ) : null}
    </div>
  )
}

const nodeTypes = { map: BrainMapNode } as const

function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s
}

export function BrainMap({ since }: { since: string | null }) {
  const state = useAsync(
    (signal) => fetchGraph({ limit: NODE_LIMIT, since: since ?? undefined }, signal),
    [since],
  )
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [hoveredId, setHoveredId] = useState<string | null>(null)

  if (state.kind === 'loading') return <Spinner label={tr('Mapping connections…')} />
  if (state.kind === 'error') {
    return <ErrorState message={state.message} onRetry={state.retry} />
  }

  const { nodes: gNodes, edges: gEdges, meta } = state.data

  if (gNodes.length === 0) {
    return (
      <EmptyState title={tr('No connections yet')}>
        {tr('Relationships between knowledge and insights will appear here.')}
      </EmptyState>
    )
  }

  return (
    <MapSurface
      gNodes={gNodes}
      gEdges={gEdges}
      totalNodes={meta.total_nodes}
      since={since}
      selectedId={selectedId}
      hoveredId={hoveredId}
      onSelect={setSelectedId}
      onHover={setHoveredId}
    />
  )
}

interface MapSurfaceProps {
  gNodes: GraphNode[]
  gEdges: GraphEdge[]
  totalNodes: number
  since: string | null
  selectedId: string | null
  hoveredId: string | null
  onSelect: (id: string | null) => void
  onHover: (id: string | null) => void
}

function MapSurface({
  gNodes,
  gEdges,
  totalNodes,
  since,
  selectedId,
  hoveredId,
  onSelect,
  onHover,
}: MapSurfaceProps) {
  // Layout is recomputed only when the graph payload changes — NOT on selection
  // — so picking a node never shifts the map (calm/static).
  const layout = useMemo(() => computeLayout(gNodes, gEdges), [gNodes, gEdges])
  const adj = useMemo(() => adjacency(gEdges), [gEdges])
  const deg = useMemo(() => degrees(gNodes, gEdges), [gNodes, gEdges])

  // The few most-connected nodes, for the idle label set. Degree is a
  // readability cue only — it implies nothing about truth or authority.
  const hubIds = useMemo(() => {
    const ranked = [...deg.entries()].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))
    return new Set(ranked.slice(0, HUB_LABEL_COUNT).map(([id]) => id))
  }, [deg])

  const neighborIds = selectedId ? adj.get(selectedId) : null
  const hasRecent = since != null && gNodes.some((n) => n.recent === true)

  const nodes: MapNodeType[] = useMemo(
    () =>
      gNodes.map((n) => {
        const radius = nodeRadius(deg.get(n.id) ?? 0)
        const pt = layout.get(n.id) ?? { x: 0, y: 0 }
        const selected = n.id === selectedId
        const neighbor = neighborIds?.has(n.id) ?? false
        const hovered = n.id === hoveredId
        const dimmed = selectedId != null && !selected && !neighbor
        // During a recent-change window with nothing selected, quietly de-emphasize
        // unchanged nodes so the changed ones stand out (selection takes over otherwise).
        const quieted = hasRecent && selectedId == null && n.recent !== true
        // Declutter: label only what matters right now — a small hub set when
        // idle, the hovered node, and (on selection) the selected node + its
        // direct neighbors. Everything stays reachable by click/tap.
        const idle = selectedId == null && hoveredId == null
        const showLabel = selected || neighbor || hovered || (idle && hubIds.has(n.id))
        const isInsight = n.category === 'insight'
        const data: MapNodeData = {
          id: n.id,
          title: n.title,
          category: n.category,
          subtype: n.subtype,
          status: n.status,
          statusTone: isInsight ? (statusMeta(n.status)?.tone ?? 'tone-neutral') : null,
          isInsight,
          radius,
          recent: n.recent ?? null,
          selected,
          neighbor,
          hovered,
          dimmed,
          quieted,
          showLabel,
        }
        return {
          id: n.id,
          type: 'map',
          position: { x: pt.x - radius, y: pt.y - radius },
          data,
          draggable: false,
          selectable: true,
        }
      }),
    [gNodes, deg, layout, neighborIds, selectedId, hoveredId, hubIds],
  )

  const edges: Edge[] = useMemo(
    () =>
      gEdges.map((e) => {
        const involved =
          selectedId != null && (e.source === selectedId || e.target === selectedId)
        const dimmed = selectedId != null && !involved
        return {
          id: `${e.source}__${e.target}__${e.type}`,
          source: e.source,
          target: e.target,
          type: 'default',
          className: [
            'map-edge',
            `map-edge--${e.type}`,
            involved ? 'is-hot' : '',
            dimmed ? 'is-dim' : '',
          ]
            .filter(Boolean)
            .join(' '),
        }
      }),
    [gEdges, selectedId],
  )

  // Remount the canvas only when the bounded node set changes (a different
  // overview / period) so it re-fits. Selection never changes this signature.
  const signature = `${gNodes.map((n) => n.id).join(',')}|${gEdges.length}|${since ?? ''}`

  const onNodeClick: NodeMouseHandler = (_, node) => {
    onSelect(selectedId === node.id ? null : node.id)
  }
  const onNodeDoubleClick: NodeMouseHandler = (_, node) => {
    navigate(`/record/${encodeId(node.id)}`)
  }

  const selected = selectedId ? gNodes.find((n) => n.id === selectedId) ?? null : null
  const hiddenCount = Math.max(0, totalNodes - gNodes.length)
  // The single most-connected node title (deterministic: degree desc, then title
  // asc). "Most connected" describes the graph's connectivity only — never the
  // truth or authority of a note.
  const mostConnected = useMemo(() => {
    const ranked = gNodes
      .map((n) => ({ title: n.title, d: deg.get(n.id) ?? 0 }))
      .filter((x) => x.d > 0)
      .sort((a, b) => b.d - a.d || (a.title < b.title ? -1 : 1))
    return ranked[0]?.title ?? null
  }, [gNodes, deg])

  return (
    <div className="brain-map">
      <div className="brain-map__viewport" role="group" aria-label="Brain map">
        <ReactFlow
          key={signature}
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodeClick={onNodeClick}
          onNodeDoubleClick={onNodeDoubleClick}
          onNodeMouseEnter={(_, node) => onHover(node.id)}
          onNodeMouseLeave={() => onHover(null)}
          onPaneClick={() => {
            onSelect(null)
            onHover(null)
          }}
          fitView
          fitViewOptions={{ padding: 0.25 }}
          minZoom={0.3}
          maxZoom={1.8}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={22} size={1.3} color="var(--border)" />
          <Controls showInteractive={false} />
        </ReactFlow>
        {selected ? (
          <DetailChip node={selected} onClear={() => onSelect(null)} />
        ) : null}
      </div>
      <MapSummary
        shown={gNodes.length}
        relationships={gEdges.length}
        hiddenCount={hiddenCount}
        mostConnected={mostConnected}
      />
      <MapLegend showRecent={hasRecent} />
    </div>
  )
}

function DetailChip({ node, onClear }: { node: GraphNode; onClear: () => void }) {
  const isInsight = node.category === 'insight'
  return (
    <div className="map-chip" role="status" aria-live="polite">
      <div className="map-chip__head">
        <span className={`map-chip__cat map-chip__cat--${node.category}`}>
          {isInsight ? 'Insight' : titleCase(node.category) ?? node.category}
        </span>
        <button
          type="button"
          className="map-chip__close"
          aria-label="Clear selection"
          onClick={onClear}
        >
          ✕
        </button>
      </div>
      <div className="map-chip__title">{node.title}</div>
      <div className="map-chip__meta">
        {isInsight ? <StatusBadge status={node.status} /> : null}
        <MetaBadge label="Type" value={titleCase(node.subtype)} />
      </div>
      <Link className="btn map-chip__open" to={`/record/${encodeId(node.id)}`}>
        {tr('Open record →')}
      </Link>
    </div>
  )
}

interface MapSummaryProps {
  shown: number
  relationships: number
  hiddenCount: number
  mostConnected: string | null
}

/** User-facing summary: record/relationship counts and, when knowable, the most
 *  connected record. No developer-facing "edge timing" caveat on Home. */
function MapSummary({ shown, relationships, hiddenCount, mostConnected }: MapSummaryProps) {
  return (
    <p className="map-summary" aria-label="Brain map summary">
      <span className="map-summary__count">
        {shown} {shown === 1 ? 'record' : 'records'} · {relationships}{' '}
        {relationships === 1 ? 'explicit relationship' : 'explicit relationships'}
        {hiddenCount > 0 ? ` · +${hiddenCount} more` : ''}
      </span>
      {mostConnected ? (
        <span className="map-summary__note">Most connected: {mostConnected}</span>
      ) : null}
    </p>
  )
}

function MapLegend({ showRecent }: { showRecent: boolean }) {
  return (
    <div className="map-legend" aria-label="Brain map legend">
      <span className="map-legend__item">
        <svg className="map-legend__swatch" viewBox="0 0 12 12" aria-hidden="true">
          <circle cx="6" cy="6" r="5" />
        </svg>
        {tr('Knowledge')}
      </span>
      <span className="map-legend__item">
        <svg className="map-legend__swatch" viewBox="0 0 12 12" aria-hidden="true">
          <polygon points="6,1 11,6 6,11 1,6" />
        </svg>
        {tr('Insight')}
      </span>
      <span className="map-legend__item">
        <span className="map-legend__line map-legend__line--solid" />
        wikilink
      </span>
      <span className="map-legend__item">
        <span className="map-legend__line map-legend__line--dashed" />
        derived&nbsp;from
      </span>
      {showRecent ? (
        <span className="map-legend__item">
          <span className="map-legend__dot" />
          recently changed
        </span>
      ) : null}
    </div>
  )
}
