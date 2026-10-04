import type { FigureDraw } from "@/lib/tutor/types";

/**
 * A figure cleaned once, at the component's edge. The tool has validated what
 * Célestin sent, but a stored conversation is replayed as it was written, and the
 * board must never throw: `sanitise` is total over any input and returns null
 * when nothing is left to draw. Everything after it assumes clean data.
 */

export type Pt = [number, number];
export type ShapeStyle = "dashed" | "highlight" | null;

export type CleanShape = {
  draw: FigureDraw;
  of: string[];
  radius: number | null;
  marks: number;
  label: string | null;
  style: ShapeStyle;
};
export type CleanPoint = { name: string; at: Pt };

export type CleanPlane = {
  kind: "plane";
  points: CleanPoint[];
  shapes: CleanShape[];
  xRange: Pt | null;
  yRange: Pt | null;
  axes: boolean;
  grid: boolean;
  marker: "cross" | "dot";
  showValues: boolean;
  caption: string | null;
};

export type Closure = "both" | "left" | "right" | "neither";
export type CleanInterval = {
  start: number | null;
  end: number | null;
  closed: Closure;
  label: string | null;
};
export type CleanMark = { x: number; label: string | null };
export type Convention = "brackets" | "dots" | "hatched";

export type CleanLine = {
  kind: "number_line";
  intervals: CleanInterval[];
  marks: CleanMark[];
  convention: Convention;
  showValues: boolean;
  caption: string | null;
};

export type Layout = "nested" | "overlap" | "separate";
export type CleanSet = { id: string; label: string };
/**
 * `zone` is where the element lands: for nested sets the ring of the deepest
 * listed set (`[i]`), otherwise the sorted indices of its sets; `[]` is outside
 * them all, inside the universe.
 */
export type CleanElement = { text: string; zone: number[] };

export type CleanSets = {
  kind: "sets";
  layout: Layout;
  sets: CleanSet[];
  universe: string | null;
  elements: CleanElement[];
  shade: number[][];
  caption: string | null;
};

export type CleanFigure = CleanPlane | CleanLine | CleanSets;

const DRAWS: readonly FigureDraw[] = [
  "segment",
  "line",
  "ray",
  "vector",
  "polygon",
  "circle",
  "arc",
  "angle",
  "right_angle",
];
const POINT_NAME = /^[A-Z]('{1,2}|_[0-9]{1,2})?$/;
const SET_ID = /^[A-Za-z][A-Za-z0-9]?$/;

const MAX_POINTS = 26;
const MAX_SHAPES = 30;
const MAX_VERTICES = 12;
const MAX_INTERVALS = 4;
const MAX_MARKS = 12;
const MAX_SETS = 5;
const MAX_ELEMENTS = 24;
const MAX_ZONES = 8;
const MAX_LABEL = 80;
const MAX_CAPTION = 200;

/**
 * The largest number a figure holds, in its own units, as the tool bounds it
 * (`_MAX_MAGNITUDE` in `figures.py`). A number beyond it is dropped like a
 * non-finite one, so the board's scale, ticks and window stay exact arithmetic.
 */
export const MAX_MAGNITUDE = 1e6;
/**
 * Below this extent, in the figure's units, a range is unusable and a figure's
 * content sits at one place. The tool refuses anything under 1e-3 (`_MIN_EXTENT`);
 * this only keeps a stored card's tick steps far above what `toFixed` can count.
 */
export const MIN_SPAN = 1e-9;

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
/** A number the board can draw: finite, and within the tool's magnitude. */
const finite = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v) && Math.abs(v) <= MAX_MAGNITUDE;
const text = (v: unknown, max = MAX_LABEL): string | null =>
  typeof v === "string" && v.trim() !== "" && v.length <= max ? v : null;
/** A text kept as written, even blank: a set's name, an element, the universe, as the tool counted them. */
const written = (v: unknown): string | null =>
  typeof v === "string" && v.length > 0 && v.length <= MAX_LABEL ? v : null;

