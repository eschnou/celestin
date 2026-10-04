import { niceTicks } from "../charts/scale";
import { MIN_SPAN, type CleanPlane, type CleanPoint, type CleanShape, type Pt } from "./sanitise";

/**
 * Plane geometry, from the figure's own units to pixels. The window only ever
 * grows to hold what the figure draws (the tool refuses gross misses), both
 * axes share one scale (a square stays square), and every helper returns ""
 * or null rather than NaN for anything degenerate that slipped through.
 */

export type Window = { x0: number; x1: number; y0: number; y1: number };

const EPS = 1e-9;
const sub = (a: Pt, b: Pt): Pt => [a[0] - b[0], a[1] - b[1]];
const add = (a: Pt, b: Pt): Pt => [a[0] + b[0], a[1] + b[1]];
const mul = (a: Pt, k: number): Pt => [a[0] * k, a[1] * k];
const len = (a: Pt) => Math.hypot(a[0], a[1]);
const unit = (a: Pt): Pt | null => {
  const l = len(a);
  return l > EPS && Number.isFinite(l) ? [a[0] / l, a[1] / l] : null;
};
const fmt = (v: number) => (Math.round(v * 100) / 100).toString();
/** A point for an SVG path: two decimals, never NaN. */
export const pt = ([x, y]: Pt) => `${fmt(x)} ${fmt(y)}`;
const ok = (...ps: Pt[]) => ps.every(([x, y]) => Number.isFinite(x) && Number.isFinite(y));

export function lookup(fig: CleanPlane): Map<string, Pt> {
  return new Map(fig.points.map((p) => [p.name, p.at]));
}

/** A circle's radius: given, or the distance to its point. */
export function radiusOf(shape: CleanShape, points: Map<string, Pt>): number {
  if (shape.radius !== null) return shape.radius;
  const [c, p] = shape.of.map((n) => points.get(n));
  return c && p ? len(sub(p, c)) : 0;
}

/**
 * The minor arc from A to B around O (maths coordinates, y up): its radius |OA|,
 * the angle A sits at, and the signed turn (counter-clockwise positive, at most
 * a half turn). The y flip keeps the visual orientation, so a counter-clockwise
 * turn is SVG sweep-flag 0. Null when A or B sits on O, or A and B align with O
 * on the same side.
 */
export function minorArc(
  a: Pt,
  o: Pt,
  b: Pt,
): { r: number; from: number; delta: number; sweep: 0 | 1 } | null {
  const ua = sub(a, o);
  const ub = sub(b, o);
  const r = len(ua);
  if (!(r > EPS) || !(len(ub) > EPS)) return null;
  const cross = ua[0] * ub[1] - ua[1] * ub[0];
  const dot = ua[0] * ub[0] + ua[1] * ub[1];
  const delta = cross === 0 && dot < 0 ? Math.PI : Math.atan2(cross, dot);
  if (!Number.isFinite(delta) || Math.abs(delta) < EPS) return null;
  return { r, from: Math.atan2(ua[1], ua[0]), delta, sweep: delta > 0 ? 0 : 1 };
}

/** The arc's end: on its circle, in B's direction from O. */
function arcEnd(o: Pt, b: Pt, r: number): Pt | null {
  const u = unit(sub(b, o));
  return u ? add(o, mul(u, r)) : null;
}

/** What an arc covers: its two ends and the circle's cardinal points inside its sweep. */
export function arcPoints(a: Pt, o: Pt, b: Pt): Pt[] {
  const arc = minorArc(a, o, b);
  if (!arc) return [a, b];
  const end = arcEnd(o, b, arc.r);
  const out: Pt[] = end ? [a, end] : [a];
  const turn = 2 * Math.PI;
  for (let k = 0; k < 4; k += 1) {
    const theta = (k * Math.PI) / 2;
    const along =
      arc.delta > 0
        ? (((theta - arc.from) % turn) + turn) % turn
        : (((arc.from - theta) % turn) + turn) % turn;
    if (along < Math.abs(arc.delta))
      out.push(add(o, [arc.r * Math.cos(theta), arc.r * Math.sin(theta)]));
  }
  return out;
}

