/**
 * Deterministic graph layout + adjacency for the 2D Brain Map.
 *
 * Positions are computed with d3-force from *seeded* initial coordinates, then
 * frozen — the simulation is run a fixed number of synchronous ticks and never
 * animated. d3-force's forces contain no randomness, so a given graph always
 * lays out the same way (readable + stable across re-renders, never "alive").
 *
 * These helpers are pure (no React, no DOM) so they are trivially unit-testable.
 */

import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from 'd3-force'

import type { GraphEdge, GraphNode } from '../types'

export interface Pt {
  x: number
  y: number
}

interface SimNode extends SimulationNodeDatum {
  id: string
  r: number
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  source: string
  target: string
}

/**
 * Map a record's connectivity (undirected degree) to a node radius.
 *
 * Size is a **graph/readability cue only** — it implies nothing about the
 * truth, authority, or confidence of a note. The band is deliberately narrow so
 * no node dominates the map by merit of being well-linked.
 */
export function nodeRadius(degree: number): number {
  return 13 + Math.min(degree, 5) * 2 // degree 1 -> 15px … degree ≥5 -> 23px
}

/** Undirected degree of each node id over the given edges. */
export function degrees(nodes: GraphNode[], edges: GraphEdge[]): Map<string, number> {
  const deg = new Map<string, number>()
  for (const n of nodes) deg.set(n.id, 0)
  for (const e of edges) {
    if (e.source === e.target) continue
    deg.set(e.source, (deg.get(e.source) ?? 0) + 1)
    deg.set(e.target, (deg.get(e.target) ?? 0) + 1)
  }
  return deg
}

/** Undirected adjacency map (both directions) over edges. */
export function adjacency(edges: GraphEdge[]): Map<string, Set<string>> {
  const adj = new Map<string, Set<string>>()
  const add = (a: string, b: string) => {
    let set = adj.get(a)
    if (!set) {
      set = new Set<string>()
      adj.set(a, set)
    }
    set.add(b)
  }
  for (const e of edges) {
    if (e.source === e.target) continue
    add(e.source, e.target)
    add(e.target, e.source)
  }
  return adj
}

/** Direct (1-hop) neighbors of `id`, or an empty set when it has none. */
export function neighbors(id: string, adj: Map<string, Set<string>>): Set<string> {
  return adj.get(id) ?? new Set<string>()
}

/**
 * Compute frozen, deterministic {x, y} positions for every node via d3-force.
 *
 * Initial coordinates are seeded on a deterministic circle (no RNG), so the
 * result is stable for a given graph payload. Layout is recomputed only when the
 * graph data changes — *not* on node selection — so selecting a node never
 * shifts the map (calm/static). Returns an empty map for an empty node set.
 */
export function computeLayout(nodes: GraphNode[], edges: GraphEdge[]): Map<string, Pt> {
  const out = new Map<string, Pt>()
  if (nodes.length === 0) return out

  const deg = degrees(nodes, edges)
  const simNodes: SimNode[] = nodes.map((n, i) => {
    const angle = (i / nodes.length) * 2 * Math.PI
    // Stagger two concentric rings so the initial spread is not perfectly
    // circular (helps the force layout settle into a readable shape).
    const ring = 100 + (i % 2 === 0 ? 0 : 55)
    return {
      id: n.id,
      r: nodeRadius(deg.get(n.id) ?? 0),
      x: Math.cos(angle) * ring,
      y: Math.sin(angle) * ring,
    }
  })
  const byId = new Set(simNodes.map((s) => s.id))
  const links: SimLink[] = edges
    .filter((e) => e.source !== e.target && byId.has(e.source) && byId.has(e.target))
    .map((e) => ({ source: e.source, target: e.target }))

  const simulation = forceSimulation<SimNode>(simNodes)
    .force(
      'link',
      forceLink<SimNode, SimLink>(links)
        .id((d) => d.id)
        .distance(72)
        .strength(0.45),
    )
    .force('charge', forceManyBody().strength(-280))
    .force('collide', forceCollide<SimNode>().radius((d) => d.r + 10).iterations(2))
    .force('center', forceCenter(0, 0))
    .stop()

  // Run a fixed, deterministic number of ticks then freeze. No animation.
  const ticks = Math.min(320, 120 + nodes.length * 8)
  for (let i = 0; i < ticks; i++) simulation.tick()

  for (const s of simNodes) out.set(s.id, { x: s.x ?? 0, y: s.y ?? 0 })
  return out
}
