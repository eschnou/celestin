import type { Box, Chart } from "@/lib/tutor/types";
import { FRENCH, type Notation } from "./format";

/**
 * Geometry from statistics, in data units. The board computes only what has one
 * definition (cumulative sums, a sector's angle, a histogram's area rule); what a
 * course defines its own way (quartiles, grouped medians) comes from Célestin.
 *
 * The tool has validated the data, but a stored conversation is replayed as it
 * was written (008 design §5), so `sanitise` cleans a chart once, at the edge,
 * and everything after it assumes clean data.
 */

const count = (v: number) => (Number.isFinite(v) && v > 0 ? v : 0);

/**
 * The chart with lists cut to matching lengths, every count a finite
 * non-negative number, sticks on finite values, classes stopping at the first
 * bound that is not finite or not increasing, and each box's numbers in order.
 */
export function sanitise(chart: Chart): Chart {
  switch (chart.kind) {
    case "bars":
    case "pie": {
      const n = Math.min(chart.categories.length, chart.values.length);
      return {
        ...chart,
        categories: chart.categories.slice(0, n),
        values: chart.values.slice(0, n).map(count),
      };
    }
    case "sticks": {
      const kept = chart.x
        .slice(0, chart.values.length)
        .map((x, i) => [x, count(chart.values[i] as number)] as const)
        .filter(([x]) => Number.isFinite(x));
      return { ...chart, x: kept.map(([x]) => x), values: kept.map(([, v]) => v) };
    }
    case "histogram":
    case "cumulative": {
      let n = 0;
      while (n < chart.values.length && n + 1 < chart.bounds.length) {
        const [a, b] = [chart.bounds[n] as number, chart.bounds[n + 1] as number];
        if (!Number.isFinite(a) || !Number.isFinite(b) || b <= a) break;
        n += 1;
      }
      return {
        ...chart,
        bounds: chart.bounds.slice(0, n + 1),
        values: chart.values.slice(0, n).map(count),
      };
    }
    case "box":
      return {
        ...chart,
        boxes: chart.boxes.map((b) => ({ label: b.label ?? null, ...boxGeometry(b) })),
      };
  }
}

export type Entry = { label: string; value: number };

/** One entry per category, value or class, labelled as the course writes it. */
export function entries(
  chart: Exclude<Chart, { kind: "box" }>,
  notation: Notation = FRENCH,
): Entry[] {
  switch (chart.kind) {
    case "bars":
    case "pie":
      return chart.categories.map((label, i) => ({ label, value: chart.values[i] as number }));
    case "sticks":
      return chart.x.map((x, i) => ({
        label: notation.number(x),
        value: chart.values[i] as number,
      }));
    case "histogram":
    case "cumulative":
      return chart.values.map((value, i) => ({
        label: notation.classLabel(
          chart.bounds[i] as number,
          chart.bounds[i + 1] as number,
          chart.closed,
        ),
        value,
      }));
  }
}

/** Whether a sanitised chart has anything to draw; if not, the board says so. */
export function drawable(chart: Chart): boolean {
  return chart.kind === "box" ? chart.boxes.length > 0 : entries(chart).some((e) => e.value > 0);
}

export type Rect = { x0: number; x1: number; value: number; height: number };

/**
 * A histogram's rectangles. The area is proportional to the value: height =
 * value × reference / amplitude, the reference defaulting to the smallest
 * amplitude, so equal amplitudes give heights equal to the values.
 */
export function histogramRects(
  bounds: number[],
  values: number[],
  reference?: number | null,
): Rect[] {
  const classes = values.map((value, i) => ({
    x0: bounds[i] as number,
    x1: bounds[i + 1] as number,
    value,
  }));
  const smallest = Math.min(...classes.map((c) => c.x1 - c.x0));
  const ref = reference && reference > 0 ? reference : smallest;
  return classes.map((c) => ({ ...c, height: (c.value * ref) / (c.x1 - c.x0) }));
}

export type Point = [number, number];

/**
 * The frequency polygon over a histogram: the middle of each rectangle's top.
 * Closed, it comes down to the axis at the middle of an empty class of the same
 * amplitude on each side.
 */
export function polygonPoints(rects: Rect[], mode: "open" | "closed"): Point[] {
  const tops = rects.map((r): Point => [(r.x0 + r.x1) / 2, r.height]);
  const first = rects[0];
  const last = rects.at(-1);
  if (mode === "open" || !first || !last) return tops;
  return [
    [first.x0 - (first.x1 - first.x0) / 2, 0],
    ...tops,
    [last.x1 + (last.x1 - last.x0) / 2, 0],
  ];
}

/**
 * The cumulative polygon, with one point per bound. Increasing, it starts at 0 on
 * the first bound and reaches the total on the last; decreasing, the reverse.
 */
export function cumulativePoints(
  bounds: number[],
  values: number[],
  direction: "increasing" | "decreasing",
): Point[] {
  const total = values.reduce((a, b) => a + b, 0);
  let running = 0;
  return bounds.map((b, i): Point => {
    if (i > 0) running += values[i - 1] as number;
    return [b, direction === "increasing" ? running : total - running];
  });
}

export type Arc = { start: number; end: number; value: number };

/** Sector angles in radians, clockwise from 12 o'clock, summing to 2π. */
export function pieArcs(values: number[]): Arc[] {
  const total = values.reduce((a, b) => a + b, 0);
  if (total === 0) return [];
  let angle = 0;
  return values.map((value) => {
    const start = angle;
    angle += (value / total) * 2 * Math.PI;
    return { start, end: angle, value };
  });
}

/** The SVG path of a sector; a sector of the whole turn is two half arcs. */
export function arcPath(cx: number, cy: number, r: number, start: number, end: number): string {
  const at = (a: number) => `${cx + r * Math.sin(a)} ${cy - r * Math.cos(a)}`;
  if (end - start >= 2 * Math.PI - 1e-9) {
    return `M ${at(0)} A ${r} ${r} 0 1 1 ${at(Math.PI)} A ${r} ${r} 0 1 1 ${at(0)} Z`;
  }
  const large = end - start > Math.PI ? 1 : 0;
  return `M ${cx} ${cy} L ${at(start)} A ${r} ${r} 0 ${large} 1 ${at(end)} Z`;
}

export type BoxNumbers = {
  minimum: number;
  q1: number;
  median: number;
  q3: number;
  maximum: number;
};

/** The five numbers in order; a box stored out of order is sorted, not dropped. */
export function boxGeometry(box: Box): BoxNumbers {
  const [minimum, q1, median, q3, maximum] = [box.minimum, box.q1, box.median, box.q3, box.maximum]
    .map((v) => (Number.isFinite(v) ? v : 0))
    .sort((a, b) => a - b) as [number, number, number, number, number];
  return { minimum, q1, median, q3, maximum };
}
