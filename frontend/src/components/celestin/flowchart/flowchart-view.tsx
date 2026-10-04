import { memo, useMemo, useRef, type CSSProperties } from "react";
import type { FlowchartBlock } from "@/lib/tutor/types";
import { m } from "@/paraglide/messages";
import { getLocale } from "@/paraglide/runtime";
import { RichText } from "../board-blocks";
import { useWidth } from "../charts/use-width";
import { describe, type Step } from "./describe";
import { pathState, sanitise, type Graph } from "./graph";
import { layoutFlowchart, metricsFor, structure, type Layout, type PlacedEdge } from "./layout";
import { measureItems } from "./measure";
import { MeasureLayer } from "./measure-layer";
import { shapeProps } from "./shapes";
import { useLabelSizes } from "./use-label-sizes";

/**
 * A flowchart (organigramme) on the board. Célestin gives nodes and their exits; the
 * board lays them out (`layout.ts`) and draws them: an SVG that holds geometry
 * only, with every label an HTML block over it, rendered by RichText (KaTeX,
 * `trust: false`), so node texts and answers may carry maths.
 *
 * Nothing reacts to the pointer. A hidden node's text never reaches the DOM: it
 * is « ? » from `sanitise` on. When the drawing would have to shrink below 85 %,
 * the steps are listed instead, never scrolled.
 */

type State = "idle" | "path" | "current" | "hidden";

const FILL: Record<State, string> = {
  idle: "fill-card",
  path: "fill-primary/10",
  current: "fill-primary/20",
  hidden: "fill-card",
};
const STROKE: Record<State, { className: string; width: number }> = {
  idle: { className: "stroke-muted-foreground", width: 1.5 },
  path: { className: "stroke-primary", width: 2 },
  current: { className: "stroke-primary", width: 2.5 },
  hidden: { className: "stroke-muted-foreground", width: 1.5 },
};

/** Steps of the animation: a row appears every 60 ms, edges trace from the row above. */
const nodeDelay = (row: number) => Math.min(row * 60, 360);
const edgeDelay = (row: number) => (row + 1) * 60;
const LABEL_AFTER = 500;

