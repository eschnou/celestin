import { FRENCH, type Bound, type Notation } from "../charts/format";
import { linear, niceTicks, type Ticks } from "../charts/scale";
import { textPx } from "./labels";
import { MIN_SPAN, type CleanInterval, type CleanLine, type CleanMark } from "./sanitise";

/**
 * A number line: graduations, the numbers Célestin places, and intervals drawn in
 * the course's convention. Intervals sharing a label are one set: one colour,
 * one lane, one notation (`S = ]−∞ ; 2] ∪ ]5 ; +∞[`). An unlabelled interval
 * is a set of its own, as its notation and the description say; disjoint ones
 * may share a lane when nothing is written over them. The notation is written
 * here, from numbers and closures, never by the model.
 *
 * Hatching belongs to a lane, not to a set: « on hachure ce qui ne convient
 * pas » on that line, so a lane hatches what none of its pieces holds. Two sets
 * sharing the axis, each hatching its own complement, would hatch it whole.
 */

export type Group = { label: string | null; pieces: CleanInterval[] };

/** Colour classes by group, written out whole so Tailwind finds them. */
export const GROUP_COLOURS = [
  { stroke: "stroke-chart-1", fill: "fill-chart-1", text: "text-chart-1" },
  { stroke: "stroke-chart-4", fill: "fill-chart-4", text: "text-chart-4" },
  { stroke: "stroke-chart-2", fill: "fill-chart-2", text: "text-chart-2" },
  { stroke: "stroke-chart-3", fill: "fill-chart-3", text: "text-chart-3" },
] as const;

export const colourOf = (i: number) => GROUP_COLOURS[i % GROUP_COLOURS.length] ?? GROUP_COLOURS[0];

const startOf = (i: CleanInterval) => (i.start === null ? -Infinity : i.start);
const endOf = (i: CleanInterval) => (i.end === null ? Infinity : i.end);
export const closedStart = (i: CleanInterval) => i.closed === "both" || i.closed === "left";
export const closedEnd = (i: CleanInterval) => i.closed === "both" || i.closed === "right";

/**
 * Intervals by set: one group per trimmed label. An unlabelled interval is its own
 * set, except under hatching: hatching shows what does not fit, so the unlabelled
 * pieces there are one solution, one group, one lane — with or without values.
 */
export function groups(intervals: CleanInterval[], hatched = false): Group[] {
  const out: Group[] = [];
  for (const piece of intervals) {
    const label = piece.label?.trim() || null;
    const same =
      label === null
        ? hatched
          ? out.find((g) => g.label === null)
          : undefined
        : out.find((g) => g.label === label);
    if (same) same.pieces.push(piece);
    else out.push({ label, pieces: [piece] });
  }
  for (const g of out) g.pieces.sort((a, b) => startOf(a) - startOf(b));
  return out;
}

/**
 * The lane each group is drawn in, 0 being the axis itself. A group with
 * something written over it (its label, or its notation when values are shown)
 * has a lane of its own, so its label row is its alone; the others share a lane
 * when they do not overlap.
 */
export function groupLanes(gs: Group[], written = gs.map((g) => g.label !== null)): number[] {
  const lanes: { labelled: boolean; end: number }[] = [];
  return gs.map((g, i) => {
    const start = Math.min(...g.pieces.map(startOf));
    const end = Math.max(...g.pieces.map(endOf));
    const labelled = written[i] ?? g.label !== null;
    if (!labelled) {
      const free = lanes.findIndex((l) => !l.labelled && l.end < start);
      const lane = lanes[free];
      if (lane) {
        lane.end = end;
        return free;
      }
    }
    lanes.push({ labelled, end });
    return lanes.length - 1;
  });
}

/** What stands at a bound: the mark's own label when one sits there, else the number. */
function markedBound(value: number | null, marks: CleanMark[]): Bound {
  if (value === null) return null;
  return marks.find((m) => m.x === value)?.label ?? value;
}

/** A bound as the course writes it: the mark's own label when one sits there. */
export function boundText(
  value: number | null,
  infinity: string,
  marks: CleanMark[],
  notation: Notation = FRENCH,
): string {
  return notation.bound(markedBound(value, marks), infinity);
}

