import type { StickChart } from "@/lib/tutor/types";
import { CartesianSvg, MarkValue, valueFrame } from "./axes";
import { useNotation } from "./format";
import { linear } from "./scale";

/** « Diagramme en bâtons »: a thin stick at each value of a discrete variable. */
export function Sticks({ chart, width }: { chart: StickChart; width: number }) {
  const notation = useNotation();
  const { x: xs, values } = chart;
  // Half the smallest gap on each side, so the end sticks do not sit on the frame.
  const gap = Math.min(...xs.slice(1).map((v, i) => v - (xs[i] as number)));
  const pad = gap > 0 && Number.isFinite(gap) ? gap / 2 : 1;
  const axis = valueFrame(width, Math.max(...values), chart.measure, undefined, notation);
  const { f, y } = axis;
  const x = linear([Math.min(...xs) - pad, Math.max(...xs) + pad], [f.left, f.right]);
  const tops = xs.map((v, i) => `${x(v)},${y(values[i] as number)}`).join(" ");

  return (
    <CartesianSvg
      width={width}
      axis={axis}
      labels={xs.map((v) => ({ at: x(v), text: notation.number(v) }))}
    >
      {xs.map((v, i) => {
        const n = values[i] as number;
        return (
          <g key={v}>
            <rect
              x={x(v) - 2}
              y={y(n)}
              width={4}
              height={f.bottom - y(n)}
              className="chart-grow fill-chart-1"
            />
            {chart.show_values && (
              <MarkValue x={x(v)} y={y(n)} text={notation.value(n, chart.measure)} />
            )}
          </g>
        );
      })}
      {chart.polygon && (
        <polyline
          points={tops}
          pathLength={1}
          fill="none"
          strokeWidth={2}
          className="chart-trace stroke-chart-4"
        />
      )}
    </CartesianSvg>
  );
}
