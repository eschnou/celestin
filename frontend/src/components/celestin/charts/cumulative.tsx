import type { CumulativePolygon } from "@/lib/tutor/types";
import { CartesianSvg, MarkValue, valueFrame } from "./axes";
import { useNotation } from "./format";
import { linear } from "./scale";
import { cumulativePoints } from "./series";

/** « Polygone des effectifs / fréquences cumulé(e)s »: one point per class bound. */
export function Cumulative({ chart, width }: { chart: CumulativePolygon; width: number }) {
  const notation = useNotation();
  const points = cumulativePoints(chart.bounds, chart.values, chart.direction);
  const axis = valueFrame(
    width,
    Math.max(...points.map(([, c]) => c)),
    chart.measure,
    undefined,
    notation,
  );
  const { f, y } = axis;
  const bounds = points.map(([b]) => b);
  const x = linear([Math.min(...bounds), Math.max(...bounds)], [f.left + 4, f.right - 4]);

  return (
    <CartesianSvg
      width={width}
      axis={axis}
      labels={bounds.map((b) => ({ at: x(b), text: notation.number(b) }))}
    >
      <polyline
        points={points.map(([b, c]) => `${x(b)},${y(c)}`).join(" ")}
        pathLength={1}
        fill="none"
        strokeWidth={2}
        className="chart-trace stroke-chart-1"
      />
      {points.map(([b, c]) => (
        <g key={b}>
          <circle cx={x(b)} cy={y(c)} r={3.5} className="fill-chart-1" />
          {chart.show_values && (
            <MarkValue x={x(b)} y={y(c)} text={notation.value(c, chart.measure)} />
          )}
        </g>
      ))}
    </CartesianSvg>
  );
}