/** One interval in the course's notation: `[2 ; 5[`, `]−∞ ; 2]`, `]−∞ ; +∞[`. */
export function intervalNotation(
  piece: CleanInterval,
  marks: CleanMark[] = [],
  notation: Notation = FRENCH,
): string {
  return notation.interval(
    markedBound(piece.start, marks),
    markedBound(piece.end, marks),
    closedStart(piece),
    closedEnd(piece),
  );
}

/** A group as one union: `]−∞ ; 2] ∪ ]5 ; +∞[`. */
export function groupNotation(
  g: Group,
  marks: CleanMark[] = [],
  notation: Notation = FRENCH,
): string {
  return g.pieces.map((p) => intervalNotation(p, marks, notation)).join(" ∪ ");
}

/** What a group's lane says: its label, and its notation only when values are shown. */
export function groupLabel(
  g: Group,
  marks: CleanMark[],
  showValues: boolean,
  notation: Notation = FRENCH,
): string | null {
  if (!showValues) return g.label;
  const written = groupNotation(g, marks, notation);
  return g.label ? `${g.label} = ${written}` : written;
}

/**
 * The same, broken into lines of at most `room` px: after « = » when the first
 * piece does not fit beside the label, and before a « ∪ » when the next piece
 * does not fit. Never inside the model's label or a piece, so each line is whole
 * `$…$`. A single piece wider than `room` still stands alone on its line.
 */
export function groupLabelLines(
  g: Group,
  marks: CleanMark[],
  showValues: boolean,
  room: number,
  notation: Notation = FRENCH,
): string[] {
  if (!showValues) return g.label ? [g.label] : [];
  const [first = "", ...rest] = g.pieces.map((p) => intervalNotation(p, marks, notation));
  const lines: string[] = [];
  let current = g.label ? `${g.label} = ${first}` : first;
  if (g.label && textPx(current) > room) {
    lines.push(`${g.label} =`);
    current = first;
  }
  for (const piece of rest) {
    const next = `${current} ∪ ${piece}`;
    if (textPx(next) <= room) {
      current = next;
    } else {
      lines.push(current);
      current = `∪ ${piece}`;
    }
  }
  lines.push(current);
  return lines;
}

/** Which way a bracket's arms point: `[` right, `]` left. */
export function bracketArms(side: "start" | "end", closed: boolean): 1 | -1 {
  if (side === "start") return closed ? 1 : -1;
  return closed ? -1 : 1;
}

/** A 16 px bracket at x, its 5 px arms pointing `arms`. */
export function bracketPath(x: number, y: number, arms: 1 | -1): string {
  const r = (v: number) => Math.round(v * 100) / 100;
  return `M ${r(x + arms * 5)} ${r(y - 8)} H ${r(x)} V ${r(y + 8)} H ${r(x + arms * 5)}`;
}

/** What the pieces, together, leave out of [lo, hi]: the parts « on hachure ». */
export function complement(pieces: CleanInterval[], lo: number, hi: number): [number, number][] {
  const sorted = [...pieces].sort((a, b) => startOf(a) - startOf(b));
  const out: [number, number][] = [];
  let from = lo;
  for (const p of sorted) {
    const a = Math.max(lo, startOf(p));
    if (a > from) out.push([from, Math.min(a, hi)]);
    from = Math.max(from, Math.min(hi, endOf(p)));
  }
  if (from < hi) out.push([from, hi]);
  return out.filter(([a, b]) => b > a);
}

/**
 * Label rows under the axis: the first row where each label, left to right,
 * clears the one before it by 6 px. Three rows hold any realistic line (√2, 1,4
 * and 1,5 side by side); a crowded one opens more rather than overlap.
 */
export function rowsBelow(items: { at: number; width: number }[]): number[] {
  const order = items.map((_, i) => i).sort((a, b) => (items[a]?.at ?? 0) - (items[b]?.at ?? 0));
  const ends: number[] = [];
  const out = new Array<number>(items.length).fill(0);
  for (const i of order) {
    const item = items[i];
    if (!item) continue;
    const half = item.width / 2;
    let row = ends.findIndex((end) => item.at - half >= end + 6);
    if (row === -1) row = ends.push(-Infinity) - 1;
    ends[row] = item.at + half;
    out[i] = row;
  }
  return out;
}

/** Lane pitch with and without a label row, the rows under the axis, and a label's line. */
export const LANE_WITH_LABEL = 34;
export const LANE_PLAIN = 20;
export const ROW_BELOW = 16;
export const LABEL_LINE = 16;

