import { edgeId, type Graph } from "./graph";
import { LADDER, type LabelSizes } from "./measure";
import { boxFor, metricsFor, rhombusHalf, type Box, type Metrics, type Size } from "./shapes";

export { LADDER } from "./measure";
export { METRICS, metricsFor } from "./shapes";

/**
 * Lays a flowchart out: rows, order, x positions, edge routes. Pure, no React.
 *
 * Rows come from a depth-first walk and longest paths (`layers`, shared with the
 * backend's `wide` rule through a case table). Long edges get passages; rows are
 * ordered depth-first with the heavier branch first, then by barycenter sweeps
 * that keep an ordering only when it crosses fewer edges. x positions are an
 * isotonic least-squares fit over each item's footprint, the space it and its
 * exit labels take. Edges are orthogonal: they run on tracks in the gaps between
 * rows, loops in lanes on the sides.
 *
 * Items are indices: nodes first (their index in the graph), then passages. No
 * object is ever keyed by a model id.
 */

export const MIN_SCALE = 0.85;

/** Two verticals closer than this (px) read as one line: edges keep them apart. */
export const SAME_X = 4;

/** Which vertex an exit leaves from: bottom, right or left. */
export type Port = "B" | "R" | "L";

type Loop = { e: number; u: number; v: number };

export type Structure = {
  /** Nodes; items at `n` and after are passages. */
  n: number;
  /** Row of each item. */
  row: number[];
  /** Items of each row, left to right. */
  order: number[][];
  /** Each forward edge's stations: its passages, then its target. */
  chain: Map<number, number[]>;
  loops: Loop[];
  /** Neighbours along forward edges, between consecutive stations. */
  preds: number[][];
  succs: number[][];
  port: Map<number, Port>;
};

/**
 * Each node's row and the loops: the backend's `layers`, index-based
 * (`tests/fixtures/flowchart_layers.json` holds the two together).
 */
export function layers(exits: readonly (readonly number[])[]): {
  row: number[];
  loops: [number, number][];
} {
  const n = exits.length;
  const state = new Array<number>(n).fill(0);
  const loops: [number, number][] = [];
  const finished: number[] = [];
  const walk = (u: number) => {
    state[u] = 1;
    for (const v of exits[u] ?? []) {
      if (v < 0 || v >= n || v === u) continue;
      if (state[v] === 1) loops.push([u, v]);
      else if (state[v] === 0) walk(v);
    }
    state[u] = 2;
    finished.push(u);
  };
  for (let u = 0; u < n; u++) if (state[u] === 0) walk(u);
  const back = new Set(loops.map(([u, v]) => u * n + v));
  const row = new Array<number>(n).fill(0);
  for (let k = finished.length - 1; k >= 0; k--) {
    const u = finished[k]!;
    for (const v of exits[u] ?? []) {
      if (v >= 0 && v < n && v !== u && !back.has(u * n + v))
        row[v] = Math.max(row[v]!, row[u]! + 1);
    }
  }
  return { row, loops };
}

function crossings(order: number[][], succs: number[][]): number {
  const pos = new Map<number, number>();
  for (const items of order) items.forEach((x, i) => pos.set(x, i));
  let count = 0;
  for (let r = 0; r + 1 < order.length; r++) {
    const edges: [number, number][] = [];
    for (const a of order[r]!) for (const b of succs[a]!) edges.push([pos.get(a)!, pos.get(b)!]);
    for (let i = 0; i < edges.length; i++) {
      for (let j = i + 1; j < edges.length; j++) {
        const [[a, b], [c, d]] = [edges[i]!, edges[j]!];
        if ((a - c) * (b - d) < 0) count += 1;
      }
    }
  }
  return count;
}

