import type { FlowchartBlock, FlowNodeKind } from "@/lib/tutor/types";

/**
 * A flowchart as the board draws it: nodes by index, never by id.
 *
 * The tool has validated the flowchart, but a stored conversation is replayed as
 * it was written, so `sanitise` cleans it once, at the edge, and everything after
 * it assumes a clean graph. Ids live in a `Map` for lookup only: a plain object
 * keyed by ids would put numeric-looking ones (« 10 », « 2 ») first.
 *
 * A hidden node's text becomes « ? » here and goes no further: not into
 * measurement, labels, keys, the sr-only list or the aria-label.
 */

export type GExit = { to: number; label: string | null };
export type GNode = {
  index: number;
  kind: FlowNodeKind;
  /** « ? » when hidden: the secret is dropped here. */
  text: string;
  hidden: boolean;
  /** At most two for a decision, one otherwise; never to itself, never twice to one node. */
  exits: GExit[];
};
export type Graph = { nodes: GNode[]; path: number[]; caption: string | null };

export const MAX_NODES = 12;
const KINDS: readonly FlowNodeKind[] = ["start", "end", "step", "decision", "io"];

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;
const isName = (v: unknown): v is string => typeof v === "string" && v.length > 0;
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);

export function sanitise(block: FlowchartBlock | unknown): Graph {
  const raw = isRecord(block) ? block : {};
  const index = new Map<string, number>();
  const kept: Record<string, unknown>[] = [];
  for (const node of list(raw["nodes"])) {
    if (kept.length >= MAX_NODES) break;
    if (!isRecord(node) || !isName(node["id"]) || !isName(node["text"])) continue;
    if (index.has(node["id"])) continue;
    index.set(node["id"], kept.length);
    kept.push(node);
  }
  const ids = (v: unknown): number[] =>
    list(v).flatMap((name) => {
      const i = typeof name === "string" ? index.get(name) : undefined;
      return i === undefined ? [] : [i];
    });
  const hidden = new Set(ids(raw["hidden"]));

  const nodes = kept.map((node, i): GNode => {
    const kind = KINDS.find((k) => k === node["kind"]) ?? "step";
    const exits: GExit[] = [];
    for (const exit of list(node["next"])) {
      if (!isRecord(exit) || typeof exit["to"] !== "string") continue;
      const to = index.get(exit["to"]);
      if (to === undefined || to === i || exits.some((e) => e.to === to)) continue;
      const label = exit["label"];
      // A label of spaces only would draw an empty answer: it counts as none.
      const shown = typeof label === "string" && label.trim().length > 0;
      exits.push({ to, label: shown ? label : null });
    }
    const secret = hidden.has(i);
    return {
      index: i,
      kind,
      text: secret ? "?" : (node["text"] as string),
      hidden: secret,
      exits: exits.slice(0, kind === "decision" ? 2 : 1),
    };
  });
  const caption = raw["caption"];
  return {
    nodes,
    path: ids(raw["path"]),
    caption: typeof caption === "string" && caption.length > 0 ? caption : null,
  };
}

/** An edge's id: node `i`'s exit `k`. */
export const edgeId = (i: number, k: number) => i * 2 + k;

/**
 * The order a reader follows: depth-first from the first node, each node's exits
 * in Célestin's order, then any node not reached, in list order.
 */
export function readingOrder(g: Graph): number[] {
  const seen = new Array<boolean>(g.nodes.length).fill(false);
  const order: number[] = [];
  const walk = (u: number) => {
    seen[u] = true;
    order.push(u);
    for (const e of g.nodes[u]?.exits ?? []) if (!seen[e.to]) walk(e.to);
  };
  for (let u = 0; u < g.nodes.length; u++) if (!seen[u]) walk(u);
  return order;
}

export type PathState = {
  /** Nodes on the path before the current one (the current one excluded). */
  visited: Set<number>;
  /** The path's last node: where the walk-through stands. */
  current: number | null;
  /** Edges the path followed, by `edgeId`. */
  edges: Set<number>;
};

export function pathState(g: Graph): PathState {
  const current = g.path.length > 0 ? (g.path[g.path.length - 1] ?? null) : null;
  const visited = new Set(g.path.filter((i) => i !== current));
  const edges = new Set<number>();
  for (let k = 1; k < g.path.length; k++) {
    const [a, b] = [g.path[k - 1] as number, g.path[k] as number];
    const exit = g.nodes[a]?.exits.findIndex((e) => e.to === b) ?? -1;
    if (exit >= 0) edges.add(edgeId(a, exit));
  }
  return { visited, current, edges };
}
