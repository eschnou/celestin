import { useMemo, type ReactNode } from "react";
import { LabelLayer } from "./label-layer";
import type { Flow, PlacedLabel } from "./labels";
import type { CleanSets } from "./sanitise";
import {
  BOARD_PX,
  layoutWidth,
  setsLayout,
  shapePath,
  zoneCut,
  type Rect,
  type SetShape,
} from "./venn";

/**
 * A diagram of sets. Overlapping or separate sets are coloured outlines with
 * their names above; nested sets are rounded rectangles in the ink colour, each
 * named in its own band. Elements flow in HTML over the SVG, zone by zone; a
 * hatched zone is the hatch pattern clipped to its sets and masked by the others.
 *
 * The layout is built for a 294 px drawing and only grows: a narrower board (a
 * phone) scales the whole drawing down rather than letting anything overlap.
 */

const OUTLINE = [
  { stroke: "stroke-chart-1", text: "text-chart-1" },
  { stroke: "stroke-chart-4", text: "text-chart-4" },
  { stroke: "stroke-chart-2", text: "text-chart-2" },
] as const;

function ShapeEl({ shape, fill }: { shape: SetShape; fill?: string }) {
  if (shape.kind === "ellipse") {
    return <ellipse cx={shape.cx} cy={shape.cy} rx={shape.rx} ry={shape.ry} fill={fill} />;
  }
  return (
    <rect
      x={shape.x0}
      y={shape.y0}
      width={Math.max(0, shape.x1 - shape.x0)}
      height={Math.max(0, shape.y1 - shape.y0)}
      rx={shape.r}
      fill={fill}
    />
  );
}

const box = (r: Rect) => ({
  x: r.x0,
  y: r.y0,
  width: Math.max(0, r.x1 - r.x0),
  height: Math.max(0, r.y1 - r.y0),
});

export function SetDrawing({ fig, width, uid }: { fig: CleanSets; width: number; uid: string }) {
  const L = layoutWidth(width);
  const layout = useMemo(() => setsLayout(fig, L), [fig, L]);
  const scale = width < BOARD_PX ? width / BOARD_PX : 1;
  const left = width > L ? (width - L) / 2 : 0;
  const H = layout.height;
  const hatch = `${uid}-hatch`;
  const nested = fig.layout === "nested";
  const setClip = (i: number) => (i < 0 ? `${uid}-universe` : `${uid}-set-${i}`);

  const labels: PlacedLabel[] = layout.labels.map((l) => ({
    key: l.key,
    x: l.x,
    y: l.y,
    dir: l.dir,
    parts: [{ kind: "rich", text: l.text }],
    ...(nested ? {} : { className: OUTLINE[l.set % OUTLINE.length]?.text ?? "" }),
  }));
  if (fig.universe && layout.universeLabel) {
    labels.push({
      key: "u",
      x: layout.universeLabel.x,
      y: layout.universeLabel.y,
      dir: [1, 0],
      parts: [{ kind: "rich", text: fig.universe }],
      className: "text-muted-foreground",
    });
  }
  const flows: Flow[] = layout.zones.map((z) => ({
    key: `z${z.key}`,
    left: z.rect.x0,
    top: z.rect.y0,
    width: Math.max(0, z.rect.x1 - z.rect.x0),
    height: Math.max(0, z.rect.y1 - z.rect.y0),
    items: z.items,
    column: z.column,
  }));

  return (
    <div className="relative" style={{ width, height: H * scale }}>
      <div
        className="absolute top-0"
        style={{
          left,
          width: L,
          height: H,
          ...(scale < 1 ? { transform: `scale(${scale})`, transformOrigin: "top left" } : {}),
        }}
      >
        <svg width={L} height={H} aria-hidden="true" className="overflow-visible">
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
            {layout.shapes.map((shape, i) => (
              <clipPath key={i} id={setClip(i)}>
                <ShapeEl shape={shape} />
              </clipPath>
            ))}
            {layout.universe && (
              <clipPath id={setClip(-1)}>
                <rect {...box(layout.universe)} />
              </clipPath>
            )}
            {fig.shade.map((zone, j) => (
              <mask
                key={j}
                id={`${uid}-zone-${j}`}
                maskUnits="userSpaceOnUse"
                x={0}
                y={0}
                width={L}
                height={H}
              >
                <rect x={0} y={0} width={L} height={H} fill="white" />
                {zoneCut(fig, zone).outside.map((k) => {
                  const shape = layout.shapes[k];
                  return shape ? <ShapeEl key={k} shape={shape} fill="black" /> : null;
                })}
              </mask>
            ))}
          </defs>
          {layout.universe && (
            <rect
              {...box(layout.universe)}
              rx={6}
              fill="none"
              strokeWidth={1.25}
              className="stroke-muted-foreground"
            />
          )}
          {fig.shade.map((zone, j) => {
            const { inside } = zoneCut(fig, zone);
            const hatched: ReactNode = (
              <rect
                x={0}
                y={0}
                width={L}
                height={H}
                fill={`url(#${hatch})`}
                mask={`url(#${uid}-zone-${j})`}
              />
            );
            return (
              <g key={j} data-zone={zone.join("")}>
                {inside.reduceRight<ReactNode>(
                  (child, k) => (
                    <g clipPath={`url(#${setClip(k)})`}>{child}</g>
                  ),
                  hatched,
                )}
              </g>
            );
          })}
          {layout.shapes.map((shape, i) => (
            <path
              key={i}
              d={shapePath(shape)}
              fill="none"
              strokeWidth={nested ? 1.5 : 1.75}
              pathLength={1}
              style={{ animationDelay: `${i * 60}ms` }}
              className={`chart-trace ${nested ? "stroke-foreground" : (OUTLINE[i % OUTLINE.length]?.stroke ?? "")}`}
            />
          ))}
        </svg>
        <LabelLayer labels={labels} flows={flows} />
      </div>
    </div>
  );
}