/** Rows, order, passages and ports: everything that does not depend on the width. */
export function structure(g: Graph): Structure {
  const n = g.nodes.length;
  const exits = g.nodes.map((node) => node.exits.map((e) => e.to));
  const layered = layers(exits);
  const back = new Set(layered.loops.map(([u, v]) => u * n + v));
  const isLoop = (u: number, v: number) => back.has(u * n + v);
  const rows = Math.max(0, ...layered.row) + 1;
  const row = [...layered.row];
  const order: number[][] = Array.from({ length: rows }, () => []);
  const seen: boolean[] = new Array<boolean>(n).fill(false);
  const reach = (x: number) => {
    if (seen[x]) return;
    seen[x] = true;
    order[row[x]!]!.push(x);
  };
  // Nodes reachable through forward exits: a branch's weight.
  const weight = (v: number) => {
    const found = new Set<number>();
    const todo = [v];
    while (todo.length > 0) {
      const x = todo.pop()!;
      if (found.has(x)) continue;
      found.add(x);
      for (const w of exits[x]!) if (!isLoop(x, w)) todo.push(w);
    }
    return found.size;
  };

  // (a) The ordering walk: a decision's heavier branch first, ties in Célestin's order.
  const chain = new Map<number, number[]>();
  let items = n;
  const walk = (u: number) => {
    reach(u);
    const node = g.nodes[u]!;
    const out = node.exits.map((e, k) => ({ v: e.to, k, w: isLoop(u, e.to) ? 0 : weight(e.to) }));
    if (node.kind === "decision") out.sort((a, b) => b.w - a.w || a.k - b.k);
    for (const { v, k } of out) {
      if (isLoop(u, v)) continue;
      const stations: number[] = [];
      for (let r = row[u]! + 1; r < row[v]!; r++) {
        const p = items++;
        row[p] = r;
        seen[p] = false;
        reach(p);
        stations.push(p);
      }
      stations.push(v);
      chain.set(edgeId(u, k), stations);
      if (!seen[v]) walk(v);
    }
  };
  for (let u = 0; u < n; u++) if (!seen[u]) walk(u);

  const preds: number[][] = Array.from({ length: items }, () => []);
  const succs: number[][] = Array.from({ length: items }, () => []);
  for (const [e, stations] of chain) {
    let prev = Math.floor(e / 2);
    for (const s of stations) {
      succs[prev]!.push(s);
      preds[s]!.push(prev);
      prev = s;
    }
  }

  // (b) Barycenter sweeps, keeping an ordering only when it crosses fewer edges.
  let current = order.map((r) => [...r]);
  let best = current.map((r) => [...r]);
  let fewest = crossings(best, succs);
  for (let round = 0; round < 4; round++) {
    for (const down of [true, false]) {
      const range = down
        ? Array.from({ length: rows - 1 }, (_, i) => i + 1)
        : Array.from({ length: rows - 1 }, (_, i) => rows - 2 - i);
      for (const r of range) {
        const ref = current[down ? r - 1 : r + 1]!;
        const pos = new Map(ref.map((x, i) => [x, i] as const));
        const neighbours = down ? preds : succs;
        const key = new Map<number, number>();
        current[r]!.forEach((x, i) => {
          const near = neighbours[x]!;
          key.set(x, near.length > 0 ? near.reduce((s, y) => s + pos.get(y)!, 0) / near.length : i);
        });
        current = current.map((items, j) =>
          j === r ? [...items].sort((a, b) => key.get(a)! - key.get(b)!) : items,
        );
      }
      const c = crossings(current, succs);
      if (c < fewest) {
        fewest = c;
        best = current.map((r) => [...r]);
      }
    }
  }

  // (c) Ports follow the final order: a decision's left answer leaves from the
  // bottom vertex, its right answer from the right one, a loop from a free side.
  const posi = new Map<number, number>();
  for (const items of best) items.forEach((x, i) => posi.set(x, i));
  const port = new Map<number, Port>();
  const loops: Loop[] = [];
  for (const node of g.nodes) {
    const u = node.index;
    const forward = node.exits.map((e, k) => ({ v: e.to, k })).filter(({ v }) => !isLoop(u, v));
    const backward = node.exits.map((e, k) => ({ v: e.to, k })).filter(({ v }) => isLoop(u, v));
    for (const { v, k } of backward) loops.push({ e: edgeId(u, k), u, v });
    if (node.kind !== "decision") {
      node.exits.forEach((_, k) => port.set(edgeId(u, k), "B"));
      continue;
    }
    const first = (k: number) => posi.get(chain.get(edgeId(u, k))![0]!)!;
    forward.sort((a, b) => first(a.k) - first(b.k));
    const taken: Port[] = forward.length === 2 ? ["B", "R"] : forward.length === 1 ? ["B"] : [];
    const free = (["L", "R", "B"] as Port[]).filter((p) => !taken.includes(p));
    forward.forEach(({ k }, i) => port.set(edgeId(u, k), taken[i]!));
    backward.forEach(({ k }, i) => port.set(edgeId(u, k), free[i]!));
  }
  return { n, row, order: best, chain, loops, preds, succs, port };
}

