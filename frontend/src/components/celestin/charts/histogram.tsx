import type { Histogram as HistogramChart } from "@/lib/tutor/types";
import { CartesianSvg, MarkValue, valueFrame } from "./axes";
import { useNotation } from "./format";
import { linear } from "./scale";
import { histogramRects, polygonPoints } from "./series";

/**
 * A histogram: contiguous rectangles whose areas are proportional to the values,
 * ticked at the class bounds, with its frequency polygon if Célestin asks for it.
 */
export function Histogram({ chart, width }: { chart: HistogramChart; width: number }) {
  const notation = useNotation();
  const rects = histogramRects(chart.bounds, chart.values, chart.reference_amplitude);
  const polygon =
    chart.polygon && chart.polygon !== "none" ? polygonPoints(rects, chart.polygon) : [];
  const xs = [...chart.bounds, ...polygon.map(([px]) => px)];
  const axis = valueFrame(
    width,
    Math.max(...rects.map((r) => r.height)),
    chart.measure,
    undefined,
    notation,
  );
  const { f, y } = axis;
  const x = linear([Math.min(...xs), Math.max(...xs)], [f.left + 4, f.right - 4]);
  const withBars = chart.bars !== false;

  return (
    <CartesianSvg
      width={width}
      axis={axis}
      labels={chart.bounds.map((b) => ({ at: x(b), text: notation.number(b) }))}
    >
      {withBars &&
        rects.map((r) => (
          <rect
            key={r.x0}
            x={x(r.x0)}
            y={y(r.height)}
            width={x(r.x1) - x(r.x0)}
            height={f.bottom - y(r.height)}
            strokeWidth={1.5}
            className="chart-grow fill-chart-1 stroke-board"
          />
        ))}
      {polygon.length > 1 && (
        <polyline
          points={polygon.map(([px, py]) => `${x(px)},${y(py)}`).join(" ")}
          pathLength={1}
          fill="none"
          strokeWidth={2}
          className={withBars ? "chart-trace stroke-chart-4" : "chart-trace stroke-chart-1"}
        />
      )}
      {chart.show_values &&
        rects.map((r) => (
          <MarkValue
            key={r.x0}
            x={(x(r.x0) + x(r.x1)) / 2}
            y={y(r.height)}
            text={notation.value(r.value, chart.measure)}
          />
        ))}
    </CartesianSvg>
  );
}
