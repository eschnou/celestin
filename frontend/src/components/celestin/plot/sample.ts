import type { PlotDot, PlotPair } from "@/lib/tutor/types";
import type { Fn } from "./sanitise";

/**
 * Curves, sequences and broken lines, in data units, cut to the window. Pure:
 * the layout turns the result into pixels.
 *
 * A curve is sampled about every 2 px across its visible domain, then each gap
 * is halved until it moves less than 3 px on screen. A gap that never settles,
 * and whose midpoint does not split its rise, is a pole or a jump and breaks the
 * curve there; so does a value that is not a finite number (1/0, sqrt(−1), ln 0:
 * `evaluate` returns NaN for them).
 */

export type Win = { x0: number; x1: number; y0: number; y1: number };
export type Run = PlotPair[];

const TOLERANCE_PX = 3;
const MAX_DEPTH = 12;
const MIN_SAMPLES = 8;
const MAX_SAMPLES = 800;
/** Where a hollow dot finds its value when the bound is excluded, as the tool does. */
export const INSIDE = 1e-9;

export function sampleCurve(
  f: Fn,
  from: number,
  to: number,
  win: Win,
  plotW: number,
  plotH: number,
  budget = 20_000,
): { runs: Run[]; calls: number } {
  const a = Math.max(from, win.x0);
  const b = Math.min(to, win.x1);
  if (!(b > a) || !(plotW > 0) || !(plotH > 0)) return { runs: [], calls: 0 };
  let calls = 0;
  const F = (x: number) => {
    calls += 1;
    return f(x);
  };
  const pyScale = plotH / (win.y1 - win.y0);
  const n = Math.min(
    MAX_SAMPLES,
    Math.max(MIN_SAMPLES, Math.ceil((((b - a) / (win.x1 - win.x0)) * plotW) / 2)),
  );
  const pieces: Run[] = [];
  let current: Run = [];
  const breakPiece = () => {
    if (current.length > 1) pieces.push(current);
    current = [];
  };
  const segment = (xa: number, ya: number, xb: number, yb: number) => {
    if (current.length === 0) current.push([xa, ya]);
    current.push([xb, yb]);
  };
  const side = (y: number) => (y < win.y0 ? -1 : y > win.y1 ? 1 : 0);

  const refine = (xa: number, ya: number, xb: number, yb: number, depth: number): void => {
    const fa = !Number.isNaN(ya);
    const fb = !Number.isNaN(yb);
    if (!fa && !fb) return breakPiece();
    const spent = calls >= budget;
    if (fa && fb) {
      const sa = side(ya);
      const sb = side(yb);
      if (sa !== 0 && sa === sb) return breakPiece();
      const dp = Math.abs(yb - ya) * pyScale;
      // A gap across the window's edge keeps halving, so the curve ends on the edge.
      if (spent || (dp <= TOLERANCE_PX && sa === sb)) return segment(xa, ya, xb, yb);
      if (depth >= MAX_DEPTH) {
        // Still steep over a few millionths of the window: continuous if the midpoint
        // splits the rise, as a steep line's does. A jump's midpoint lands on one
        // side (both halves' shares near 0 and 1), a pole's beyond both ends.
        const ym = F((xa + xb) / 2);
        const rise = Math.abs(yb - ya);
        const split =
          Math.min(ya, yb) <= ym &&
          ym <= Math.max(ya, yb) &&
          Math.min(Math.abs(ym - ya), Math.abs(yb - ym)) > 0.25 * rise;
        return split ? segment(xa, ya, xb, yb) : breakPiece();
      }
    } else if (spent || depth >= MAX_DEPTH) return breakPiece();
    const xm = (xa + xb) / 2;
    const ym = F(xm);
    refine(xa, ya, xm, ym, depth + 1);
    refine(xm, ym, xb, yb, depth + 1);
  };

  const xs = Array.from({ length: n + 1 }, (_, i) => (i === n ? b : a + ((b - a) * i) / n));
  const ys = xs.map(F);
  for (let i = 0; i < n; i += 1) {
    refine(xs[i] as number, ys[i] as number, xs[i + 1] as number, ys[i + 1] as number, 0);
  }
  breakPiece();
  return { runs: pieces.flatMap((p) => clipBand(p, win.y0, win.y1)), calls };
}

