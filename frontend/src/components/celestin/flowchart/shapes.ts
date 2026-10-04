import type { FlowNodeKind } from "@/lib/tutor/types";

/**
 * Box sizes and outlines for each kind of node, from its label's measured size.
 * The label always sits inside the outline: a rhombus is sized so that its label
 * rectangle fits, a parallelogram adds its skew on both sides.
 */

export type Size = { w: number; h: number };

export type Metrics = {
  compact: boolean;
  /** Node labels. */
  font: number;
  line: number;
  padX: number;
  padY: number;
  /** Space between the footprints of two items in a row, and between rows. */
  gapX: number;
  gapY: number;
  /** Horizontal edge tracks in a gap, and loop lanes on the sides. */
  track: number;
  lane: number;
  laneGap: number;
  /** A long edge's footprint in a row it crosses. */
  passage: number;
  /** A rhombus is ρ times as wide as it is tall. */
  rho: number;
  padD: number;
  /** Half-width of the smallest rhombus. */
  Amin: number;
  /** Exit labels. */
  edgeFont: number;
  edgeLine: number;
  hiddenW: number;
  hiddenH: number;
  hiddenA: number;
  margin: number;
  /** A parallelogram's slant. */
  skew: number;
  minW: number;
  stepMinH: number;
  pillMinH: number;
  arrowLength: number;
  arrowHalf: number;
};

const NORMAL: Metrics = {
  compact: false,
  font: 13,
  line: 18,
  padX: 10,
  padY: 7,
  gapX: 16,
  gapY: 26,
  track: 8,
  lane: 12,
  laneGap: 12,
  passage: 8,
  rho: 2,
  padD: 7,
  Amin: 48,
  edgeFont: 12,
  edgeLine: 16,
  hiddenW: 64,
  hiddenH: 36,
  hiddenA: 48,
  margin: 2,
  skew: 8,
  minW: 56,
  stepMinH: 36,
  pillMinH: 32,
  arrowLength: 7,
  arrowHalf: 4,
};

const COMPACT: Metrics = {
  ...NORMAL,
  compact: true,
  font: 12,
  line: 16,
  padX: 8,
  padY: 6,
  gapX: 12,
  gapY: 24,
  laneGap: 10,
  padD: 6,
  Amin: 40,
  edgeFont: 11,
  edgeLine: 14,
  hiddenW: 56,
  hiddenH: 32,
  hiddenA: 44,
  arrowLength: 6,
  arrowHalf: 3.5,
};

export const METRICS = { normal: NORMAL, compact: COMPACT } as const;

/** Below this drawing width (a phone's board is about 268 px) the metrics tighten. */
export const COMPACT_BELOW = 360;

export function metricsFor(width: number): Metrics {
  return width < COMPACT_BELOW ? COMPACT : NORMAL;
}

export type Box = {
  kind: FlowNodeKind;
  hidden: boolean;
  w: number;
  h: number;
  /** A rhombus's half-width: where its side vertices are. Null for other shapes. */
  A: number | null;
  /** The label's size inside the box (0 × 0 for a hidden node's « ? »). */
  label: Size;
  rx: number;
};

/** A rhombus's half-width for a label, the label rectangle inside it. */
export function rhombusHalf(label: Size, m: Metrics): number {
  return Math.max(m.Amin, label.w / 2 + (m.rho * label.h) / 2 + m.padD);
}

/**
 * The box for a node. A hidden node's box has a fixed size per kind, so the
 * length of what it hides never shows.
 */
export function boxFor(kind: FlowNodeKind, label: Size, m: Metrics, hidden: boolean): Box {
  if (hidden) {
    if (kind === "decision") {
      const A = m.hiddenA;
      return { kind, hidden, w: 2 * A, h: (2 * A) / m.rho, A, label: { w: 0, h: 0 }, rx: 0 };
    }
    const rx = kind === "start" || kind === "end" ? m.hiddenH / 2 : kind === "step" ? 6 : 0;
    return { kind, hidden, w: m.hiddenW, h: m.hiddenH, A: null, label: { w: 0, h: 0 }, rx };
  }
  switch (kind) {
    case "decision": {
      const A = rhombusHalf(label, m);
      return { kind, hidden, w: 2 * A, h: (2 * A) / m.rho, A, label, rx: 0 };
    }
    case "io": {
      const h = Math.max(m.stepMinH, label.h + 2 * m.padY);
      const w = Math.max(m.minW, label.w + 2 * m.padX + 2 * m.skew);
      return { kind, hidden, w, h, A: null, label, rx: 0 };
    }
    case "start":
    case "end": {
      const h = Math.max(m.pillMinH, label.h + 2 * m.padY);
      const w = Math.max(m.minW, label.w + 2 * m.padX + h / 2);
      return { kind, hidden, w, h, A: null, label, rx: h / 2 };
    }
    case "step": {
      const h = Math.max(m.stepMinH, label.h + 2 * m.padY);
      const w = Math.max(m.minW, label.w + 2 * m.padX);
      return { kind, hidden, w, h, A: null, label, rx: 6 };
    }
  }
}

export type ShapeProps =
  | { tag: "rect"; x: number; y: number; width: number; height: number; rx: number }
  | { tag: "polygon"; points: string };

const pts = (list: [number, number][]) => list.map(([x, y]) => `${x},${y}`).join(" ");

/** The outline of a box centred on (x, cy): a rectangle, a pill, a rhombus or a parallelogram. */
export function shapeProps(box: Box, x: number, cy: number, m: Metrics): ShapeProps {
  const [l, r, t, b] = [x - box.w / 2, x + box.w / 2, cy - box.h / 2, cy + box.h / 2];
  if (box.kind === "decision") {
    return {
      tag: "polygon",
      points: pts([
        [x, t],
        [r, cy],
        [x, b],
        [l, cy],
      ]),
    };
  }
  if (box.kind === "io") {
    return {
      tag: "polygon",
      points: pts([
        [l + m.skew, t],
        [r, t],
        [r - m.skew, b],
        [l, b],
      ]),
    };
  }
  return { tag: "rect", x: l, y: t, width: box.w, height: box.h, rx: box.rx };
}
