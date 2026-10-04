import { useNotation } from "../charts/format";
import { memo, useMemo, useRef, type CSSProperties } from "react";
import type { PlotBlock } from "@/lib/tutor/types";
import { m } from "@/paraglide/messages";
import { getLocale } from "@/paraglide/runtime";
import { RichText, splitInlineMath } from "../board-blocks";
import { useWidth } from "../charts/use-width";
import { Math } from "../math";
import { ariaLabel, describe } from "./describe";
import { layout, type PlotLabel, type Scene, type TextBox } from "./layout";
import { sanitise } from "./sanitise";

/**
 * A graph in a cartesian plane (specs/009-board-drawings/plot.md §4). Célestin
 * gives the mathematics, the board samples and draws it: `sanitise` cleans the
 * block once, `layout` makes every geometric decision, and this only draws the
 * scene.
 *
 * The SVG holds only numbers we format (ticks, and the values Célestin shows);
 * everything Célestin writes (titles, labels) is a span over it, typeset by KaTeX.
 * An expression, a domain or an endpoint never becomes text. Nothing reacts to
 * the pointer: no tooltip, no hover, no handler, so a reading exercise shows
 * exactly what is drawn.
 */

const FONT = 12;
const HALO: CSSProperties = { paintOrder: "stroke" };

/** Prose and maths on one line: `$$…$$` is typeset inline too, never as a display block. */
function InlineRich({ text }: { text: string }) {
  return (
    <>
      {splitInlineMath(text).map((part, i) =>
        part.math ? (
          <Math key={i} tex={part.value} block={false} />
        ) : (
          <span key={i}>{part.value}</span>
        ),
      )}
    </>
  );
}

/** Pinned on the side the layout anchored, so a text wider than estimated grows away from its mark. */
function position(box: TextBox | PlotLabel, width: number): CSSProperties {
  return box.align === "right"
    ? { right: width - box.left - box.width, top: box.top }
    : { left: box.left, top: box.top };
}

function Title({ box, width }: { box: TextBox; width: number }) {
  return (
    <span
      className="absolute whitespace-nowrap text-xs leading-5 font-semibold text-muted-foreground"
      style={position(box, width)}
    >
      <InlineRich text={box.text} />
    </span>
  );
}

function Label({ label, width }: { label: PlotLabel; width: number }) {
  const style: CSSProperties = { ...position(label, width) };
  if (label.colour) style.borderBottom = `2px ${label.dashed ? "dashed" : "solid"} ${label.colour}`;
  return (
    <span
      data-plot-label=""
      className="absolute whitespace-nowrap rounded-sm bg-card/85 px-0.5 text-sm leading-5 text-foreground"
      style={style}
    >
      {label.text && <InlineRich text={label.text} />}
      {label.coords && (
        <span className="tabular-nums">
          {label.text ? " " : ""}
          {label.coords}
        </span>
      )}
    </span>
  );
}

function Axes({ scene }: { scene: Scene }) {
  const { frame, xAxis, yAxis } = scene;
  return (
    <g>
      {scene.grid && (
        <g className="stroke-border" strokeWidth={1}>
          {xAxis.ticks.map((t) => (
            <line key={`gx${t.value}`} x1={t.px} x2={t.px} y1={frame.top} y2={frame.bottom} />
          ))}
          {yAxis.ticks.map((t) => (
            <line key={`gy${t.value}`} x1={frame.left} x2={frame.right} y1={t.px} y2={t.px} />
          ))}
        </g>
      )}
      <g className="stroke-muted-foreground" strokeWidth={1}>
        {xAxis.ticks.map((t) => (
          <line key={`tx${t.value}`} x1={t.px} x2={t.px} y1={xAxis.pos - 2} y2={xAxis.pos + 2} />
        ))}
        {yAxis.ticks.map((t) => (
          <line key={`ty${t.value}`} x1={yAxis.pos - 2} x2={yAxis.pos + 2} y1={t.px} y2={t.px} />
        ))}
      </g>
      <g className="stroke-muted-foreground" strokeWidth={1.25}>
        <line x1={xAxis.from} x2={xAxis.to} y1={xAxis.pos} y2={xAxis.pos} />
        <line x1={yAxis.pos} x2={yAxis.pos} y1={yAxis.from} y2={yAxis.to} />
      </g>
      {xAxis.arrow && (
        <path className="fill-muted-foreground" d={`M${xAxis.to} ${xAxis.pos}l-7 -3.5v7z`} />
      )}
      {yAxis.arrow && (
        <path className="fill-muted-foreground" d={`M${yAxis.pos} ${yAxis.to}l-3.5 7h7z`} />
      )}
      <g
        fontSize={FONT}
        className="fill-muted-foreground stroke-card tabular-nums"
        strokeWidth={3}
        style={HALO}
      >
        {xAxis.ticks.map(
          (t) =>
            t.label !== null && (
              <text key={`lx${t.value}`} x={t.px + t.shift} y={xAxis.pos + 16} textAnchor="middle">
                {t.label}
              </text>
            ),
        )}
        {yAxis.ticks.map(
          (t) =>
            t.label !== null && (
              <text
                key={`ly${t.value}`}
                x={yAxis.pos - 6}
                y={t.px + t.shift}
                dy="0.32em"
                textAnchor="end"
              >
                {t.label}
              </text>
            ),
        )}
        {scene.origin && (
          <text x={scene.origin.x} y={scene.origin.y} textAnchor="end">
            0
          </text>
        )}
      </g>
    </g>
  );
}