export type LineLabel = { key: string; x: number; y: number; text: string; rich: boolean };
export type LaidPiece = {
  from: number;
  to: number;
  startOpen: boolean;
  endOpen: boolean;
  /** Pixel x of a finite start or end; null for an infinite one. */
  start: number | null;
  end: number | null;
  closedStart: boolean;
  closedEnd: boolean;
};
export type LaidGroup = {
  index: number;
  lane: number;
  y: number;
  pieces: LaidPiece[];
  /** What is written over the lane, line by line, top to bottom; none for an unlabelled set. */
  labels: { x: number; y: number; text: string }[];
};
/** A lane's hatching: what no piece drawn in that lane holds, from x0 to the arrow. */
export type LaidHatch = { lane: number; y: number; spans: [number, number][] };

export type LineLayout = {
  height: number;
  axisY: number;
  x0: number;
  x1: number;
  ticks: Ticks;
  x: (v: number) => number;
  graduations: number[];
  numbers: LineLabel[];
  /** Every finite bound and mark, each with its tick; `dot` for a mark, unless a hollow or filled end already sits there. */
  bounds: { x: number; mark: boolean; dot: boolean }[];
  groups: LaidGroup[];
  /** One per lane in the hatched convention, none otherwise. */
  hatches: LaidHatch[];
};

