import type { PlotBlock, PlotDot, PlotPair } from "@/lib/tutor/types";
import { compileExpression, CURVE_VARIABLES, SEQUENCE_VARIABLES } from "./expression";

/**
 * A plot as the board draws it. The tool has validated what Célestin sent, but a
 * stored conversation is replayed as it was written, so `sanitise` cleans a plot
 * once, at the edge: every field present, every number finite and inside the
 * tool's limits, every expression compiled. Nothing after it checks again, and
 * nothing in it throws, whatever JSON it is handed.
 */

export type Fn = (v: number) => number;
export type Mark = "filled" | "hollow" | "cross";

export type CleanCurve = {
  f: Fn;
  domain: PlotPair | null;
  start_dot: PlotDot;
  end_dot: PlotDot;
  dashed: boolean;
  label: string | null;
};
export type CleanSequence = { f: Fn; first: number; last: number; label: string | null };
export type CleanPoint = {
  x: number;
  y: number;
  label: string | null;
  mark: Mark;
  guides: boolean;
  show_values: boolean;
};
export type CleanLine = { vertices: PlotPair[]; dashed: boolean; label: string | null };
export type CleanPlot = {
  x_range: PlotPair;
  y_range: PlotPair;
  x_title: string;
  y_title: string;
  x_step: number | null;
  y_step: number | null;
  grid: boolean;
  orthonormal: boolean;
  curves: CleanCurve[];
  sequences: CleanSequence[];
  points: CleanPoint[];
  lines: CleanLine[];
  caption: string | null;
};

// The tool's limits (app/services/tools/plots.py), so a stored plot that predates
// one still draws, and the scales never see a span `toFixed` cannot write.
const MAX_BOUND = 1e6;
const MIN_SPAN = 1e-3;
const FALLBACK_RANGE: PlotPair = [-10, 10];
const STEP_DECIMALS = 4;
// Twice the tool's 30: a stored step over that falls back to automatic ticks.
const MAX_INTERVALS = 60;
// The tool's bounds on an orthonormal window (plots.py), with its float slack:
// [0.3 ; 0.7] over [0 ; 1] is the 0.4 the model wrote, not 0.39999999999999997.
const MIN_ASPECT = 0.4;
const MAX_ASPECT = 2;
const ASPECT_SLACK = 1e-9;
const MAX_CURVES = 6;
const MAX_SEQUENCES = 3;
const MAX_POINTS = 20;
const MAX_LINES = 8;
const MAX_VERTICES = 30;
const MAX_TERMS = 60;
// The model's bounds on n (plot.py): past them, `n + 1` may no longer be a new number.
const MAX_INDEX = 1000;
// Stored labels may predate the 24-character limit; 40 still fits a 400 px board.
const MAX_LABEL = 40;
const MAX_TITLE = 60;
const MAX_CAPTION = 200;

type Loose = Record<string, unknown>;

const record = (v: unknown): Loose =>
  typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Loose) : {};
const list = (v: unknown, max: number): unknown[] => (Array.isArray(v) ? v.slice(0, max) : []);
const finite = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;

/** Two finite numbers, as written: a vertex. */
function vertex(v: unknown): PlotPair | null {
  if (!Array.isArray(v) || v.length !== 2) return null;
  const a = finite(v[0]);
  const b = finite(v[1]);
  return a === null || b === null ? null : [a, b];
}

/** Two finite numbers, smaller first: a range or a domain. */
function interval(v: unknown): PlotPair | null {
  const p = vertex(v);
  return p === null ? null : [Math.min(p[0], p[1]), Math.max(p[0], p[1])];
}

function range(v: unknown): PlotPair {
  const p = interval(v);
  if (p === null) return FALLBACK_RANGE;
  const [a, b] = p;
  // The tool's float slack: 1.101 − 1.1 is a thousandth, as written.
  return Math.max(Math.abs(a), Math.abs(b)) > MAX_BOUND || b - a < MIN_SPAN - 1e-9
    ? FALLBACK_RANGE
    : p;
}