function pathD(points: readonly [number, number][], trim: number): string {
  const pts = points.map(([x, y]) => [x, y] as [number, number]);
  // The stroke stops under the arrowhead, whose tip is the route's last point.
  const [a, b] = [pts[pts.length - 2], pts[pts.length - 1]];
  if (a && b) {
    const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (length > trim) {
      b[0] -= ((b[0] - a[0]) / length) * trim;
      b[1] -= ((b[1] - a[1]) / length) * trim;
    }
  }
  return pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`).join(" ");
}

function StepLine({ step, mathOutput }: { step: Step; mathOutput: "html" | "mathml" }) {
  return (
    <>
      {step.parts.map((part, i) =>
        part.rich ? (
          <RichText key={i} text={part.text} mathOutput={mathOutput} />
        ) : (
          <span key={i}>{part.text}</span>
        ),
      )}
    </>
  );
}

function Drawing({ graph, layout }: { graph: Graph; layout: Layout }) {
  const { width, height, scale, metrics } = layout;
  const walk = pathState(graph);
  const animate = graph.path.length === 0;
  const state = (i: number): State =>
    graph.nodes[i]?.hidden
      ? "hidden"
      : walk.current === i
        ? "current"
        : walk.visited.has(i)
          ? "path"
          : "idle";
  const rowOf = (i: number) => layout.nodes[i]?.row ?? 0;
  const onPath = (edge: PlacedEdge) => walk.edges.has(edge.id);
  // Path edges last, so they are drawn over the others.
  const edges = [...layout.edges].sort((a, b) => Number(onPath(a)) - Number(onPath(b)));
  const count = graph.nodes.length;
  const enter = (delay: number): { className?: string; style?: CSSProperties } =>
    animate ? { className: "flow-enter", style: { animationDelay: `${delay}ms` } } : {};

  return (
    <div
      role="img"
      aria-label={m.describe_flowchart_label({ count })}
      className="relative mx-auto"
      style={{ width: width * scale, height: height * scale }}
    >
      <div
        className="absolute top-0 left-0 origin-top-left"
        style={{ width, height, ...(scale < 1 ? { transform: `scale(${scale})` } : {}) }}
      >
        <svg
          width={width}
          height={height}
          aria-hidden="true"
          className="absolute inset-0 overflow-visible"
        >
          <g fill="none" strokeLinejoin="round">
            {edges.map((edge) => {
              const primary = onPath(edge);
              return (
                <path
                  key={edge.id}
                  d={pathD(edge.points, metrics.arrowLength - 1)}
                  pathLength={1}
                  strokeWidth={primary ? 2 : 1.5}
                  className={`${primary ? "stroke-primary" : "stroke-muted-foreground"}${animate ? " chart-trace" : ""}`}
                  style={
                    animate ? { animationDelay: `${edgeDelay(rowOf(edge.from))}ms` } : undefined
                  }
                />
              );
            })}
          </g>
          <g>
            {layout.nodes.map((node) => {
              const s = state(node.index);
              const shape = shapeProps(node.box, node.x, node.cy, metrics);
              const common = {
                className: `${node.box.kind === "start" || node.box.kind === "end" ? (s === "idle" ? "fill-secondary" : FILL[s]) : FILL[s]} ${STROKE[s].className}`,
                strokeWidth: STROKE[s].width,
                ...(s === "hidden" ? { strokeDasharray: "4 3" } : {}),
              };
              return (
                <g key={node.index} data-state={s} {...enter(nodeDelay(node.row))}>
                  {shape.tag === "rect" ? (
                    <rect
                      x={shape.x}
                      y={shape.y}
                      width={shape.width}
                      height={shape.height}
                      rx={shape.rx}
                      {...common}
                    />
                  ) : (
                    <polygon points={shape.points} {...common} />
                  )}
                </g>
              );
            })}
          </g>
          <g>
            {layout.arrows.map((arrow) => {
              const into = layout.edges.filter((e) => e.to === arrow.node);
              const primary = into.some(onPath);
              const delay = Math.min(...into.map((e) => edgeDelay(rowOf(e.from)))) + LABEL_AFTER;
              const { x, y } = arrow;
              const [l, h] = [metrics.arrowLength, metrics.arrowHalf];
              return (
                <polygon
                  key={arrow.node}
                  points={`${x - h},${y - l} ${x + h},${y - l} ${x},${y}`}
                  className={`${primary ? "fill-primary" : "fill-muted-foreground"}${animate ? " flow-enter" : ""}`}
                  style={animate ? { animationDelay: `${delay}ms` } : undefined}
                />
              );
            })}
          </g>
        </svg>
        {layout.nodes.map((node) => {
          const hidden = graph.nodes[node.index]?.hidden ?? false;
          const text = graph.nodes[node.index]?.text ?? "";
          const { left, top, width: w, height: h } = node.label;
          const motion = enter(nodeDelay(node.row));
          return hidden ? (
            <div
              key={node.index}
              aria-hidden="true"
              className={`absolute flex items-center justify-center font-semibold text-muted-foreground ${motion.className ?? ""}`}
              style={{ left, top, width: w, height: h, fontSize: metrics.font, ...motion.style }}
            >
              ?
            </div>
          ) : (
            <div
              key={node.index}
              aria-hidden="true"
              className={`absolute text-center text-foreground ${motion.className ?? ""}`}
              style={{
                left: left - 0.5,
                top,
                width: w + 1,
                fontSize: metrics.font,
                lineHeight: `${metrics.line}px`,
                ...motion.style,
              }}
            >
              <RichText text={text} />
            </div>
          );
        })}
        {layout.edges.map((edge) => {
          if (!edge.label) return null;
          const motion = enter(edgeDelay(rowOf(edge.from)) + LABEL_AFTER);
          return (
            <div
              key={edge.id}
              aria-hidden="true"
              className={`absolute font-semibold whitespace-nowrap text-muted-foreground ${motion.className ?? ""}`}
              style={{
                left: edge.label.left,
                top: edge.label.top,
                fontSize: metrics.edgeFont,
                lineHeight: `${metrics.edgeLine}px`,
                ...motion.style,
              }}
            >
              <RichText text={edge.label.text} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

export const FlowchartView = memo(function FlowchartView({ block }: { block: FlowchartBlock }) {
  const widthRef = useRef<HTMLDivElement>(null);
  const width = useWidth(widthRef);
  const graph = useMemo(() => sanitise(block), [block]);
  const shape = useMemo(() => {
    try {
      return graph.nodes.length > 0 ? structure(graph) : null;
    } catch {
      return null;
    }
  }, [graph]);
  const metrics = metricsFor(width);
  const items = useMemo(() => measureItems(graph), [graph]);
  const { sizes, layerRef } = useLabelSizes(graph, items, metrics, widthRef);
  const layout = useMemo(() => {
    if (!shape) return null;
    try {
      return layoutFlowchart(graph, sizes, width, shape);
    } catch {
      return null;
    }
  }, [graph, shape, sizes, width]);
  const steps = useMemo(() => describe(graph), [graph]);
  const empty = graph.nodes.length === 0;

  return (
    <figure className="rounded-lg border border-border bg-card px-3 py-4 sm:px-5">
      <div ref={widthRef} className="relative">
        {empty ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            {m.describe_flowchart_empty()}
          </p>
        ) : layout ? (
          <Drawing graph={graph} layout={layout} />
        ) : (
          <div>
            <p className="mb-2 text-sm text-muted-foreground">{m.describe_flowchart_too_wide()}</p>
            {/* Read once: the sr-only list below carries the maths as MathML. */}
            <ol aria-hidden="true" className="space-y-1 text-sm">
              {steps.map((step, i) => (
                <li key={i}>
                  <StepLine step={step} mathOutput="html" />
                </li>
              ))}
            </ol>
          </div>
        )}
        {!empty && <MeasureLayer items={items} m={metrics} layerRef={layerRef} />}
      </div>
      {graph.caption && (
        <figcaption className="mt-3 text-center text-xs text-muted-foreground">
          {/* KaTeX's html is aria-hidden: screen readers get a MathML copy. */}
          <span aria-hidden="true">
            <RichText text={graph.caption} />
          </span>
          <span className="sr-only">
            <RichText text={graph.caption} mathOutput="mathml" />
          </span>
        </figcaption>
      )}
      {!empty && (
        <ol lang={getLocale()} className="sr-only">
          {steps.map((step, i) => (
            <li key={i}>
              <StepLine step={step} mathOutput="mathml" />
            </li>
          ))}
        </ol>
      )}
    </figure>
  );
});
