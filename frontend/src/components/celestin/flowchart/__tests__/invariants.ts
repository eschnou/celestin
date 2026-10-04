import type { FlowchartBlock, FlowNode, FlowNodeKind } from "@/lib/tutor/types";
import { sanitise, type Graph } from "../graph";
import { arrange, layers, SAME_X, type Layout } from "../layout";
import { labelSizes, measureItems } from "../measure";
import { metricsFor } from "../shapes";

/** The layout of a flowchart at `width`, with estimated label sizes (jsdom has none). */
export function laidOut(block: FlowchartBlock, width: number): { graph: Graph; layout: Layout } {
  const graph = sanitise(block);
  const sizes = labelSizes(graph, measureItems(graph), [], metricsFor(width)).sizes;
  return { graph, layout: arrange(graph, sizes, width) };
}

type Box = { l: number; t: number; r: number; b: number };

type Segment = { edge: number; to: number; x1: number; y1: number; x2: number; y2: number };

/**
 * Two edges into different nodes that run along each other (parallel, closer
 * than SAME_X, for more than 1 px): a reader sees one line that forks, and
 * cannot tell which arrow goes where. Edges into the same node merge on purpose.
 */
export function sharedStretches(layout: Layout): string[] {
  const segments: Segment[] = layout.edges.flatMap((e) =>
    e.points.slice(1).map(([x2, y2], k) => {
      const [x1, y1] = e.points[k]!;
      return { edge: e.id, to: e.to, x1, y1, x2, y2 };
    }),
  );
  const overlap = (a1: number, a2: number, b1: number, b2: number) =>
    Math.min(Math.max(a1, a2), Math.max(b1, b2)) - Math.max(Math.min(a1, a2), Math.min(b1, b2));
  const bad: string[] = [];
  segments.forEach((s, i) => {
    for (const t of segments.slice(i + 1)) {
      if (s.edge === t.edge || s.to === t.to) continue;
      const vertical = (q: Segment) => Math.abs(q.x1 - q.x2) < 0.01;
      const horizontal = (q: Segment) => Math.abs(q.y1 - q.y2) < 0.01;
      const along =
        vertical(s) && vertical(t) && Math.abs(s.x1 - t.x1) < SAME_X
          ? overlap(s.y1, s.y2, t.y1, t.y2)
          : horizontal(s) && horizontal(t) && Math.abs(s.y1 - t.y1) < SAME_X
            ? overlap(s.x1, s.x2, t.x1, t.x2)
            : 0;
      if (along > 1) bad.push(`edges ${s.edge} and ${t.edge} run along each other`);
    }
  });
  return bad;
}

/**
 * What must hold on every drawing: no segment enters a box (a side port's
 * horizontal at its own vertex excepted), no label overlaps a box, a label or
 * another edge's segment, every edge ends at its target's top centre, one
 * arrowhead per target, no two edges into different nodes run along each
 * other, and everything within bounds.
 */
export function violations(layout: Layout): string[] {
  const bad: string[] = [];
  const boxes = layout.nodes.map((n) => ({
    node: n.index,
    decision: n.box.kind === "decision",
    cy: n.cy,
    l: n.x - n.box.w / 2,
    t: n.cy - n.box.h / 2,
    r: n.x + n.box.w / 2,
    b: n.cy + n.box.h / 2,
  }));
  const labels = layout.edges.flatMap((e) =>
    e.label
      ? [
          {
            edge: e.id,
            l: e.label.left,
            t: e.label.top,
            r: e.label.left + e.label.width,
            b: e.label.top + e.label.height,
          },
        ]
      : [],
  );
  const touch = (a: Box, c: Box) => !(a.r < c.l || a.l > c.r || a.b < c.t || a.t > c.b);

  for (const edge of layout.edges) {
    edge.points.forEach(([x1, y1], k) => {
      const next = edge.points[k + 1];
      if (!next) return;
      const [x2, y2] = next;
      const seg = {
        l: Math.min(x1, x2),
        r: Math.max(x1, x2),
        t: Math.min(y1, y2),
        b: Math.max(y1, y2),
      };
      for (const box of boxes) {
        if (
          seg.r <= box.l + 0.5 ||
          seg.l >= box.r - 0.5 ||
          seg.b <= box.t + 0.5 ||
          seg.t >= box.b - 0.5
        )
          continue;
        const sidePort =
          box.node === edge.from && box.decision && y1 === y2 && Math.abs(y1 - box.cy) < 0.5;
        if (!sidePort) bad.push(`edge ${edge.id} enters box ${box.node}`);
      }
      for (const label of labels) {
        if (label.edge !== edge.id && touch(seg, label))
          bad.push(`edge ${edge.id} crosses label ${label.edge}`);
      }
    });
    const end = edge.points[edge.points.length - 1];
    const target = layout.nodes[edge.to];
    if (
      !end ||
      !target ||
      Math.abs(end[0] - target.x) > 0.01 ||
      Math.abs(end[1] - (target.cy - target.box.h / 2)) > 0.01
    )
      bad.push(`edge ${edge.id} does not end at the top of ${edge.to}`);
  }
  for (const label of labels) {
    for (const box of boxes)
      if (touch(label, box)) bad.push(`label ${label.edge} over box ${box.node}`);
  }
  labels.forEach((a, i) => {
    for (const c of labels.slice(i + 1))
      if (touch(a, c)) bad.push(`labels ${a.edge} and ${c.edge}`);
  });
  boxes.forEach((a, i) => {
    for (const c of boxes.slice(i + 1)) if (touch(a, c)) bad.push(`boxes ${a.node} and ${c.node}`);
  });
  const targets = new Set(layout.edges.map((e) => e.to));
  const arrows = layout.arrows.map((a) => a.node);
  if (arrows.length !== new Set(arrows).size || arrows.length !== targets.size)
    bad.push("not one arrowhead per target");
  const inside = (x: number, y: number) =>
    x >= -0.01 && y >= -0.01 && x <= layout.width + 0.01 && y <= layout.height + 0.01;
  for (const box of boxes) {
    if (!inside(box.l, box.t) || !inside(box.r, box.b)) bad.push(`box ${box.node} out of bounds`);
  }
  for (const edge of layout.edges) {
    if (!edge.points.every(([x, y]) => inside(x, y))) bad.push(`edge ${edge.id} out of bounds`);
  }
  for (const label of labels) {
    if (!inside(label.l, label.t) || !inside(label.r, label.b))
      bad.push(`label ${label.edge} out of bounds`);
  }
  return [...bad, ...sharedStretches(layout)];
}