/** Everything the figure draws, in its units: points, circles, arcs. */
function content(fig: CleanPlane): Pt[] {
  const points = lookup(fig);
  const out: Pt[] = fig.points.map((p) => p.at);
  for (const s of fig.shapes) {
    const [p0, p1, p2] = s.of.map((n) => points.get(n));
    if (s.draw === "circle" && p0) {
      const r = radiusOf(s, points);
      if (r > 0) out.push([p0[0] - r, p0[1] - r], [p0[0] + r, p0[1] + r]);
    }
    if (s.draw === "arc" && p0 && p1 && p2) out.push(...arcPoints(p0, p1, p2));
  }
  return out.filter((p) => ok(p));
}

/**
 * The grid's step: 1 for the course's quadrillage (a span of 4 to 20 units),
 * otherwise a round step giving about ten lines.
 */
export function gridStep(w: number, h: number): number {
  const span = Math.max(w, h);
  if (span >= 4 && span <= 20) return 1;
  // A window too small (or too large) to count ticks in gets the unit step.
  if (!(span >= MIN_SPAN) || !Number.isFinite(span)) return 1;
  const t = niceTicks(0, span, 10).ticks;
  const [first, second] = t;
  return first !== undefined && second !== undefined ? Number((second - first).toPrecision(6)) : 1;
}

const snap = (v: number, step: number, up: boolean) =>
  Number(((up ? Math.ceil(v / step - EPS) : Math.floor(v / step + EPS)) * step).toPrecision(10));

/**
 * The window the figure is drawn in. Content is padded by a tenth of its larger
 * span, or by one unit when it sits at one place (within `MIN_SPAN`); a given
 * range is kept but grown to hold the content (and the origin with axes); a flat
 * or tall window is widened so nothing is squashed; with axes or a grid, the
 * edges snap outward to the grid.
 */
export function planeWindow(fig: CleanPlane): Window {
  const pts = content(fig);
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  if (fig.axes && pts.length) {
    xs.push(0);
    ys.push(0);
  }
  const has = xs.length > 0;
  const [cx0, cx1] = has ? [Math.min(...xs), Math.max(...xs)] : [-5, 5];
  const [cy0, cy1] = has ? [Math.min(...ys), Math.max(...ys)] : [-5, 5];
  const extent = Math.max(cx1 - cx0, cy1 - cy0);
  const pad = has ? (extent >= MIN_SPAN ? 0.1 * extent : 1) : 0;
  const axis = (given: Pt | null, lo: number, hi: number): Pt => {
    if (!given) return [lo - pad, hi + pad];
    let [a, b] = given;
    const slack = 0.02 * (b - a);
    if (has && lo < a) a = lo - slack;
    if (has && hi > b) b = hi + slack;
    if (fig.axes) [a, b] = [Math.min(a, 0), Math.max(b, 0)];
    return [a, b];
  };
  let [x0, x1] = axis(fig.xRange, cx0, cx1);
  let [y0, y1] = axis(fig.yRange, cy0, cy1);
  const w = x1 - x0;
  const h = y1 - y0;
  if (h < 0.25 * w) {
    const grow = (0.25 * w - h) / 2;
    [y0, y1] = [y0 - grow, y1 + grow];
  } else if (h > 1.5 * w) {
    const grow = (h / 1.5 - w) / 2;
    [x0, x1] = [x0 - grow, x1 + grow];
  }
  if (fig.axes || fig.grid) {
    const step = gridStep(x1 - x0, y1 - y0);
    [x0, x1, y0, y1] = [
      snap(x0, step, false),
      snap(x1, step, true),
      snap(y0, step, false),
      snap(y1, step, true),
    ];
  }
  return { x0, x1, y0, y1 };
}

export type Frame = {
  /** Pixels per unit, the same on both axes. */
  s: number;
  width: number;
  height: number;
  px: (p: Pt) => Pt;
};

/** Room kept around the window for labels, in px. */
export const FRAME_MARGIN = 20;