/**
 * Offsets that keep items in order with their footprints `gap` apart, as close
 * as possible (least squares) to the desired positions: pool-adjacent-violators
 * on the desired positions minus the packed offsets.
 */
export function fit(d: number[], eL: number[], eR: number[], gap: number): number[] {
  const off = d.map(() => 0);
  for (let i = 1; i < d.length; i++) off[i] = off[i - 1]! + eR[i - 1]! + gap + eL[i]!;
  const blocks: { s: number; c: number }[] = [];
  d.forEach((v, i) => {
    blocks.push({ s: v - off[i]!, c: 1 });
    while (blocks.length > 1) {
      const [a, b] = [blocks[blocks.length - 2]!, blocks[blocks.length - 1]!];
      if (a.s / a.c <= b.s / b.c) break;
      blocks.pop();
      a.s += b.s;
      a.c += b.c;
    }
  });
  const x: number[] = [];
  for (const b of blocks) for (let k = 0; k < b.c; k++) x.push(b.s / b.c + off[x.length]!);
  return x;
}

export type Rect = { left: number; top: number; width: number; height: number };

export type PlacedNode = {
  index: number;
  row: number;
  /** Centre of the box. */
  x: number;
  cy: number;
  box: Box;
  /** Where the label is written: the measured label, or the whole box for « ? ». */
  label: Rect;
};

export type PlacedEdge = {
  /** `edgeId`: node `from`'s exit `id % 2`. */
  id: number;
  from: number;
  to: number;
  loop: boolean;
  port: Port;
  points: [number, number][];
  label: (Rect & { text: string }) | null;
};

export type Layout = {
  width: number;
  height: number;
  /** 1, or the factor the drawing is shrunk by (never below MIN_SCALE when returned). */
  scale: number;
  /** The ladder level the labels were narrowed to. */
  level: number;
  metrics: Metrics;
  nodes: PlacedNode[];
  edges: PlacedEdge[];
  /** One per edge target: an arrowhead's tip at the target's top centre. */
  arrows: { node: number; x: number; y: number }[];
};

const nodeSize = (sizes: LabelSizes, i: number, rung: number, m: Metrics): Size =>
  sizes.node[i]?.[rung] ?? { w: LADDER[rung] ?? 64, h: m.line };

/** Each node's box at a ladder level: labels narrowed to what the row leaves them. */
function boxesAt(
  g: Graph,
  st: Structure,
  sizes: LabelSizes,
  m: Metrics,
  width: number,
  level: number,
): Box[] {
  const boxes: Box[] = [];
  for (const items of st.order) {
    const nodes = items.filter((i) => i < st.n);
    const passages = items.length - nodes.length;
    const chrome = nodes.reduce(
      (s, i) => s + 2 * m.padX + (g.nodes[i]!.kind === "io" ? 2 * m.skew : 0),
      0,
    );
    const cap =
      (width - (items.length - 1) * m.gapX - passages * m.passage - chrome) /
      Math.max(1, nodes.length);
    const most = Math.min(LADDER[level] ?? LADDER[4], Math.max(LADDER[4], cap));
    const rung = Math.max(
      0,
      LADDER.findIndex((c) => c <= most),
    );
    for (const i of nodes) {
      const node = g.nodes[i]!;
      if (node.hidden) {
        boxes[i] = boxFor(node.kind, { w: 0, h: 0 }, m, true);
      } else if (node.kind === "decision") {
        // The rung that makes the smallest rhombus, whatever the level.
        let bestRung = 0;
        for (let r = 1; r < LADDER.length; r++) {
          if (
            rhombusHalf(nodeSize(sizes, i, r, m), m) <
            rhombusHalf(nodeSize(sizes, i, bestRung, m), m)
          )
            bestRung = r;
        }
        boxes[i] = boxFor("decision", nodeSize(sizes, i, bestRung, m), m, false);
      } else {
        boxes[i] = boxFor(node.kind, nodeSize(sizes, i, rung, m), m, false);
      }
    }
  }
  return boxes;
}

