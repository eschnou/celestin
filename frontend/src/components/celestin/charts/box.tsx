import type { BoxPlot } from "@/lib/tutor/types";
import { BaseAxis, FONT, fitLabel, frame, LANE_HEIGHT, LANES, lanes, textWidth } from "./axes";
import { useNotation } from "./format";
import { linear, niceTicks } from "./scale";
import type { BoxNumbers } from "./series";

/** Half the box's height. */
const HALF = 12;
/** Room for the value lane above a box. */
const ABOVE = 18;
const ROW = 56;
/** One lane above the box, the others under it, and a gap to the next row. */
const ROW_WITH_VALUES = ABOVE + 2 * HALF + LANE_HEIGHT * (LANES - 1) + 2 + 12;

/** « Boîte à moustaches », horizontal, one row per series, on a shared axis. */
export function Box({ chart, width }: { chart: BoxPlot; width: number }) {
  const notation = useNotation();
  const { boxes } = chart;
  const numbers = boxes.flatMap((b) => [b.minimum, b.maximum]);
  const ticks = niceTicks(Math.min(...numbers), Math.max(...numbers));
  // Labels take at most 30 % of the width, so a long series name cannot eat the plot
  // on a phone; the screen-reader table keeps it whole.
  const labelRoom = boxes.some((b) => b.label)
    ? Math.min(
        Math.ceil(Math.max(...boxes.map((b) => textWidth(b.label ?? "")))),
        Math.round(width * 0.3),
      )
    : 0;
  const left = labelRoom ? labelRoom + 16 : 12;
  const row = chart.show_values ? ROW_WITH_VALUES : ROW;
  const f = frame(width, left, 12 + boxes.length * row + 28);
  const x = linear([ticks.lo, ticks.hi], [f.left, f.right]);
  // The box's middle in its row: under the value lane when values are shown.
  const middle = (i: number) => f.top + row * i + (chart.show_values ? ABOVE + HALF : row / 2 + 6);

  return (
    <svg width={width} height={f.height} aria-hidden="true" className="overflow-visible">
      {ticks.ticks.map((t) => (
        <line key={t} x1={x(t)} x2={x(t)} y1={f.top} y2={f.bottom} className="stroke-border" />
      ))}
      {boxes.map((b, i) => {
        const mid = middle(i);
        return (
          <g key={i} strokeWidth={1.5} className="stroke-chart-1">
            {b.label && (
              <text
                x={f.left - 10}
                y={mid}
                dy="0.32em"
                textAnchor="end"
                fontSize={FONT}
                stroke="none"
                className="fill-foreground"
              >
                {fitLabel(b.label, labelRoom)}
              </text>
            )}
            <line x1={x(b.minimum)} x2={x(b.q1)} y1={mid} y2={mid} />
            <line x1={x(b.q3)} x2={x(b.maximum)} y1={mid} y2={mid} />
            <line x1={x(b.minimum)} x2={x(b.minimum)} y1={mid - HALF / 2} y2={mid + HALF / 2} />
            <line x1={x(b.maximum)} x2={x(b.maximum)} y1={mid - HALF / 2} y2={mid + HALF / 2} />
            <rect
              x={x(b.q1)}
              y={mid - HALF}
              width={x(b.q3) - x(b.q1)}
              height={HALF * 2}
              className="fill-chart-1/15"
            />
            <line
              x1={x(b.median)}
              x2={x(b.median)}
              y1={mid - HALF}
              y2={mid + HALF}
              strokeWidth={3}
            />
            {chart.show_values && <BoxValues b={b} x={x} mid={mid} />}
          </g>
        );
      })}
      <BaseAxis f={f} labels={ticks.ticks.map((t) => ({ at: x(t), text: notation.number(t) }))} />
    </svg>
  );
}

/** The five numbers: above the box, those that would collide moved to a lane below it. */
function BoxValues({ b, x, mid }: { b: BoxNumbers; x: (v: number) => number; mid: number }) {
  const notation = useNotation();
  const labels = [b.minimum, b.q1, b.median, b.q3, b.maximum].map((v) => ({
    at: x(v),
    text: notation.number(v),
  }));
  const lane = lanes(labels);
  return labels.map((l, k) => {
    const n = lane[k] as number;
    return (
      <text
        key={k}
        x={l.at}
        y={n === 0 ? mid - HALF - 6 : mid + HALF + 2 + LANE_HEIGHT * n}
        textAnchor="middle"
        fontSize={11}
        stroke="none"
        className="fill-foreground tabular-nums"
      >
        {l.text}
      </text>
    );
  });
}