function Marks({ scene }: { scene: Scene }) {
  return (
    <g>
      {scene.runs.map((run, i) =>
        run.dashed ? (
          <polyline
            key={i}
            points={run.points}
            fill="none"
            strokeWidth={1.5}
            strokeDasharray="6 4"
            style={{ stroke: run.colour }}
          />
        ) : (
          <polyline
            key={i}
            points={run.points}
            pathLength={1}
            fill="none"
            strokeWidth={2.25}
            strokeLinejoin="round"
            strokeLinecap="round"
            className="chart-trace"
            style={{ stroke: run.colour }}
          />
        ),
      )}
      {scene.guides.map((g, i) => (
        <line
          key={i}
          {...g}
          className="stroke-muted-foreground"
          strokeWidth={1}
          strokeDasharray="3 3"
        />
      ))}
      {scene.dots.map((d, i) => (
        <circle key={i} cx={d.x} cy={d.y} r={3.5} style={{ fill: d.colour }} />
      ))}
      {scene.endpoints.map((e, i) =>
        e.hollow ? (
          <circle
            key={i}
            cx={e.x}
            cy={e.y}
            r={4}
            className="fill-card"
            strokeWidth={2}
            style={{ stroke: e.colour }}
          />
        ) : (
          <circle key={i} cx={e.x} cy={e.y} r={4} style={{ fill: e.colour }} />
        ),
      )}
      {scene.marks.map((m, i) =>
        m.mark === "cross" ? (
          <path
            key={i}
            d={`M${m.x - 4.5} ${m.y - 4.5}l9 9m0 -9l-9 9`}
            className="stroke-foreground"
            strokeWidth={2}
            strokeLinecap="round"
          />
        ) : m.mark === "hollow" ? (
          <circle
            key={i}
            cx={m.x}
            cy={m.y}
            r={4}
            className="fill-card stroke-foreground"
            strokeWidth={2}
          />
        ) : (
          <circle key={i} cx={m.x} cy={m.y} r={4} className="fill-foreground" />
        ),
      )}
      {scene.feet.length > 0 && (
        <g
          fontSize={FONT}
          className="fill-foreground stroke-card font-semibold tabular-nums"
          strokeWidth={3}
          style={HALO}
        >
          {scene.feet.map((f, i) => (
            <text
              key={i}
              x={f.x}
              y={f.y}
              dy={f.anchor === "end" ? "0.32em" : undefined}
              textAnchor={f.anchor}
            >
              {f.text}
            </text>
          ))}
        </g>
      )}
    </g>
  );
}

export const PlotView = memo(function PlotView({ block }: { block: PlotBlock }) {
  const ref = useRef<HTMLDivElement>(null);
  const measured = useWidth(ref);
  const plot = useMemo(() => sanitise(block), [block]);
  const notation = useNotation();
  const scene = useMemo(() => layout(plot, measured, notation), [plot, measured, notation]);
  const width = scene.width;

  return (
    <figure className="rounded-lg border border-border bg-card px-5 py-4">
      <div ref={ref} role="img" aria-label={ariaLabel(plot)} className="relative">
        <svg
          width={width}
          height={scene.height}
          aria-hidden="true"
          className="block overflow-visible"
        >
          <Axes scene={scene} />
          <Marks scene={scene} />
        </svg>
        <div aria-hidden="true">
          {scene.yTitle && <Title box={scene.yTitle} width={width} />}
          {scene.xTitle && <Title box={scene.xTitle} width={width} />}
          {scene.labels.map((label, i) => (
            <Label key={i} label={label} width={width} />
          ))}
        </div>
      </div>
      {!scene.drawable && (
        <p className="mt-2 text-center text-sm text-muted-foreground">{m.plot_empty_note()}</p>
      )}
      {plot.caption && (
        <figcaption className="mt-3 text-center text-xs text-muted-foreground">
          {/* KaTeX's html is aria-hidden: a screen reader reads the MathML copy instead. */}
          <span aria-hidden="true">
            <RichText text={plot.caption} />
          </span>
          <span className="sr-only">
            <RichText text={plot.caption} mathOutput="mathml" />
          </span>
        </figcaption>
      )}
      <p lang={getLocale()} className="sr-only">
        {describe(plot, scene, notation)}
      </p>
    </figure>
  );
});