/** The window at the drawing's width: one scale for both axes, at most min(1,1·W, 400) px tall. */
export function fitWindow(win: Window, W: number): Frame {
  const M = FRAME_MARGIN;
  const w = win.x1 - win.x0 > 0 ? win.x1 - win.x0 : 1;
  const h = win.y1 - win.y0 > 0 ? win.y1 - win.y0 : 1;
  const width = Math.max(W, 2 * M + 1);
  const hMax = Math.min(1.1 * width, 400);
  // No floor: a window of a million units is a small scale, never a taller drawing.
  const fitted = Math.min((width - 2 * M) / w, (hMax - 2 * M) / h);
  const s = fitted > 0 && Number.isFinite(fitted) ? fitted : 1;
  const height = Math.min(Math.round(h * s + 2 * M), Math.round(hMax));
  const offX = (width - w * s) / 2;
  return {
    s,
    width,
    height,
    px: ([x, y]) => [offX + (x - win.x0) * s, M + (win.y1 - y) * s],
  };
}

/**
 * Numbers on an axis at every k-th grid line, with k the first of 1, 2, 5, 10…
 * that leaves at least `minPx` between two of them.
 */
export function labelStep(step: number, s: number, minPx: number): number {
  for (const k of [1, 2, 5, 10, 20, 50, 100]) if (k * step * s >= minPx) return k;
  return 100;
}

/** The multiples of `step` inside [lo, hi], rounded so no float noise reaches a label. */
export function multiples(lo: number, hi: number, step: number): number[] {
  if (!(step > 0) || !Number.isFinite(lo) || !Number.isFinite(hi)) return [];
  const out: number[] = [];
  const first = Math.ceil(lo / step - EPS);
  for (let k = first; k * step <= hi + step * EPS && out.length < 500; k += 1) {
    out.push(Number((k * step).toPrecision(10)));
  }
  return out;
}

/**
 * The visible part of the line through P and Q (t ∈ ℝ) or of the ray from P
 * through Q (t ≥ 0), cut to the window (Liang–Barsky); null when none of it is.
 */
export function clipToWindow(p: Pt, q: Pt, win: Window, ray: boolean): [Pt, Pt] | null {
  const [dx, dy] = sub(q, p);
  let t0 = ray ? 0 : -Infinity;
  let t1 = Infinity;
  const edges: [number, number][] = [
    [-dx, p[0] - win.x0],
    [dx, win.x1 - p[0]],
    [-dy, p[1] - win.y0],
    [dy, win.y1 - p[1]],
  ];
  for (const [d, room] of edges) {
    if (Math.abs(d) < 1e-12) {
      if (room < 0) return null;
      continue;
    }
    const t = room / d;
    if (d < 0) t0 = Math.max(t0, t);
    else t1 = Math.min(t1, t);
  }
  if (!Number.isFinite(t0) || !Number.isFinite(t1) || t0 >= t1) return null;
  return [add(p, mul([dx, dy], t0)), add(p, mul([dx, dy], t1))];
}

/** An SVG path for the minor arc A → B around O, drawn in px. */
export function arcPath(a: Pt, o: Pt, b: Pt, px: (p: Pt) => Pt, s: number): string {
  const arc = minorArc(a, o, b);
  const end = arc && arcEnd(o, b, arc.r);
  if (!arc || !end) return "";
  const r = arc.r * s;
  const [from, to] = [px(a), px(end)];
  if (!ok(from, to) || !Number.isFinite(r)) return "";
  return `M ${pt(from)} A ${fmt(r)} ${fmt(r)} 0 0 ${arc.sweep} ${pt(to)}`;
}

/** A whole circle as two arcs, so it can trace like any other path. */
export function circlePath(c: Pt, r: number): string {
  if (!ok(c) || !(r > 0) || !Number.isFinite(r)) return "";
  const [x, y] = c;
  return `M ${pt([x - r, y])} A ${fmt(r)} ${fmt(r)} 0 1 0 ${pt([x + r, y])} A ${fmt(r)} ${fmt(r)} 0 1 0 ${pt([x - r, y])}`;
}

/**
 * The mark of the angle ABC at B, in px (y down). With a codage (marks ≥ 1),
 * that many arcs 4 px apart; without, a filled sector and no arc at all, so an
 * unmarked angle never reads as coded. Always the angle's own (minor) opening.
 */