/** The number line at width W: range, lanes, labels, every position in px. */
export function lineLayout(fig: CleanLine, W: number, notation: Notation = FRENCH): LineLayout {
  const width = Math.max(W, 120);
  const finite = [
    ...fig.intervals.flatMap((i) => [i.start, i.end]).filter((v): v is number => v !== null),
    ...fig.marks.map((m) => m.x),
  ];
  const [lo, hi] = finite.length ? [Math.min(...finite), Math.max(...finite)] : [-5, 5];
  // Numbers closer than MIN_SPAN sit at one place: the line spans a unit around them.
  const span = hi - lo >= MIN_SPAN ? hi - lo : 0;
  const pad = span > 0 ? 0.15 * span : Math.max(1, Math.abs(lo) / 2);
  const extra = 0.25 * (span > 0 ? span : 2 * pad);
  const leftOpen = fig.intervals.some((i) => i.start === null);
  const rightOpen = fig.intervals.some((i) => i.end === null);
  const x0 = 12;
  const x1 = width - 12;
  const count = Math.min(10, Math.max(4, Math.floor((x1 - x0) / 48)));
  const ticks = niceTicks(
    lo - pad - (leftOpen ? extra : 0),
    hi + pad + (rightOpen ? extra : 0),
    count,
  );
  const x = linear([ticks.lo, ticks.hi], [x0 + 8, x1 - 14]);

  const gs = groups(fig.intervals, fig.convention === "hatched");
  const room = width - 4 - x0;
  const labels = gs.map((g) => groupLabelLines(g, fig.marks, fig.showValues, room, notation));
  const lanes = groupLanes(
    gs,
    labels.map((l) => l.length > 0),
  );
  const laneCount = Math.max(1, ...lanes.map((l) => l + 1));
  const labelled = labels.some((l) => l.length > 0);
  const pitch = labelled || fig.showValues ? LANE_WITH_LABEL : LANE_PLAIN;
  // A label broken over n lines lifts every lane above its own by n − 1 lines.
  const lifted = Array.from({ length: laneCount }, () => 0);
  labels.forEach((l, i) => {
    const lane = lanes[i] ?? 0;
    lifted[lane] = Math.max(lifted[lane] ?? 0, l.length - 1);
  });
  const offsets: number[] = [];
  lifted.reduce((at, more) => {
    offsets.push(at);
    return at + pitch + more * LABEL_LINE;
  }, 0);
  const top = laneCount - 1;
  const axisY = 8 + (offsets[top] ?? 0) + (lifted[top] ?? 0) * LABEL_LINE + (labelled ? 26 : 10);

  // Every finite bound and mark, labelled under the axis in as many rows as it takes.
  const placed = new Map<number, { text: string; rich: boolean; mark: boolean }>();
  for (const v of finite) placed.set(v, { text: notation.number(v), rich: false, mark: false });
  for (const m of fig.marks) {
    placed.set(m.x, { text: m.label ?? notation.number(m.x), rich: m.label !== null, mark: true });
  }
  const entries = [...placed.entries()].sort((a, b) => a[0] - b[0]);
  const rows = rowsBelow(entries.map(([v, l]) => ({ at: x(v), width: textPx(l.text) })));
  const rowY = (row: number) => axisY + 10 + row * ROW_BELOW;
  const numbers: LineLabel[] = entries.map(([v, l], i) => ({
    key: `b${v}`,
    x: x(v),
    y: rowY(rows[i] ?? 0),
    text: l.text,
    rich: l.rich,
  }));
  // Graduation numbers in the first row: every k-th, never crowding a bound's label.
  const widest = Math.max(0, ...ticks.ticks.map((t) => textPx(notation.number(t))));
  const spacing =
    ticks.ticks.length > 1 ? Math.abs(x(ticks.ticks[1] ?? 0) - x(ticks.ticks[0] ?? 0)) : Infinity;
  let every = 1;
  while (every < ticks.ticks.length && spacing * every < widest + 8) every += 1;
  for (const [k, t] of ticks.ticks.entries()) {
    if (k % every !== 0 || placed.has(t)) continue;
    if (numbers.some((n) => Math.abs(n.x - x(t)) < 22)) continue;
    numbers.push({ key: `g${t}`, x: x(t), y: rowY(0), text: notation.number(t), rich: false });
  }
  const rowCount = Math.max(1, ...rows.map((r) => r + 1));

  const clampX = (v: number) => Math.min(x1 - 10, Math.max(x0, v));
  const laid: LaidGroup[] = gs.map((g, index) => {
    const lane = lanes[index] ?? 0;
    const y = axisY - (offsets[lane] ?? 0);
    const pieces: LaidPiece[] = g.pieces.map((p) => ({
      from: p.start === null ? x0 : clampX(x(p.start)),
      to: p.end === null ? x1 - 10 : clampX(x(p.end)),
      startOpen: p.start === null,
      endOpen: p.end === null,
      start: p.start === null ? null : x(p.start),
      end: p.end === null ? null : x(p.end),
      closedStart: closedStart(p),
      closedEnd: closedEnd(p),
    }));
    const lines = labels[index] ?? [];
    const first = pieces[0];
    const widest = Math.max(0, ...lines.map(textPx));
    const lx = Math.max(x0, Math.min(first ? first.from : x0, width - 4 - widest));
    const written = lines.map((text, j) => ({
      x: lx,
      y: y - 17 - (lines.length - 1 - j) * LABEL_LINE,
      text,
    }));
    return { index, lane, y, pieces, labels: written };
  });
  // Once per lane, over every set drawn in it: the complement of their union.
  const hatches: LaidHatch[] =
    fig.convention === "hatched"
      ? Array.from({ length: laneCount }, (_, lane) => laid.filter((g) => g.lane === lane))
          // A lane with nothing on it hatches nothing: an empty lane's complement is the
          // whole axis, which would say that no number fits.
          .map((on, lane) => ({ on, lane }))
          .filter(({ on }) => on.length > 0)
          .map(({ on, lane }) => {
            return {
              lane,
              y: axisY - (offsets[lane] ?? 0),
              spans: complementPx(
                on.flatMap((g) => g.pieces),
                x0,
                x1 - 10,
              ),
            };
          })
      : [];
  // A number placed on an interval's bound keeps its tick and label but no dot, in every
  // convention: the bound's own notation (bracket, dot or hatching) says whether it is
  // included, and a filled dot on an excluded bound would say the opposite.
  const ends = new Set(
    laid
      .flatMap((g) => g.pieces.flatMap((p) => [p.start, p.end]))
      .filter((v): v is number => v !== null),
  );

  return {
    height: axisY + 10 + rowCount * ROW_BELOW + 8,
    axisY,
    x0,
    x1,
    ticks,
    x,
    graduations: ticks.ticks.map(x),
    numbers,
    bounds: entries.map(([v, l]) => ({ x: x(v), mark: l.mark, dot: l.mark && !ends.has(x(v)) })),
    groups: laid,
    hatches,
  };
}

/** The complement of drawn pieces along [x0, x1], in px. */
function complementPx(pieces: LaidPiece[], x0: number, x1: number): [number, number][] {
  const asIntervals: CleanInterval[] = pieces.map((p) => ({
    start: p.startOpen ? null : p.from,
    end: p.endOpen ? null : p.to,
    closed: "neither",
    label: null,
  }));
  return complement(asIntervals, x0, x1);
}
