import type { Graph } from "./graph";
import { edgeId } from "./graph";
import type { Metrics, Size } from "./shapes";

/**
 * What the board measures before it lays a flowchart out, and the estimate it
 * uses until then (and in jsdom, where nothing has a size).
 *
 * Every node label is measured once at each of the five label widths of the
 * ladder; the sizes do not depend on the board's width, so a resize never
 * re-measures. Hidden nodes are never measured: their box has a fixed size.
 */

/** Label max-widths, widest first. The layout narrows labels before it scales. */
export const LADDER = [220, 160, 120, 90, 64] as const;

export type MeasureItem =
  | { kind: "node"; node: number; rung: number; text: string }
  | { kind: "edge"; edge: number; text: string };

/** Per node, its label's size at each rung (null when hidden); per edge id, its label's size. */
export type LabelSizes = { node: (Size[] | null)[]; edge: (Size | null)[] };

export function measureItems(g: Graph): MeasureItem[] {
  const items: MeasureItem[] = [];
  for (const node of g.nodes) {
    if (node.hidden) continue;
    LADDER.forEach((_, rung) =>
      items.push({ kind: "node", node: node.index, rung, text: node.text }),
    );
  }
  for (const node of g.nodes) {
    node.exits.forEach((exit, k) => {
      if (exit.label !== null)
        items.push({ kind: "edge", edge: edgeId(node.index, k), text: exit.label });
    });
  }
  return items;
}

// The delimiters RichText renders, closely enough for an estimate.
const MATH = /\$\$([\s\S]+?)\$\$|\$(?!\s)([^$]*?)(?<!\s)\$/g;

/** Glyphs a formula shows: a `\command` is one, braces, scripts' markers and spaces none. */
function glyphs(tex: string): number {
  return tex.replace(/\\[A-Za-z]+/g, "#").replace(/[{}^_\s]/g, "").length;
}

function tokens(text: string, font: number): { widths: number[]; frac: boolean } {
  const widths: number[] = [];
  let frac = false;
  const words = (prose: string) => {
    for (const word of prose.split(/\s+/)) if (word) widths.push(word.length * 0.56 * font);
  };
  let pos = 0;
  for (const m of text.matchAll(MATH)) {
    words(text.slice(pos, m.index));
    const tex = m[1] ?? m[2] ?? "";
    const isFrac = tex.includes("\\frac");
    frac ||= isFrac;
    widths.push(glyphs(tex) * 0.6 * font * (isFrac ? 0.6 : 1));
    pos = m.index + m[0].length;
  }
  words(text.slice(pos));
  return { widths, frac };
}

/**
 * A label's size before it is measured: words wrap greedily at `maxW`, a formula
 * is one unbreakable token, and a token wider than `maxW` takes its own line at
 * full width, as `min-width: min-content` lets it.
 */
export function estimateSize(text: string, maxW: number, font: number, line: number): Size {
  const { widths, frac } = tokens(text, font);
  const space = 0.28 * font;
  const lines: number[] = [];
  let current = 0;
  let count = 0;
  for (const w of widths) {
    if (count > 0 && current + space + w <= maxW) {
      current += space + w;
      count += 1;
    } else {
      if (count > 0) lines.push(current);
      current = w;
      count = 1;
    }
  }
  lines.push(current);
  return { w: Math.max(...lines), h: lines.length * line + (frac ? 0.8 * line : 0) };
}

/** An exit label on one line, in the edge font (semibold, so a little wider). */
export function estimateLine(text: string, font: number, line: number): Size {
  const { widths, frac } = tokens(text, font);
  const sum = widths.reduce((a, b) => a + b, 0) * 1.05;
  return {
    w: sum + 0.28 * font * Math.max(0, widths.length - 1),
    h: line + (frac ? 0.8 * line : 0),
  };
}

export function estimateItem(item: MeasureItem, m: Metrics): Size {
  return item.kind === "node"
    ? estimateSize(item.text, LADDER[item.rung] ?? LADDER[4], m.font, m.line)
    : estimateLine(item.text, m.edgeFont, m.edgeLine);
}

/**
 * Sizes for every item, from what the measure layer reported where it reported a
 * size, estimated elsewhere; `estimated` says whether any was.
 */
export function labelSizes(
  g: Graph,
  items: readonly MeasureItem[],
  measured: readonly (Size | null)[],
  m: Metrics,
): { sizes: LabelSizes; estimated: boolean } {
  const node: (Size[] | null)[] = g.nodes.map(() => null);
  const edge: (Size | null)[] = new Array<Size | null>(g.nodes.length * 2).fill(null);
  let estimated = false;
  items.forEach((item, i) => {
    const got = measured[i];
    let size: Size;
    if (got && got.w > 0 && got.h > 0) size = got;
    else {
      size = estimateItem(item, m);
      estimated = true;
    }
    if (item.kind === "node") (node[item.node] ??= [])[item.rung] = size;
    else edge[item.edge] = size;
  });
  return { sizes: { node, edge }, estimated };
}

/** What the measurements depend on: the items and the fonts, never the width. */
export function sizesKey(items: readonly MeasureItem[], m: Metrics): string {
  const what = items.map((i) =>
    i.kind === "node" ? [i.node, i.rung, i.text] : [-1, i.edge, i.text],
  );
  return JSON.stringify([m.font, m.line, m.edgeFont, m.edgeLine, what]);
}
