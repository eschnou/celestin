import type { ReactNode } from "react";
import type { Measure } from "@/lib/tutor/types";
import { FRENCH, type Notation } from "./format";
import { linear, niceTicks } from "./scale";

/**
 * What every chart shares: its frame, its value axis with gridlines (a reading
 * exercise is done on them), and a category or number axis whose labels thin out
 * rather than overlap. `CartesianSvg` puts the four counting charts together, so
 * each of them only has its horizontal scale and its marks to draw.
 */

export const FONT = 12;
/** Below this spacing, every second axis label is dropped. */
const MIN_LABEL_SPACING = 28;
const MARGIN = { top: 12, right: 16, bottom: 28 };

/** Rough width of a label in 12 px Lato, enough to size margins. */
export function textWidth(text: string): number {
  return text.length * FONT * 0.56;
}

/** The label, shortened with « … » if it would be wider than `px`. */
export function fitLabel(text: string, px: number): string {
  if (textWidth(text) <= px) return text;
  const chars = Math.max(1, Math.floor(px / (FONT * 0.56)) - 1);
  return `${text.slice(0, chars).trimEnd()}…`;
}

export type Frame = { height: number; left: number; right: number; top: number; bottom: number };

export function frame(width: number, left: number, height: number, bottom = MARGIN.bottom): Frame {
  return { height, left, right: width - MARGIN.right, top: MARGIN.top, bottom: height - bottom };
}

/**
 * A chart with a value axis from 0: its frame, ticks, vertical scale, and the
 * way a tick is written (`20 %` on a percentage axis).
 */
export function valueFrame(
  width: number,
  max: number,
  measure: Measure,
  bottom?: number,
  notation: Notation = FRENCH,
) {
  const ticks = niceTicks(0, max);
  const tick = (t: number) => notation.value(t, measure);
  const left = Math.ceil(Math.max(...ticks.ticks.map((t) => textWidth(tick(t))))) + 14;
  const height = Math.round(Math.min(340, Math.max(220, width * 0.55)));
  const f = frame(width, left, height, bottom);
  return { f, ticks, tick, y: linear([ticks.lo, ticks.hi], [f.bottom, f.top]) };
}

export type ValueFrame = ReturnType<typeof valueFrame>;

/** Horizontal gridlines and their labels, the axis itself drawn darker. */
function ValueAxis({ f, ticks, tick, y }: ValueFrame) {
  return (
    <g>
      {ticks.ticks.map((t) => (
        <g key={t}>
          <line
            x1={f.left}
            x2={f.right}
            y1={y(t)}
            y2={y(t)}
            className={t === ticks.lo ? "stroke-muted-foreground" : "stroke-border"}
            strokeWidth={1}
          />
          <text
            x={f.left - 8}
            y={y(t)}
            dy="0.32em"
            textAnchor="end"
            fontSize={FONT}
            className="fill-muted-foreground tabular-nums"
          >
            {tick(t)}
          </text>
        </g>
      ))}
      <line x1={f.left} x2={f.left} y1={f.top} y2={f.bottom} className="stroke-muted-foreground" />
    </g>
  );
}

export type AxisLabel = { at: number; text: string };

/** Keeps every label when they fit, otherwise every second one (ends included). */
export function thinned(labels: AxisLabel[]): AxisLabel[] {
  if (labels.length < 3) return labels;
  const spacing = Math.min(...labels.slice(1).map((l, i) => l.at - (labels[i] as AxisLabel).at));
  const widest = Math.max(...labels.map((l) => textWidth(l.text)));
  if (spacing >= Math.max(MIN_LABEL_SPACING, widest + 6)) return labels;
  return labels.filter((_, i) => i % 2 === 0 || i === labels.length - 1);
}

/** The horizontal axis: a line, tick marks and labels under them. */
export function BaseAxis({
  f,
  labels,
  ticks = true,
  rotate = false,
}: {
  f: Frame;
  labels: AxisLabel[];
  ticks?: boolean;
  rotate?: boolean;
}) {
  const shown = rotate ? labels : thinned(labels);
  return (
    <g>
      <line
        x1={f.left}
        x2={f.right}
        y1={f.bottom}
        y2={f.bottom}
        className="stroke-muted-foreground"
      />
      {shown.map((l) => (
        <g key={`${l.at}-${l.text}`}>
          {ticks && (
            <line
              x1={l.at}
              x2={l.at}
              y1={f.bottom}
              y2={f.bottom + 4}
              className="stroke-muted-foreground"
            />
          )}
          <text
            x={l.at}
            y={f.bottom + 8}
            dy="0.71em"
            fontSize={FONT}
            textAnchor={rotate ? "end" : "middle"}
            transform={rotate ? `rotate(-35 ${l.at} ${f.bottom + 8})` : undefined}
            className="fill-muted-foreground tabular-nums"
          >
            {l.text}
          </text>
        </g>
      ))}
    </g>
  );
}

/** The shell of a counting chart: value axis behind the marks, base axis in front. */
export function CartesianSvg({
  width,
  axis,
  labels,
  baseTicks = true,
  rotate = false,
  children,
}: {
  width: number;
  axis: ValueFrame;
  labels: AxisLabel[];
  baseTicks?: boolean;
  rotate?: boolean;
  children: ReactNode;
}) {
  return (
    <svg width={width} height={axis.f.height} aria-hidden="true" className="overflow-visible">
      <ValueAxis {...axis} />
      {children}
      <BaseAxis f={axis.f} labels={labels} ticks={baseTicks} rotate={rotate} />
    </svg>
  );
}

/** Lanes for labels along one line: one above it, the rest below. */
export const LANES = 3;
export const LANE_HEIGHT = 12;

/**
 * For labels along one line (a box plot's five numbers), the lane each goes in so
 * that none overlaps its neighbour: 0 above the line, then 1 and 2 below it.
 * Greedy, left to right; a label that fits no lane takes the last one.
 */
export function lanes(labels: AxisLabel[]): number[] {
  const ends = Array.from({ length: LANES }, () => -Infinity);
  return labels.map((l) => {
    const half = textWidth(l.text) / 2;
    const lane = ends.findIndex((end) => l.at - half >= end + 4);
    const chosen = lane === -1 ? LANES - 1 : lane;
    ends[chosen] = l.at + half;
    return chosen;
  });
}

/** A value written on a mark, only when Célestin asked for values (R5.1). */
export function MarkValue({ x, y, text }: { x: number; y: number; text: string }) {
  return (
    <text
      x={x}
      y={y - 6}
      textAnchor="middle"
      fontSize={FONT}
      className="fill-foreground font-semibold tabular-nums"
    >
      {text}
    </text>
  );
}