/** At most `STEP_DECIMALS` decimals, the tool's test: ticks are written with four. */
export function fewDecimals(step: number): boolean {
  const scaled = step * 10 ** STEP_DECIMALS;
  return Math.abs(scaled - Math.round(scaled)) <= 1e-6 * Math.max(1, scaled);
}

function step(v: unknown, [a, b]: PlotPair): number | null {
  const s = finite(v);
  if (s === null || s <= 0 || !fewDecimals(s)) return null;
  const count = (b - a) / s;
  return count >= 1 - 1e-9 && count <= MAX_INTERVALS + 1e-9 ? s : null;
}

function text(v: unknown, max: number): string | null {
  if (typeof v !== "string") return null;
  const trimmed = v.trim();
  return trimmed ? trimmed.slice(0, max) : null;
}

function dot(v: unknown): PlotDot {
  return v === "filled" || v === "hollow" ? v : "none";
}

function mark(v: unknown): Mark {
  return v === "hollow" || v === "cross" ? v : "filled";
}

function curve(v: unknown): CleanCurve | null {
  const c = record(v);
  const f = compileExpression(c["expr"], CURVE_VARIABLES);
  if (f === null) return null;
  return {
    f,
    domain: interval(c["domain"]),
    start_dot: dot(c["start_dot"]),
    end_dot: dot(c["end_dot"]),
    dashed: c["dashed"] === true,
    label: text(c["label"], MAX_LABEL),
  };
}

function sequence(v: unknown): CleanSequence | null {
  const s = record(v);
  const f = compileExpression(s["expr"], SEQUENCE_VARIABLES);
  const first = Math.trunc(finite(s["first"]) ?? 1);
  const last = finite(s["last"]);
  if (f === null || last === null || first < 0 || first > MAX_INDEX) return null;
  const end = Math.trunc(last);
  if (end < first) return null;
  return {
    f,
    first,
    last: Math.min(end, first + MAX_TERMS - 1),
    label: text(s["label"], MAX_LABEL),
  };
}

function point(v: unknown): CleanPoint | null {
  const p = record(v);
  const x = finite(p["x"]);
  const y = finite(p["y"]);
  if (x === null || y === null) return null;
  return {
    x,
    y,
    label: text(p["label"], MAX_LABEL),
    mark: mark(p["mark"]),
    guides: p["guides"] === true,
    show_values: p["show_values"] === true,
  };
}

function line(v: unknown): CleanLine | null {
  const l = record(v);
  const vertices = list(l["vertices"], MAX_VERTICES)
    .map(vertex)
    .filter((p): p is PlotPair => p !== null);
  if (vertices.length < 2) return null;
  return { vertices, dashed: l["dashed"] === true, label: text(l["label"], MAX_LABEL) };
}

const kept = <T>(items: (T | null)[]): T[] => items.filter((i): i is T => i !== null);

export function sanitise(block: PlotBlock): CleanPlot {
  const b = record(block);
  const x_range = range(b["x_range"]);
  const y_range = range(b["y_range"]);
  const aspect = (y_range[1] - y_range[0]) / (x_range[1] - x_range[0]);
  return {
    x_range,
    y_range,
    x_title: text(b["x_title"], MAX_TITLE) ?? "",
    y_title: text(b["y_title"], MAX_TITLE) ?? "",
    x_step: step(b["x_step"], x_range),
    y_step: step(b["y_step"], y_range),
    grid: b["grid"] !== false,
    orthonormal:
      b["orthonormal"] === true &&
      aspect >= MIN_ASPECT - ASPECT_SLACK &&
      aspect <= MAX_ASPECT + ASPECT_SLACK,
    curves: kept(list(b["curves"], MAX_CURVES).map(curve)),
    sequences: kept(list(b["sequences"], MAX_SEQUENCES).map(sequence)),
    points: kept(list(b["points"], MAX_POINTS).map(point)),
    lines: kept(list(b["lines"], MAX_LINES).map(line)),
    caption: text(b["caption"], MAX_CAPTION),
  };
}
