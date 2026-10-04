import type { PieChart } from "@/lib/tutor/types";
import { arcPath, pieArcs } from "./series";

/** Sector colours, in order; the legend in `ChartView` uses the same list. */
export const PIE_COLOURS = Array.from({ length: 8 }, (_, i) => `var(--chart-${i + 1})`);

/** « Diagramme circulaire »: sectors clockwise from 12 o'clock. The legend is HTML, beside it. */
export function Pie({ chart, width }: { chart: PieChart; width: number }) {
  const size = Math.min(width, 260);
  const r = size / 2 - 4;
  return (
    <svg width={size} height={size} aria-hidden="true">
      {pieArcs(chart.values).map((arc, i) =>
        arc.value > 0 ? (
          <path
            key={i}
            d={arcPath(size / 2, size / 2, r, arc.start, arc.end)}
            style={{ fill: PIE_COLOURS[i % PIE_COLOURS.length] }}
            strokeWidth={2}
            className="stroke-board"
          />
        ) : null,
      )}
    </svg>
  );
}