function pair(v: unknown): Pt | null {
  if (!Array.isArray(v) || v.length !== 2) return null;
  const [a, b] = v as unknown[];
  return finite(a) && finite(b) ? [a, b] : null;
}

function range(v: unknown): Pt | null {
  const p = pair(v);
  return p && p[1] - p[0] >= MIN_SPAN ? p : null;
}

/** How many points each shape keeps: the first `max`, and none below `min`. */
const ARITY: Record<Exclude<FigureDraw, "circle">, [number, number]> = {
  segment: [2, 2],
  line: [2, 2],
  ray: [2, 2],
  vector: [2, 2],
  polygon: [3, MAX_VERTICES],
  arc: [3, 3],
  angle: [3, 3],
  right_angle: [3, 3],
};

function shape(raw: unknown, known: Set<string>): CleanShape | null {
  if (!isObj(raw)) return null;
  const draw = DRAWS.find((d) => d === raw["draw"]);
  if (!draw) return null;
  const of = [
    ...new Set(list(raw["of"]).filter((n): n is string => typeof n === "string" && known.has(n))),
  ];
  const style = raw["style"] === "dashed" || raw["style"] === "highlight" ? raw["style"] : null;
  const label = text(raw["label"]);
  const m = raw["marks"];
  const marks =
    (draw === "segment" || draw === "angle") && finite(m)
      ? Math.min(3, Math.max(0, Math.round(m)))
      : 0;
  if (draw === "circle") {
    const r = raw["radius"];
    if (finite(r) && r > 0 && of.length >= 1) {
      return { draw, of: of.slice(0, 1), radius: r, marks: 0, label, style };
    }
    if (of.length < 2) return null;
    return { draw, of: of.slice(0, 2), radius: null, marks: 0, label, style };
  }
  const [min, max] = ARITY[draw];
  if (of.length < min) return null;
  return { draw, of: of.slice(0, max), radius: null, marks, label, style };
}

function plane(raw: Obj): CleanPlane | null {
  const points: CleanPoint[] = [];
  if (isObj(raw["points"])) {
    for (const [name, value] of Object.entries(raw["points"])) {
      const at = pair(value);
      if (at && POINT_NAME.test(name) && points.length < MAX_POINTS) points.push({ name, at });
    }
  }
  const known = new Set(points.map((p) => p.name));
  const shapes = list(raw["shapes"])
    .map((s) => shape(s, known))
    .filter((s): s is CleanShape => s !== null)
    .slice(0, MAX_SHAPES);
  const axes = raw["axes"] === true;
  const grid = raw["grid"] === true;
  if (points.length === 0 && !axes && !grid) return null;
  return {
    kind: "plane",
    points,
    shapes,
    xRange: range(raw["x_range"]),
    yRange: range(raw["y_range"]),
    axes,
    grid,
    marker: raw["marker"] === "dot" ? "dot" : "cross",
    showValues: raw["show_values"] === true,
    caption: text(raw["caption"], MAX_CAPTION),
  };
}

const CLOSURES: readonly Closure[] = ["both", "left", "right", "neither"];
const SWAPPED: Record<Closure, Closure> = {
  both: "both",
  left: "right",
  right: "left",
  neither: "neither",
};

/** A bound: a finite number, null for an infinite end, or undefined when unusable. */
function bound(v: unknown): number | null | undefined {
  if (v === null || v === undefined) return null;
  return finite(v) ? v : undefined;
}

function interval(raw: unknown): CleanInterval | null {
  if (!isObj(raw)) return null;
  let start = bound(raw["start"]);
  let end = bound(raw["end"]);
  if (start === undefined || end === undefined) return null;
  let closed = CLOSURES.find((c) => c === raw["closed"]) ?? "neither";
  if (start !== null && end !== null) {
    if (start === end) return null;
    if (start > end) {
      [start, end] = [end, start];
      closed = SWAPPED[closed];
    }
  }
  // −∞ and +∞ are never included.
  const left = start !== null && (closed === "both" || closed === "left");
  const right = end !== null && (closed === "both" || closed === "right");
  closed = left && right ? "both" : left ? "left" : right ? "right" : "neither";
  return { start, end, closed, label: text(raw["label"]) };
}

