import type { BarChart } from "@/lib/tutor/types";
import { CartesianSvg, MarkValue, textWidth, valueFrame } from "./axes";
import { useNotation } from "./format";
import { entries } from "./series";

/** « Diagramme en barres »: one bar per category of a qualitative variable. */
export function Bars({ chart, width }: { chart: BarChart; width: number }) {
  const notation = useNotation();
  const bars = entries(chart, notation);
  const max = Math.max(...bars.map((b) => b.value));
  const flat = valueFrame(width, max, chart.measure, undefined, notation);
  const band = (flat.f.right - flat.f.left) / bars.length;
  const longest = Math.max(...bars.map((b) => textWidth(b.label)));
  // Labels too long for their band turn, and the plot makes room below.
  const rotate = longest + 8 > band;
  const axis = rotate
    ? valueFrame(width, max, chart.measure, Math.min(120, Math.round(longest * 0.6 + 24)), notation)
    : flat;
  const { f, y } = axis;
  const barWidth = Math.min(56, band * 0.6);
  const centre = (i: number) => f.left + band * (i + 0.5);

  return (
    <CartesianSvg
      width={width}
      axis={axis}
      baseTicks={false}
      rotate={rotate}
      labels={bars.map((b, i) => ({ at: centre(i), text: b.label }))}
    >
      {bars.map((b, i) => (
        <g key={b.label + i}>
          <rect
            x={centre(i) - barWidth / 2}
            y={y(b.value)}
            width={barWidth}
            height={f.bottom - y(b.value)}
            className="chart-grow fill-chart-1"
          />
          {chart.show_values && (
            <MarkValue x={centre(i)} y={y(b.value)} text={notation.value(b.value, chart.measure)} />
          )}
        </g>
      ))}
    </CartesianSvg>
  );
}
