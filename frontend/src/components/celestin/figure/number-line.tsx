import { useMemo } from "react";
import { LabelLayer } from "./label-layer";
import type { PlacedLabel } from "./labels";
import { useNotation } from "../charts/format";
import { bracketArms, bracketPath, colourOf, lineLayout, type LaidGroup } from "./line";
import type { CleanLine } from "./sanitise";

/**
 * A number line (droite graduée): graduations and numbers under the axis, each
 * set of intervals in its own lane and colour, drawn in the course's convention:
 * brackets, filled and hollow dots, or hatching over what does not belong. The
 * hatching is the lane's, drawn once over what none of its sets holds. Every
 * bound and placed number has its tick; a placed number also has its dot, drawn
 * over the sets' bands.
 */

function Group({
  group,
  convention,
  axisY,
}: {
  group: LaidGroup;
  convention: CleanLine["convention"];
  axisY: number;
}) {
  const colour = colourOf(group.index);
  const { y, lane } = group;
  const ends = group.pieces.flatMap((p) => [
    ...(p.start === null ? [] : [{ x: p.start, side: "start" as const, closed: p.closedStart }]),
    ...(p.end === null ? [] : [{ x: p.end, side: "end" as const, closed: p.closedEnd }]),
  ]);
  return (
    <g>
      {lane > 0 &&
        ends.map((e) => (
          <path
            key={`g${e.side}${e.x}`}
            d={`M ${e.x} ${y} V ${axisY}`}
            strokeDasharray="2 3"
            strokeWidth={1}
            className="stroke-muted-foreground"
          />
        ))}
      {convention !== "hatched" &&
        group.pieces.map((p, i) => (
          <path
            // By index, not pixel position: a resize must not remount it and replay its trace.
            key={`b${i}`}
            d={`M ${p.from} ${y} H ${p.to}`}
            fill="none"
            strokeWidth={lane === 0 ? 5 : 4}
            pathLength={1}
            className={`chart-trace ${colour.stroke}`}
          />
        ))}
      {ends.map((e) =>
        convention === "dots" ? (
          <circle
            key={`e${e.side}${e.x}`}
            cx={e.x}
            cy={y}
            r={4.5}
            strokeWidth={2}
            className={e.closed ? `${colour.fill} ${colour.stroke}` : `fill-card ${colour.stroke}`}
          />
        ) : (
          <path
            key={`e${e.side}${e.x}`}
            d={bracketPath(e.x, y, bracketArms(e.side, e.closed))}
            fill="none"
            strokeWidth={2}
            className={colour.stroke}
          />
        ),
      )}
    </g>
  );
}

export function NumberLineDrawing({
  fig,
  width,
  uid,
}: {
  fig: CleanLine;
  width: number;
  uid: string;
}) {
  const notation = useNotation();
  const layout = useMemo(() => lineLayout(fig, width, notation), [fig, width, notation]);
  const { axisY, x0, x1 } = layout;
  const hatch = `${uid}-hatch`;
  const labels: PlacedLabel[] = [
    ...layout.groups.flatMap((g) =>
      g.labels.map((line, j) => ({
        key: `l${g.index}-${j}`,
        x: line.x,
        y: line.y,
        dir: [1, 0] as [number, number],
        parts: [{ kind: "rich" as const, text: line.text }],
        className: colourOf(g.index).text,
      })),
    ),
    ...layout.numbers.map((n) => ({
      key: n.key,
      x: n.x,
      y: n.y,
      dir: [0, 1] as [number, number],
      parts: [{ kind: n.rich ? ("rich" as const) : ("plain" as const), text: n.text }],
    })),
  ];
  return (
    <div className="relative" style={{ width, height: layout.height }}>
      <svg width={width} height={layout.height} aria-hidden="true" className="overflow-visible">
        <defs>
          <pattern
            id={hatch}
            width={7}
            height={7}
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)"
          >
            <path d="M 0 0 V 7" strokeWidth={2} className="stroke-chart-1" />
          </pattern>
        </defs>
        <path
          d={`M ${x0} ${axisY} H ${x1 - 6}`}
          strokeWidth={1.25}
          className="stroke-muted-foreground"
        />
        <path
          d={`M ${x1} ${axisY} L ${x1 - 7} ${axisY - 3.5} L ${x1 - 7} ${axisY + 3.5} Z`}
          className="fill-muted-foreground"
        />
        {layout.graduations.map((x) => (
          <path
            key={`t${x}`}
            d={`M ${x} ${axisY - 3} V ${axisY + 3}`}
            strokeWidth={1}
            className="stroke-muted-foreground"
          />
        ))}
        {layout.bounds.map((b, i) => (
          <path
            key={`b${i}`}
            d={`M ${b.x} ${axisY - 5} V ${axisY + 5}`}
            strokeWidth={1.25}
            className="stroke-foreground"
          />
        ))}
        {layout.hatches.flatMap((h) =>
          h.spans.map(([a, b], i) => (
            <rect
              key={`h${h.lane}-${i}`}
              data-hatch={h.lane}
              x={a}
              y={h.y - 8}
              width={b - a}
              height={8}
              fill={`url(#${hatch})`}
            />
          )),
        )}
        {layout.groups.map((g) => (
          <Group key={g.index} group={g} convention={fig.convention} axisY={axisY} />
        ))}
        {layout.bounds.map((b, i) =>
          b.dot ? (
            <circle
              key={`m${i}`}
              data-mark=""
              cx={b.x}
              cy={axisY}
              r={3.5}
              className="fill-foreground"
            />
          ) : null,
        )}
      </svg>
      <LabelLayer labels={labels} />
    </div>
  );
}
