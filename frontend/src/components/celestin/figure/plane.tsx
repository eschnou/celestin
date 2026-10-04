import { useMemo } from "react";
import { LabelLayer } from "./label-layer";
import { useNotation } from "../charts/format";
import { planeScene, type Stroke } from "./plane-scene";
import type { CleanPlane } from "./sanitise";

/**
 * Plane geometry: a repère or a bare figure, drawn to scale from points in the
 * figure's own units. Every traced stroke is a `<path>` so `pathLength` works;
 * a dashed stroke never gets one (it would turn « 6 4 » into a solid line).
 */

function Path({ stroke }: { stroke: Stroke }) {
  return (
    <path
      d={stroke.d}
      fill="none"
      strokeWidth={stroke.width}
      strokeLinejoin="round"
      className={stroke.trace ? `chart-trace ${stroke.className}` : stroke.className}
      {...(stroke.trace ? { pathLength: 1, style: { animationDelay: `${stroke.delay}ms` } } : {})}
      {...(stroke.dashed ? { strokeDasharray: "6 4" } : {})}
    />
  );
}

export function PlaneDrawing({ fig, width, uid }: { fig: CleanPlane; width: number; uid: string }) {
  const notation = useNotation();
  const scene = useMemo(() => planeScene(fig, width, notation), [fig, width, notation]);
  const clip = `${uid}-win`;
  return (
    <div className="relative" style={{ width: scene.width, height: scene.height }}>
      <svg
        width={scene.width}
        height={scene.height}
        aria-hidden="true"
        className="overflow-visible"
      >
        <defs>
          <clipPath id={clip}>
            <rect
              x={scene.clip.x}
              y={scene.clip.y}
              width={scene.clip.width}
              height={scene.clip.height}
            />
          </clipPath>
        </defs>
        {scene.grid && (
          <path d={scene.grid} fill="none" strokeWidth={1} className="stroke-border" />
        )}
        {scene.axes && (
          <g>
            <path
              d={scene.axes.lines}
              fill="none"
              strokeWidth={1.25}
              className="stroke-muted-foreground"
            />
            <path d={scene.axes.arrows} className="fill-muted-foreground" />
            <path
              d={scene.axes.ticks}
              fill="none"
              strokeWidth={1}
              className="stroke-muted-foreground"
            />
            {scene.axes.numbers.map((n) => (
              <text
                key={n.key}
                x={n.x}
                y={n.y}
                textAnchor={n.anchor}
                fontSize={11}
                className="fill-muted-foreground tabular-nums"
              >
                {n.text}
              </text>
            ))}
            {scene.axes.names.map((n) => (
              <text
                key={n.key}
                x={n.x}
                y={n.y}
                textAnchor={n.anchor}
                fontSize={12}
                fontStyle="italic"
                className="fill-muted-foreground"
              >
                {n.text}
              </text>
            ))}
          </g>
        )}
        <g clipPath={`url(#${clip})`}>
          {scene.fills.map((f) => (
            <path key={f.key} d={f.d} className={f.className} />
          ))}
          {scene.strokes.map((s) => (
            <Path key={s.key} stroke={s} />
          ))}
          {scene.marks.map((s) => (
            <Path key={s.key} stroke={s} />
          ))}
          {scene.heads.map((f) => (
            <path key={f.key} d={f.d} className={f.className} />
          ))}
        </g>
        {scene.markers.map((m) =>
          m.kind === "dot" ? (
            <circle
              key={m.key}
              data-marker="dot"
              cx={m.at[0]}
              cy={m.at[1]}
              r={3}
              className="fill-foreground"
            />
          ) : (
            <g key={m.key} data-marker="cross" strokeWidth={1.5} className="stroke-foreground">
              <path d={`M ${m.at[0] - 3.5} ${m.at[1] - 3.5} L ${m.at[0] + 3.5} ${m.at[1] + 3.5}`} />
              <path d={`M ${m.at[0] - 3.5} ${m.at[1] + 3.5} L ${m.at[0] + 3.5} ${m.at[1] - 3.5}`} />
            </g>
          ),
        )}
      </svg>
      <LabelLayer labels={scene.labels} />
    </div>
  );
}