/** A polyline cut to y0 ≤ y ≤ y1 (x is already inside): one run per stretch inside. */
export function clipBand(piece: Run, y0: number, y1: number): Run[] {
  const out: Run[] = [];
  let run: Run = [];
  let open = false; // the run ends where the last segment ended, unclipped
  const close = () => {
    if (run.length > 1) out.push(run);
    run = [];
    open = false;
  };
  for (let i = 0; i + 1 < piece.length; i += 1) {
    const [xa, ya] = piece[i] as PlotPair;
    const [xb, yb] = piece[i + 1] as PlotPair;
    const dy = yb - ya;
    let t0 = 0;
    let t1 = 1;
    if (dy === 0) {
      if (ya < y0 || ya > y1) {
        close();
        continue;
      }
    } else {
      const ta = (y0 - ya) / dy;
      const tb = (y1 - ya) / dy;
      t0 = Math.max(0, Math.min(ta, tb));
      t1 = Math.min(1, Math.max(ta, tb));
      if (t0 > t1) {
        close();
        continue;
      }
    }
    if (!(open && t0 === 0)) {
      close();
      run.push([xa + t0 * (xb - xa), ya + t0 * dy]);
    }
    run.push([xa + t1 * (xb - xa), ya + t1 * dy]);
    open = t1 === 1;
    if (!open) close();
  }
  close();
  return out;
}

/** One segment cut to the window (Liang–Barsky), as parameters along it, or null. */
function clipSegment([ax, ay]: PlotPair, [bx, by]: PlotPair, win: Win): [number, number] | null {
  let t0 = 0;
  let t1 = 1;
  const edges: [number, number][] = [
    [ax - bx, ax - win.x0],
    [bx - ax, win.x1 - ax],
    [ay - by, ay - win.y0],
    [by - ay, win.y1 - ay],
  ];
  for (const [p, q] of edges) {
    if (p === 0) {
      if (q < 0) return null;
      continue;
    }
    const r = q / p;
    if (p < 0) t0 = Math.max(t0, r);
    else t1 = Math.min(t1, r);
  }
  return t0 <= t1 ? [t0, t1] : null;
}

/** A broken line cut to the window; consecutive visible segments stay one run. */
export function clipLine(vertices: readonly PlotPair[], win: Win): Run[] {
  const out: Run[] = [];
  let run: Run = [];
  let open = false;
  const close = () => {
    if (run.length > 1) out.push(run);
    run = [];
    open = false;
  };
  for (let i = 0; i + 1 < vertices.length; i += 1) {
    const a = vertices[i] as PlotPair;
    const b = vertices[i + 1] as PlotPair;
    const clipped = clipSegment(a, b, win);
    if (clipped === null) {
      close();
      continue;
    }
    const [t0, t1] = clipped;
    const at = (t: number): PlotPair => [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])];
    if (!(open && t0 === 0)) {
      close();
      run.push(at(t0));
    }
    run.push(at(t1));
    open = t1 === 1;
    if (!open) close();
  }
  close();
  return out;
}

// A stored sequence has at most 60 terms (sanitise); the loop never runs longer.
const MAX_DOTS = 60;

/** A sequence's terms as isolated points (n ; uₙ), those defined and inside the window. */
export function sequenceDots(f: Fn, first: number, last: number, win: Win): PlotPair[] {
  const out: PlotPair[] = [];
  for (let k = 0; k < MAX_DOTS && first + k <= last; k += 1) {
    const n = first + k;
    const u = f(n);
    if (Number.isFinite(u) && n >= win.x0 && n <= win.x1 && u >= win.y0 && u <= win.y1) {
      out.push([n, u]);
    }
  }
  return out;
}

/**
 * Where an endpoint dot sits: on f(bound) when filled; when hollow, on f(bound)
 * or, where the bound is excluded because f is undefined there, on the value the
 * curve arrives at just inside it. Null: no dot.
 */
export function endpointValue(
  f: Fn,
  bound: number,
  inward: number,
  span: number,
  dot: PlotDot,
): number | null {
  if (dot === "none") return null;
  const at = f(bound);
  if (Number.isFinite(at)) return at;
  if (dot === "filled") return null;
  const near = f(bound + inward * INSIDE * span);
  return Number.isFinite(near) ? near : null;
}