type Placed = Omit<Layout, "scale" | "level">;

function place(g: Graph, st: Structure, sizes: LabelSizes, m: Metrics, boxes: Box[]): Placed {
  const { n, order, row, chain, loops, preds, succs, port } = st;
  const rows = order.length;
  const total = row.length;
  const labelOf = (e: number): Size | null => {
    const text = g.nodes[Math.floor(e / 2)]?.exits[e % 2]?.label;
    if (text === null || text === undefined) return null;
    return sizes.edge[e] ?? { w: text.length * 0.6 * m.edgeFont, h: m.edgeLine };
  };
  const portOf = (e: number): Port => port.get(e) ?? "B";

  // Footprints: half-extents left and right of an item's anchor, its exit labels included.
  const eL = new Array<number>(total).fill(m.passage / 2);
  const eR = new Array<number>(total).fill(m.passage / 2);
  for (let i = 0; i < n; i++) {
    const box = boxes[i]!;
    let [l, r] = [box.w / 2, box.w / 2];
    const half = box.A ?? box.w / 2;
    g.nodes[i]!.exits.forEach((_, k) => {
      const e = edgeId(i, k);
      const label = labelOf(e);
      const lw = label?.w ?? 0;
      const p = portOf(e);
      if (p === "R") r = Math.max(r, half + lw + 10);
      else if (p === "L") l = Math.max(l, half + lw + 10);
      else if (label) r = Math.max(r, lw + 13);
    });
    eL[i] = l;
    eR[i] = r;
  }
  const corner = (u: number, p: Port) => (p === "R" ? eR[u]! : -eL[u]!);

  // How far right of its predecessor each station wants to sit.
  const pair = (a: number, b: number) => a * total + b;
  const delta = new Map<number, number>();
  for (const [e, stations] of chain) {
    const u = Math.floor(e / 2);
    const p = portOf(e);
    let prev = u;
    for (const s of stations) {
      delta.set(pair(prev, s), prev === u && p !== "B" ? corner(u, p) : 0);
      prev = s;
    }
  }
  // A decision's bottom answer sits right under it, its right answer clear beside.
  for (const node of g.nodes) {
    if (node.kind !== "decision") continue;
    const u = node.index;
    let [bottom, right] = [-1, -1];
    node.exits.forEach((_, k) => {
      const stations = chain.get(edgeId(u, k));
      if (!stations) return;
      if (portOf(edgeId(u, k)) === "B") bottom = stations[0]!;
      else if (portOf(edgeId(u, k)) === "R") right = stations[0]!;
    });
    if (bottom < 0 || right < 0) continue;
    const items = order[row[bottom]!]!;
    if (items[items.indexOf(bottom) + 1] === right) {
      const want = eR[bottom]! + m.gapX + eL[right]!;
      delta.set(pair(u, right), Math.max(delta.get(pair(u, right)) ?? 0, want));
    }
  }

  // x: each row fitted, then swept down and up towards its neighbours.
  const x = new Array<number>(total).fill(0);
  const fitRow = (r: number, desired: number[]) => {
    const items = order[r]!;
    const xs = fit(
      desired,
      items.map((i) => eL[i]!),
      items.map((i) => eR[i]!),
      m.gapX,
    );
    items.forEach((i, j) => (x[i] = xs[j]!));
  };
  for (let r = 0; r < rows; r++)
    fitRow(
      r,
      order[r]!.map(() => 0),
    );
  const mean = (values: number[], fallback: number) =>
    values.length > 0 ? values.reduce((a, b) => a + b, 0) / values.length : fallback;
  for (const down of [true, false, true, false, true]) {
    for (let j = 0; j + 1 < rows; j++) {
      const r = down ? j + 1 : rows - 2 - j;
      fitRow(
        r,
        order[r]!.map((i) =>
          down
            ? mean(
                preds[i]!.map((p) => x[p]! + (delta.get(pair(p, i)) ?? 0)),
                x[i]!,
              )
            : mean(
                succs[i]!.map((s) => x[s]! - (delta.get(pair(i, s)) ?? 0)),
                x[i]!,
              ),
        ),
      );
    }
  }

  // Lanes for the loops, outside every footprint.
  let [minLeft, maxRight] = [Infinity, -Infinity];
  for (let i = 0; i < total; i++) {
    minLeft = Math.min(minLeft, x[i]! - eL[i]!);
    maxRight = Math.max(maxRight, x[i]! + eR[i]!);
  }
  const lanes: Record<"left" | "right", [number, number][][]> = { left: [], right: [] };
  const laneOf = new Map<number, { side: "left" | "right"; k: number }>();
  const byLength = [...loops].sort(
    (a, b) => row[a.u]! - row[a.v]! - (row[b.u]! - row[b.v]!) || row[a.v]! - row[b.v]!,
  );
  for (const loop of byLength) {
    const side = portOf(loop.e) === "R" ? "right" : "left";
    // A loop's lane runs from its bar in the gap above v to its bar in the gap
    // below u. Two loops share a lane only when they share no gap: two loops one
    // after the other would otherwise meet in the gap between them and read as one.
    const [lo, hi] = [row[loop.v]! - 1, row[loop.u]!];
    let k = lanes[side].findIndex((used) => used.every(([a, b]) => hi < a || lo > b));
    if (k < 0) {
      lanes[side].push([]);
      k = lanes[side].length - 1;
    }
    lanes[side][k]!.push([lo, hi]);
    laneOf.set(loop.e, { side, k });
  }
  const laneX = (e: number) => {
    const { side, k } = laneOf.get(e)!;
    return side === "left" ? minLeft - m.laneGap - k * m.lane : maxRight + m.laneGap + k * m.lane;
  };

  // Horizontal pieces per gap (g = -1 above row 0, g = r below row r), keyed so
  // that pieces into the same station merge into one bar. `from` is where the
  // vertical that comes down onto the piece is (null when it comes up a lane).
  type Piece = { lo: number; hi: number; key: number; from: number | null };
  const pieces: Piece[][] = Array.from({ length: rows + 1 }, () => []);
  const piece = (gap: number, a: number, b: number, key: number, from: number | null) =>
    pieces[gap + 1]!.push({ lo: Math.min(a, b), hi: Math.max(a, b), key, from });
  const loopKey = (e: number) => -1 - e;
  const clear = (r: number, u: number, x1: number, x2: number) => {
    const [lo, hi] = [Math.min(x1, x2), Math.max(x1, x2)];
    return order[r]!.every((i) => i === u || x[i]! + eR[i]! < lo - 4 || x[i]! - eL[i]! > hi + 4);
  };
  type Head = "B" | "L" | "stub";
  const heads = new Map<number, Head>();
  for (const [e, stations] of chain) {
    const u = Math.floor(e / 2);
    const p = portOf(e);
    const s1 = stations[0]!;
    const cx = x[u]!;
    if (p === "B") {
      heads.set(e, "B");
      if (Math.abs(x[s1]! - cx) >= 1) piece(row[u]!, cx, x[s1]!, s1, cx);
    } else {
      const cxn = cx + corner(u, p);
      const dir = p === "R" ? 1 : -1;
      if ((x[s1]! - cxn) * dir >= -0.5 && clear(row[u]!, u, cx, x[s1]!)) heads.set(e, "L");
      else {
        heads.set(e, "stub");
        piece(row[u]!, cxn, x[s1]!, s1, cxn);
      }
    }
    for (let j = 1; j < stations.length; j++) {
      const [a, b] = [stations[j - 1]!, stations[j]!];
      if (Math.abs(x[b]! - x[a]!) >= 1) piece(row[a]!, x[a]!, x[b]!, b, x[a]!);
    }
  }
  const directLoop = new Set<number>();
  for (const { e, u, v } of loops) {
    const p = portOf(e);
    const lx = laneX(e);
    if (p !== "B" && clear(row[u]!, u, x[u]!, lx)) directLoop.add(e);
    else {
      const from = p === "B" ? x[u]! : x[u]! + corner(u, p);
      piece(row[u]!, from, lx, loopKey(e), from);
    }
    piece(row[v]! - 1, lx, x[v]!, v, null);
  }
  const trackOf = new Map<string, number>();
  const tracks = new Array<number>(rows + 1).fill(0);
  pieces.forEach((list, slot) => {
    const groups = new Map<number, { lo: number; hi: number; from: number[] }>();
    for (const { lo, hi, key, from } of list) {
      const had = groups.get(key) ?? { lo, hi, from: [] };
      if (from !== null) had.from.push(from);
      groups.set(key, { lo: Math.min(had.lo, lo), hi: Math.max(had.hi, hi), from: had.from });
    }
    const bars = [...groups].sort((a, b) => a[1].lo - b[1].lo);
    // A bar into a station goes down at the station's x, a loop's bar up its
    // lane. A bar whose descent comes down at that x must sit on a higher track,
    // or the two verticals would run one over the other and read as one edge.
    const above = bars.map(([key]) => {
      if (key < 0) return [];
      const down = x[key]!;
      return bars.flatMap(([other, bar], i) =>
        other !== key && bar.from.some((f) => Math.abs(f - down) < SAME_X) ? [i] : [],
      );
    });
    const track = new Array<number>(bars.length).fill(-1);
    const onTrack: { lo: number; hi: number }[][] = [];
    for (let placed = 0; placed < bars.length; placed++) {
      // The leftmost bar whose higher bars are placed; in a cycle, the leftmost left.
      let j = bars.findIndex((_, i) => track[i]! < 0 && above[i]!.every((k) => track[k]! >= 0));
      if (j < 0) j = track.indexOf(-1);
      const [key, { lo, hi }] = bars[j]!;
      let t = Math.max(0, ...above[j]!.map((k) => track[k]! + 1));
      while ((onTrack[t] ?? []).some((b) => !(b.hi + 6 < lo || hi + 6 < b.lo))) t++;
      (onTrack[t] ??= []).push({ lo, hi });
      track[j] = t;
      trackOf.set(`${slot - 1}:${key}`, t);
    }
    tracks[slot] = onTrack.length;
  });
  const T = (gap: number) => tracks[gap + 1]!;

  // y: bands, the label zone under each row, then the tracks.
  const band = order.map((items) =>
    Math.max(0, ...items.filter((i) => i < n).map((i) => boxes[i]!.h)),
  );
  const zone = order.map((items) => {
    let z = 0;
    for (const i of items) {
      if (i >= n) continue;
      g.nodes[i]!.exits.forEach((_, k) => {
        const label = labelOf(edgeId(i, k));
        if (label && portOf(edgeId(i, k)) === "B") z = Math.max(z, label.h + 6);
      });
    }
    return Math.max(10, z);
  });
  const top = new Array<number>(rows).fill(0);
  top[0] = m.margin + (T(-1) > 0 ? (T(-1) - 1) * m.track + 16 : 0);
  let height = 0;
  for (let r = 0; r < rows; r++) {
    const busy = zone[r]! + Math.max(0, T(r) - 1) * m.track;
    const gapH =
      r < rows - 1 ? Math.max(m.gapY, busy + 12) : T(r) > 0 || zone[r]! > 10 ? busy + 8 : m.margin;
    if (r + 1 < rows) top[r + 1] = top[r]! + band[r]! + gapH;
    else height = top[r]! + band[r]! + gapH;
  }
  const trackY = (gap: number, key: number) => {
    const t = trackOf.get(`${gap}:${key}`) ?? 0;
    return gap < 0 ? m.margin + 8 + t * m.track : top[gap]! + band[gap]! + zone[gap]! + t * m.track;
  };
  const cy = (i: number) => top[row[i]!]! + band[row[i]!]! / 2;
  const topOf = (i: number) => (i < n ? cy(i) - boxes[i]!.h / 2 : top[row[i]!]!);
  const bottomOf = (i: number) =>
    i < n ? cy(i) + boxes[i]!.h / 2 : top[row[i]!]! + band[row[i]!]!;
  const half = (u: number) => boxes[u]!.A ?? boxes[u]!.w / 2;

  // Routes and exit labels.
  const edges: PlacedEdge[] = [];
  const labelRect = (u: number, p: Port, size: Size): Rect => {
    if (p === "B") return { left: x[u]! + 5, top: bottomOf(u) + 2, width: size.w, height: size.h };
    const y = cy(u) - 3 - size.h;
    return p === "R"
      ? { left: x[u]! + half(u) + 4, top: y, width: size.w, height: size.h }
      : { left: x[u]! - half(u) - 4 - size.w, top: y, width: size.w, height: size.h };
  };
  const edgeLabel = (e: number, u: number, p: Port) => {
    const size = labelOf(e);
    const text = g.nodes[u]!.exits[e % 2]!.label;
    return size && text !== null ? { ...labelRect(u, p, size), text } : null;
  };
  for (const [e, stations] of chain) {
    const u = Math.floor(e / 2);
    const p = portOf(e);
    const s1 = stations[0]!;
    const head = heads.get(e)!;
    let points: [number, number][];
    if (head === "B") {
      points = [[x[u]!, bottomOf(u)]];
      if (Math.abs(x[s1]! - x[u]!) >= 1) {
        const ty = trackY(row[u]!, s1);
        points.push([x[u]!, ty], [x[s1]!, ty]);
      }
      points.push([x[s1]!, topOf(s1)]);
    } else {
      const vx = x[u]! + (p === "R" ? half(u) : -half(u));
      if (head === "L")
        points = [
          [vx, cy(u)],
          [x[s1]!, cy(u)],
          [x[s1]!, topOf(s1)],
        ];
      else {
        const cxn = x[u]! + corner(u, p);
        const ty = trackY(row[u]!, s1);
        points = [
          [vx, cy(u)],
          [cxn, cy(u)],
          [cxn, ty],
          [x[s1]!, ty],
          [x[s1]!, topOf(s1)],
        ];
      }
    }
    for (let j = 1; j < stations.length; j++) {
      const [a, b] = [stations[j - 1]!, stations[j]!];
      points.push([x[a]!, bottomOf(a)]);
      if (Math.abs(x[b]! - x[a]!) >= 1) {
        const ty = trackY(row[a]!, b);
        points.push([x[a]!, ty], [x[b]!, ty]);
      }
      points.push([x[b]!, topOf(b)]);
    }
    const to = stations[stations.length - 1]!;
    edges.push({ id: e, from: u, to, loop: false, port: p, points, label: edgeLabel(e, u, p) });
  }
  for (const { e, u, v } of loops) {
    const p = portOf(e);
    const lx = laneX(e);
    let points: [number, number][];
    if (p === "B") {
      const ty = trackY(row[u]!, loopKey(e));
      points = [
        [x[u]!, bottomOf(u)],
        [x[u]!, ty],
        [lx, ty],
      ];
    } else {
      const vx = x[u]! + (p === "R" ? half(u) : -half(u));
      if (directLoop.has(e))
        points = [
          [vx, cy(u)],
          [lx, cy(u)],
        ];
      else {
        const cxn = x[u]! + corner(u, p);
        const ty = trackY(row[u]!, loopKey(e));
        points = [
          [vx, cy(u)],
          [cxn, cy(u)],
          [cxn, ty],
          [lx, ty],
        ];
      }
    }
    // Back up the lane, then along the bar into the target: « retour au test ».
    const ty = trackY(row[v]! - 1, v);
    points.push([lx, ty], [x[v]!, ty], [x[v]!, topOf(v)]);
    edges.push({ id: e, from: u, to: v, loop: true, port: p, points, label: edgeLabel(e, u, p) });
  }

  const nodes: PlacedNode[] = g.nodes.map((node) => {
    const i = node.index;
    const box = boxes[i]!;
    const label: Rect = node.hidden
      ? { left: x[i]! - box.w / 2, top: cy(i) - box.h / 2, width: box.w, height: box.h }
      : {
          left: x[i]! - box.label.w / 2,
          top: cy(i) - box.label.h / 2,
          width: box.label.w,
          height: box.label.h,
        };
    return { index: i, row: row[i]!, x: x[i]!, cy: cy(i), box, label };
  });
  const targets = [...new Set(edges.map((e) => e.to))];
  const arrows = targets.map((v) => ({ node: v, x: x[v]!, y: topOf(v) }));

  // Bounds over boxes, routes and labels; everything shifts to start at the margin.
  let [minX, maxX, minY, maxY] = [Infinity, -Infinity, Infinity, -Infinity];
  const see = (px: number, py: number) => {
    [minX, maxX, minY, maxY] = [
      Math.min(minX, px),
      Math.max(maxX, px),
      Math.min(minY, py),
      Math.max(maxY, py),
    ];
  };
  for (const p of nodes) {
    see(p.x - p.box.w / 2, p.cy - p.box.h / 2);
    see(p.x + p.box.w / 2, p.cy + p.box.h / 2);
  }
  for (const edge of edges) {
    for (const [px, py] of edge.points) see(px, py);
    if (edge.label) {
      see(edge.label.left, edge.label.top);
      see(edge.label.left + edge.label.width, edge.label.top + edge.label.height);
    }
  }
  const dx = m.margin - minX;
  const dy = Math.max(0, m.margin - minY);
  const shift = <T extends { left: number; top: number }>(r: T): T => ({
    ...r,
    left: r.left + dx,
    top: r.top + dy,
  });
  return {
    width: maxX - minX + 2 * m.margin,
    height: Math.max(height, maxY + m.margin) + dy,
    metrics: m,
    nodes: nodes.map((p) => ({ ...p, x: p.x + dx, cy: p.cy + dy, label: shift(p.label) })),
    edges: edges.map((edge) => ({
      ...edge,
      points: edge.points.map(([px, py]) => [px + dx, py + dy] as [number, number]),
      label: edge.label && shift(edge.label),
    })),
    arrows: arrows.map((a) => ({ ...a, x: a.x + dx, y: a.y + dy })),
  };
}

/**
 * The layout at the first ladder level whose drawing fits `width`, else the
 * narrowest level with the scale it needs (which may be below MIN_SCALE).
 */
export function arrange(
  g: Graph,
  sizes: LabelSizes,
  width: number,
  st: Structure = structure(g),
): Layout {
  const m = metricsFor(width);
  let placed: Placed | null = null;
  let level = 0;
  for (; level < LADDER.length; level++) {
    placed = place(g, st, sizes, m, boxesAt(g, st, sizes, m, width, level));
    if (placed.width <= width + 0.5 || level === LADDER.length - 1) break;
  }
  const done = placed!;
  return { ...done, level, scale: Math.min(1, width / done.width) };
}

/**
 * The flowchart laid out to be drawn at `width`, or null when it would have to
 * shrink below MIN_SCALE: the board then lists the steps instead of scrolling.
 */
export function layoutFlowchart(
  g: Graph,
  sizes: LabelSizes,
  width: number,
  st: Structure = structure(g),
): Layout | null {
  if (g.nodes.length === 0 || width <= 0) return null;
  const layout = arrange(g, sizes, width, st);
  return layout.scale < MIN_SCALE ? null : layout;
}