export function angleMark(
  a: Pt,
  b: Pt,
  c: Pt,
  marks: number,
): { sector: string; arcs: string[]; r0: number; bisector: Pt } | null {
  const ua = sub(a, b);
  const uc = sub(c, b);
  const u = unit(ua);
  const v = unit(uc);
  if (!u || !v || !ok(b)) return null;
  const cross = u[0] * v[1] - u[1] * v[0];
  const dot = u[0] * v[0] + u[1] * v[1];
  if (Math.abs(cross) < EPS && dot > 0) return null;
  const r0 = Math.min(16, 0.45 * Math.min(len(ua), len(uc)));
  // y down: a positive cross turns clockwise on screen, which is sweep-flag 1.
  const sweep = cross > 0 ? 1 : 0;
  const bisector = unit(add(u, v)) ?? [-u[1], u[0]];
  const at = (r: number, w: Pt) => pt(add(b, mul(w, r)));
  if (marks <= 0) {
    const sector = `M ${pt(b)} L ${at(r0, u)} A ${fmt(r0)} ${fmt(r0)} 0 0 ${sweep} ${at(r0, v)} Z`;
    return { sector, arcs: [], r0, bisector };
  }
  const arcs = Array.from({ length: Math.min(3, marks) }, (_, k) => {
    const r = r0 + 4 * k;
    return `M ${at(r, u)} A ${fmt(r)} ${fmt(r)} 0 0 ${sweep} ${at(r, v)}`;
  });
  return { sector: "", arcs, r0: r0 + 4 * (arcs.length - 1), bisector };
}

/** The square corner of a right angle ABC at B, in px. */
export function rightAngleMark(
  a: Pt,
  b: Pt,
  c: Pt,
): { path: string; bisector: Pt; size: number } | null {
  const ua = sub(a, b);
  const uc = sub(c, b);
  const u = unit(ua);
  const v = unit(uc);
  if (!u || !v || !ok(b)) return null;
  const side = Math.min(9, 0.4 * Math.min(len(ua), len(uc)));
  const p = add(b, mul(u, side));
  const q = add(p, mul(v, side));
  const r = add(b, mul(v, side));
  return { path: `M ${pt(p)} L ${pt(q)} L ${pt(r)}`, bisector: unit(add(u, v)) ?? u, size: side };
}

/** Ticks of a segment's codage: `marks` short strokes across its middle, 3,5 px apart. */
export function segmentTicks(p: Pt, q: Pt, marks: number): string {
  const u = unit(sub(q, p));
  if (!u || marks <= 0 || !ok(p, q)) return "";
  const n: Pt = [-u[1], u[0]];
  const mid = mul(add(p, q), 0.5);
  const count = Math.min(3, marks);
  return Array.from({ length: count }, (_, k) => {
    const c = add(mid, mul(u, (k - (count - 1) / 2) * 3.5));
    return `M ${pt(add(c, mul(n, 4)))} L ${pt(add(c, mul(n, -4)))}`;
  }).join(" ");
}

/** A vector: its shaft, stopping short of the tip, and a filled 9 × 7 px head. */
export function vectorPaths(p: Pt, q: Pt): { shaft: string; head: string } | null {
  const u = unit(sub(q, p));
  if (!u || !ok(p, q)) return null;
  const n: Pt = [-u[1], u[0]];
  const length = len(sub(q, p));
  const base = add(q, mul(u, -Math.min(9, length)));
  const shaftEnd = add(q, mul(u, -Math.min(8, length)));
  return {
    shaft: `M ${pt(p)} L ${pt(shaftEnd)}`,
    head: `M ${pt(q)} L ${pt(add(base, mul(n, 3.5)))} L ${pt(add(base, mul(n, -3.5)))} Z`,
  };
}

/**
 * Where a point's label goes, in screen space (y down), normalised: away from
 * the shapes that meet at the point; along a straight line through it, to one
 * side of that line (away from the figure's centre, else up, else right); for a
 * lone point, away from the centre; else up and to the right.
 */
export function labelDirection(p: Pt, neighbours: Pt[], centroid: Pt): Pt {
  const fallback: Pt = [Math.SQRT1_2, -Math.SQRT1_2];
  if (!ok(p)) return fallback;
  const dirs = neighbours
    .filter((n) => ok(n))
    .map((n) => sub(n, p))
    .filter((d) => len(d) >= 1e-6)
    .map((d) => mul(d, 1 / len(d)));
  const away = unit(sub(p, centroid));
  const first = dirs[0];
  if (first) {
    const v = mul(
      dirs.reduce<Pt>((sum, d) => add(sum, d), [0, 0]),
      -1,
    );
    if (len(v) >= 0.1) return unit(v) ?? fallback;
    const perp: Pt = [-first[1], first[0]];
    const side = ok(centroid) ? sub(p, centroid)[0] * perp[0] + sub(p, centroid)[1] * perp[1] : 0;
    if (Math.abs(side) > 1e-6) return side > 0 ? perp : mul(perp, -1);
    if (Math.abs(perp[1]) > 1e-6) return perp[1] < 0 ? perp : mul(perp, -1);
    return perp[0] > 0 ? perp : mul(perp, -1);
  }
  return away ?? fallback;
}

