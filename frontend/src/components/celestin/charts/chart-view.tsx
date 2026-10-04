import { memo, useMemo, useRef } from "react";
import type { Chart, ChartBlock } from "@/lib/tutor/types";
import { m } from "@/paraglide/messages";
import { getLocale } from "@/paraglide/runtime";
import { RichText } from "../board-blocks";
import { Bars } from "./bars";
import { Box } from "./box";
import { Cumulative } from "./cumulative";
import { useNotation, type Notation } from "./format";
import { Histogram } from "./histogram";
import { Pie, PIE_COLOURS } from "./pie";
import { cumulativePoints, drawable, entries, sanitise } from "./series";
import { Sticks } from "./sticks";
import { useWidth } from "./use-width";

/**
 * A chart on the board (spec 008). Célestin gives statistics; this draws them.
 *
 * Nothing on a chart reacts to the pointer: no tooltip, no hover, no handler, so
 * a reading exercise shows exactly what is drawn (R5.3). Values are written only
 * when Célestin sets `show_values`, and the screen-reader table follows the same rule.
 */

/** The kind's name and its first table column: message functions, read when the chart renders. */
const KIND: Record<Chart["kind"], { name: () => string; column: () => string }> = {
  bars: { name: m.describe_chart_kind_bars, column: m.describe_chart_column_category },
  sticks: { name: m.describe_chart_kind_sticks, column: m.describe_chart_column_value },
  histogram: { name: m.describe_chart_kind_histogram, column: m.describe_chart_column_class },
  cumulative: { name: m.describe_chart_kind_cumulative, column: m.describe_chart_column_bound },
  pie: { name: m.describe_chart_kind_pie, column: m.describe_chart_column_category },
  box: { name: m.describe_chart_kind_box, column: m.describe_chart_column_series },
};

function Drawing({ chart, width }: { chart: Chart; width: number }) {
  switch (chart.kind) {
    case "bars":
      return <Bars chart={chart} width={width} />;
    case "sticks":
      return <Sticks chart={chart} width={width} />;
    case "histogram":
      return <Histogram chart={chart} width={width} />;
    case "cumulative":
      return <Cumulative chart={chart} width={width} />;
    case "pie":
      return <Pie chart={chart} width={width} />;
    case "box":
      return <Box chart={chart} width={width} />;
  }
}

function PieLegend({ chart }: { chart: Extract<Chart, { kind: "pie" }> }) {
  const notation = useNotation();
  return (
    <ul className="grid content-center gap-1.5 text-sm">
      {entries(chart, notation).map((e, i) => (
        <li key={e.label + i} className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className="size-3 shrink-0 rounded-sm"
            style={{ background: PIE_COLOURS[i % PIE_COLOURS.length] }}
          />
          <span>{e.label}</span>
          {chart.show_values && (
            <span className="ml-auto pl-3 font-semibold tabular-nums">
              {notation.value(e.value, chart.measure)}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

/**
 * Rows for the screen-reader table: what is drawn, and values only when shown.
 * The value column is named after the measure, so it never repeats the first.
 */
function rows(chart: Chart, notation: Notation): { head: string[]; body: string[][] } {
  const shown = chart.show_values ?? false;
  const column = KIND[chart.kind].column();
  if (chart.kind === "box") {
    return {
      head: [column, ...(shown ? notation.boxStats : [])],
      body: chart.boxes.map((b, i) => [
        b.label ?? m.describe_chart_series_n({ n: i + 1 }),
        ...(shown ? [b.minimum, b.q1, b.median, b.q3, b.maximum].map(notation.number) : []),
      ]),
    };
  }
  const value = notation.measureName[chart.measure];
  if (chart.kind === "cumulative") {
    // The points as drawn: each bound with its cumulated value.
    return {
      head: [column, ...(shown ? [m.describe_chart_cumulated({ measure: value })] : [])],
      body: cumulativePoints(chart.bounds, chart.values, chart.direction).map(([b, c]) => [
        notation.number(b),
        ...(shown ? [notation.value(c, chart.measure)] : []),
      ]),
    };
  }
  return {
    head: [column, ...(shown ? [value] : [])],
    body: entries(chart, notation).map((e) => [
      e.label,
      ...(shown ? [notation.value(e.value, chart.measure)] : []),
    ]),
  };
}

export const ChartView = memo(function ChartView({ block }: { block: ChartBlock }) {
  const ref = useRef<HTMLDivElement>(null);
  const width = useWidth(ref);
  const notation = useNotation();
  const chart = useMemo(() => sanitise(block.chart), [block.chart]);
  const something = drawable(chart);
  const yTitle = "y_title" in chart ? chart.y_title : null;
  const xTitle = "x_title" in chart ? (chart.x_title ?? null) : null;
  const table = rows(chart, notation);
  const label = [KIND[chart.kind].name(), yTitle, xTitle].filter(Boolean).join(" — ");

  return (
    <figure className="rounded-lg border border-border bg-card px-5 py-4">
      {yTitle && (
        <p className="mb-1 text-xs font-semibold text-muted-foreground">
          <RichText text={yTitle} />
        </p>
      )}
      <div
        ref={ref}
        role="img"
        aria-label={label}
        className={chart.kind === "pie" ? "flex flex-wrap items-center gap-6" : undefined}
      >
        {something ? (
          <Drawing chart={chart} width={width} />
        ) : (
          <p className="py-8 text-center text-sm text-muted-foreground">
            {m.describe_chart_empty()}
          </p>
        )}
        {chart.kind === "pie" && something && <PieLegend chart={chart} />}
      </div>
      {xTitle && (
        <p className="mt-1 text-right text-xs font-semibold text-muted-foreground">
          <RichText text={xTitle} />
        </p>
      )}
      {chart.caption && (
        <figcaption className="mt-3 text-center text-xs text-muted-foreground">
          {/* KaTeX's html is aria-hidden: screen readers get a MathML copy. */}
          <span aria-hidden="true">
            <RichText text={chart.caption} />
          </span>
          <span className="sr-only">
            <RichText text={chart.caption} mathOutput="mathml" />
          </span>
        </figcaption>
      )}
      <table lang={getLocale()} className="sr-only">
        <caption>{label}</caption>
        <thead>
          <tr>
            {table.head.map((h) => (
              <th key={h} scope="col">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.body.map((row, i) => (
            <tr key={i}>
              {row.map((cell, k) => (
                <td key={k}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
});