function numberLine(raw: Obj): CleanLine | null {
  const intervals = list(raw["intervals"])
    .map(interval)
    .filter((i): i is CleanInterval => i !== null)
    .slice(0, MAX_INTERVALS);
  const marks: CleanMark[] = [];
  for (const m of list(raw["marks"])) {
    if (!isObj(m) || !finite(m["x"]) || marks.some((k) => k.x === m["x"])) continue;
    if (marks.length < MAX_MARKS) marks.push({ x: m["x"], label: text(m["label"]) });
  }
  if (intervals.length === 0 && marks.length === 0) return null;
  const convention = raw["convention"];
  return {
    kind: "number_line",
    intervals,
    marks,
    convention: convention === "dots" || convention === "hatched" ? convention : "brackets",
    showValues: raw["show_values"] === true,
    caption: text(raw["caption"], MAX_CAPTION),
  };
}

/** Where a `within` lands, by the one zone meaning the schema gives every layout. */
export function zoneOf(layout: Layout, ids: string[], within: unknown): number[] {
  const listed = list(within)
    .map((id) => ids.indexOf(typeof id === "string" ? id : ""))
    .filter((i) => i >= 0);
  if (layout === "separate") return listed.slice(0, 1);
  const indices = [...new Set(listed)].sort((a, b) => a - b);
  if (layout === "nested") return indices.length ? [indices[indices.length - 1] as number] : [];
  return indices;
}

export const zoneKey = (zone: number[]) => zone.join("");

function setDiagram(raw: Obj): CleanSets | null {
  const sets: CleanSet[] = [];
  for (const s of list(raw["sets"])) {
    if (!isObj(s)) continue;
    const id = s["id"];
    const label = written(s["label"]);
    if (typeof id !== "string" || !SET_ID.test(id) || label === null) continue;
    if (sets.some((k) => k.id === id) || sets.length >= MAX_SETS) continue;
    sets.push({ id, label });
  }
  if (sets.length === 0) return null;
  const asked = raw["layout"];
  let layout: Layout = asked === "overlap" || asked === "separate" ? asked : "nested";
  if (layout !== "nested" && sets.length < 2) layout = "nested";
  const kept = layout === "nested" ? sets : sets.slice(0, 3);
  const ids = kept.map((s) => s.id);
  const universe = written(raw["universe"]);
  const elements: CleanElement[] = [];
  for (const e of list(raw["elements"])) {
    if (!isObj(e)) continue;
    const t = written(e["text"]);
    if (t === null || elements.length >= MAX_ELEMENTS) continue;
    const zone = zoneOf(layout, ids, e["within"]);
    // An element outside every set needs the universe to stand in.
    if (zone.length === 0 && universe === null) continue;
    elements.push({ text: t, zone });
  }
  const shade: number[][] = [];
  for (const z of list(raw["shade"])) {
    const zone = zoneOf(layout, ids, z);
    if (zone.length === 0 && universe === null) continue;
    if (shade.some((k) => zoneKey(k) === zoneKey(zone)) || shade.length >= MAX_ZONES) continue;
    shade.push(zone);
  }
  return {
    kind: "sets",
    layout,
    sets: kept,
    universe,
    elements,
    shade,
    caption: text(raw["caption"], MAX_CAPTION),
  };
}

/** The figure, clean, or null when nothing drawable is left. Never throws. */
export function sanitise(figure: unknown): CleanFigure | null {
  if (!isObj(figure)) return null;
  switch (figure["kind"]) {
    case "plane":
      return plane(figure);
    case "number_line":
      return numberLine(figure);
    case "sets":
      return setDiagram(figure);
    default:
      return null;
  }
}