/** Each point's neighbours: the points it is joined to by the figure's shapes. */
export function neighbourMap(fig: CleanPlane): Map<string, string[]> {
  const out = new Map<string, string[]>(fig.points.map((p) => [p.name, []]));
  const link = (a: string | undefined, b: string | undefined) => {
    if (a === undefined || b === undefined || a === b) return;
    out.get(a)?.push(b);
    out.get(b)?.push(a);
  };
  for (const s of fig.shapes) {
    const [a, b, c] = s.of;
    switch (s.draw) {
      case "polygon":
        s.of.forEach((n, i) => link(n, s.of[(i + 1) % s.of.length]));
        break;
      case "arc":
        link(a, b);
        link(c, b);
        link(a, c);
        break;
      case "angle":
      case "right_angle":
        link(a, b);
        link(c, b);
        break;
      default:
        link(a, b);
    }
  }
  return out;
}

/** Points at the very same place, as one mark labelled « A = A' ». */
export function groupPoints(points: CleanPoint[], span: number): { names: string[]; at: Pt }[] {
  const tolerance = 1e-9 * (span > 0 ? span : 1);
  const groups: { names: string[]; at: Pt }[] = [];
  for (const p of points) {
    const same = groups.find((g) => len(sub(g.at, p.at)) <= tolerance);
    if (same) same.names.push(p.name);
    else groups.push({ names: [p.name], at: p.at });
  }
  return groups;
}

/** A point's name as TeX: A_12 is A_{12}; primes stay primes. */
export function nameTex(name: string): string {
  return name.replace(/_([0-9]+)$/, "_{$1}");
}

const SUBSCRIPTS = "₀₁₂₃₄₅₆₇₈₉";
/** A point's name as plain text for a screen reader: A_1 is A₁. */
export function nameText(name: string): string {
  return name.replace(/_([0-9]+)$/, (_, digits: string) =>
    [...digits].map((d) => SUBSCRIPTS[Number(d)] ?? d).join(""),
  );
}

/** The larger extent of the figure's points. */
export function spanOf(points: CleanPoint[]): number {
  if (points.length === 0) return 1;
  const xs = points.map((p) => p.at[0]);
  const ys = points.map((p) => p.at[1]);
  return Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) || 1;
}

/** A polygon's area centroid in px, or the mean of its vertices when it is flat. */
export function polygonCentroid(ps: Pt[]): Pt {
  let area = 0;
  let cx = 0;
  let cy = 0;
  ps.forEach((p, i) => {
    const q = ps[(i + 1) % ps.length] ?? p;
    const f = p[0] * q[1] - q[0] * p[1];
    area += f;
    cx += (p[0] + q[0]) * f;
    cy += (p[1] + q[1]) * f;
  });
  if (Math.abs(area) < 1e-9) {
    const n = Math.max(1, ps.length);
    return [ps.reduce((s, p) => s + p[0], 0) / n, ps.reduce((s, p) => s + p[1], 0) / n];
  }
  return [cx / (3 * area), cy / (3 * area)];
}

/** The unit normal of PQ on the side away from `centroid` (else up, else right). */
export function outwardNormal(p: Pt, q: Pt, centroid: Pt): Pt {
  const u = unit(sub(q, p));
  if (!u) return [0, -1];
  const n: Pt = [-u[1], u[0]];
  const mid = mul(add(p, q), 0.5);
  const side = (mid[0] - centroid[0]) * n[0] + (mid[1] - centroid[1]) * n[1];
  if (Number.isFinite(side) && Math.abs(side) > 1e-6) return side > 0 ? n : mul(n, -1);
  if (Math.abs(n[1]) > 1e-6) return n[1] < 0 ? n : mul(n, -1);
  return n[0] > 0 ? n : mul(n, -1);
}

export const vec = { sub, add, mul, len, unit };