/** A small seeded generator, so a failing fuzz case can be replayed. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const WORDS =
  "calculer la différence les termes afficher lire suite raison quotient vérifier si est constante égal".split(
    " ",
  );

/**
 * A random flowchart the backend accepts, or null: every node reached from the
 * first, every question with one or two labelled exits, at most three per row
 * with a question counting for two, no end, no start.
 */
export function randomChart(rand: () => number): FlowchartBlock | null {
  const pick = <T>(list: readonly T[]): T => list[Math.floor(rand() * list.length)]!;
  const int = (lo: number, hi: number) => lo + Math.floor(rand() * (hi - lo + 1));
  const n = int(3, 12);
  const kinds: FlowNodeKind[] = ["step", "step", "step", "step", "decision", "decision", "io"];
  const nodes: FlowNode[] = Array.from({ length: n }, (_, i) => {
    const kind = pick(kinds);
    let text = Array.from({ length: int(1, 6) }, () => pick(WORDS)).join(" ");
    if (kind === "decision") text = `${text.slice(0, 38)} ?`;
    return { id: `n${i}`, kind, text, next: [] };
  });
  const cap = (node: FlowNode) => (node.kind === "decision" ? 2 : 1);
  const exitsOf = (node: FlowNode) => node.next!;
  for (let i = 1; i < n; i++) {
    const p = nodes[int(0, i - 1)]!;
    const q = nodes[i - 1]!;
    if (exitsOf(p).length < cap(p)) exitsOf(p).push({ to: `n${i}` });
    else if (exitsOf(q).length < cap(q)) exitsOf(q).push({ to: `n${i}` });
  }
  for (let extra = int(0, 3); extra > 0; extra--) {
    const [a, b] = [int(0, n - 1), int(0, n - 1)];
    const from = nodes[a]!;
    // A loop may go back to the first box: only a `start` may not be gone back to.
    if (a !== b && exitsOf(from).length < cap(from) && !exitsOf(from).some((e) => e.to === `n${b}`))
      exitsOf(from).push({ to: `n${b}` });
  }
  const index = (id: string) => Number(id.slice(1));
  const seen = new Set<number>();
  const todo = [0];
  while (todo.length > 0) {
    const u = todo.pop()!;
    if (seen.has(u)) continue;
    seen.add(u);
    for (const e of exitsOf(nodes[u]!)) todo.push(index(e.to));
  }
  if (seen.size !== n) return null;
  for (const node of nodes) {
    // A question without an exit is refused by the tool: it becomes a step.
    if (node.kind === "decision" && exitsOf(node).length === 0) node.kind = "step";
    if (node.kind === "decision")
      exitsOf(node).forEach((e, k) => (e.label = k === 0 ? "oui" : "non"));
  }
  const { row } = layers(nodes.map((node) => exitsOf(node).map((e) => index(e.to))));
  const weight = new Map<number, number>();
  nodes.forEach((node, i) =>
    weight.set(row[i]!, (weight.get(row[i]!) ?? 0) + (node.kind === "decision" ? 2 : 1)),
  );
  if (Math.max(...weight.values()) > 3) return null;
  return { type: "flowchart", nodes };
}

/**
 * The same flowchart with what random texts lack: answers on some steps' arrows,
 * a fraction in some boxes, and some boxes hidden.
 */
export function varied(block: FlowchartBlock, rand: () => number): FlowchartBlock {
  const nodes = block.nodes.map((node) => {
    const next = (node.next ?? []).map((e) => ({ ...e }));
    const first = next[0];
    if (node.kind !== "decision" && first && rand() < 0.2)
      first.label = rand() < 0.5 ? "puis" : "$i > n$";
    const text = rand() < 0.1 ? `$\\frac{u_{n+1}}{u_n}$ ${node.text}` : node.text;
    return { ...node, text, next };
  });
  const hidden = rand() < 0.3 ? nodes.filter(() => rand() < 0.3).map((n) => n.id) : [];
  return { ...block, nodes, hidden };
}
