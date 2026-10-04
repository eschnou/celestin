import { FRENCH, type Notation } from "../charts/format";
import {
  angleMark,
  arcPath,
  circlePath,
  clipToWindow,
  fitWindow,
  gridStep,
  groupPoints,
  labelDirection,
  labelStep,
  lookup,
  minorArc,
  multiples,
  nameTex,
  neighbourMap,
  outwardNormal,
  planeWindow,
  polygonCentroid,
  pt,
  radiusOf,
  rightAngleMark,
  segmentTicks,
  spanOf,
  vec,
  vectorPaths,
} from "./geometry";
import {
  clampAnchor,
  labelBox,
  LABEL_H,
  overlaps,
  textPx,
  type Box,
  type Dir,
  type LabelPart,
  type PlacedLabel,
} from "./labels";
import type { CleanPlane, CleanShape, Pt } from "./sanitise";

/**
 * A plane figure as data for `plane.tsx`: every path, mark and label already in
 * pixels. Solid strokes trace themselves once (`chart-trace`); dashed strokes,
 * vector heads and the codage appear with the card.
 */

export type Stroke = {
  key: string;
  d: string;
  className: string;
  width: number;
  trace: boolean;
  dashed: boolean;
  delay: number;
};
export type Fill = { key: string; d: string; className: string };
export type Marker = { key: string; kind: "cross" | "dot"; at: Pt };
export type AxisText = {
  key: string;
  x: number;
  y: number;
  text: string;
  anchor: "start" | "middle" | "end";
};

export type PlaneScene = {
  width: number;
  height: number;
  clip: { x: number; y: number; width: number; height: number };
  grid: string;
  axes: {
    lines: string;
    arrows: string;
    ticks: string;
    numbers: AxisText[];
    names: AxisText[];
  } | null;
  fills: Fill[];
  strokes: Stroke[];
  marks: Stroke[];
  heads: Fill[];
  markers: Marker[];
  labels: PlacedLabel[];
};

/** Unmarked angles, each its own tint: no arc, so none reads as a codage. */
const SECTOR = [
  "fill-chart-1/30",
  "fill-chart-2/30",
  "fill-chart-3/30",
  "fill-chart-5/30",
  "fill-chart-6/30",
];
const SECTOR_STRONG = [
  "fill-chart-1/55",
  "fill-chart-2/55",
  "fill-chart-3/55",
  "fill-chart-5/55",
  "fill-chart-6/55",
];

/** A vector's head, filled in its shaft's colour. */
const HEAD = {
  solid: "fill-foreground",
  dashed: "fill-muted-foreground",
  highlight: "fill-chart-4",
} as const;

function look(shape: CleanShape): { className: string; width: number; dashed: boolean } {
  if (shape.style === "highlight")
    return { className: "stroke-chart-4", width: 2.5, dashed: false };
  if (shape.style === "dashed")
    return { className: "stroke-muted-foreground", width: 1.75, dashed: true };
  return { className: "stroke-foreground", width: 1.75, dashed: false };
}

const path = (ps: Pt[], close = false) =>
  ps.length ? `M ${ps.map(pt).join(" L ")}${close ? " Z" : ""}` : "";

export function planeScene(fig: CleanPlane, W: number, notation: Notation = FRENCH): PlaneScene {
  const win = planeWindow(fig);
  const frame = fitWindow(win, W);
  const { px, s, width, height } = frame;
  const units = lookup(fig);
  const at = (name: string | undefined): Pt | undefined => {
    const p = name === undefined ? undefined : units.get(name);
    return p ? px(p) : undefined;
  };
  const all = fig.points.map((p) => px(p.at));
  const centroid: Pt = all.length
    ? [
        all.reduce((t, p) => t + p[0], 0) / all.length,
        all.reduce((t, p) => t + p[1], 0) / all.length,
      ]
    : [width / 2, height / 2];
  const [left, top] = px([win.x0, win.y1]);
  const [right, bottom] = px([win.x1, win.y0]);

  const labels: PlacedLabel[] = [];
  const boxes: Box[] = [];
  const fit = (anchor: Pt, dir: Dir, w: number) => {
    const [x, y] = clampAnchor(anchor[0], anchor[1], dir, w, LABEL_H, width, height);
    return { x, y, box: labelBox(x, y, dir, w, LABEL_H) };
  };
  const place = (key: string, anchor: Pt, dir: Dir, parts: LabelPart[], w: number) => {
    const { x, y, box } = fit(anchor, dir, w);
    labels.push({ key, x, y, dir, parts });
    boxes.push(box);
  };
  const shapeLabel = (key: string, shape: CleanShape, anchor: Pt, dir: Dir) => {
    if (shape.label)
      place(key, anchor, dir, [{ kind: "rich", text: shape.label }], textPx(shape.label));
  };

  // Grid and axes: the course's quadrillage and repère.
  const step = fig.axes || fig.grid ? gridStep(win.x1 - win.x0, win.y1 - win.y0) : null;
  const xs = step ? multiples(win.x0, win.x1, step) : [];
  const ys = step ? multiples(win.y0, win.y1, step) : [];
  const grid = fig.grid
    ? [
        ...xs.map((x) => `M ${pt(px([x, win.y0]))} L ${pt(px([x, win.y1]))}`),
        ...ys.map((y) => `M ${pt(px([win.x0, y]))} L ${pt(px([win.x1, y]))}`),
      ].join(" ")
    : "";
  let axes: PlaneScene["axes"] = null;
  if (fig.axes && step) {
    const [ox, oy] = px([0, 0]);
    const tipX = right + 12;
    const tipY = top - 12;
    const tickPath = [
      ...xs
        .filter((x) => x !== 0)
        .map((x) => `M ${pt([px([x, 0])[0], oy - 2])} L ${pt([px([x, 0])[0], oy + 2])}`),
      ...ys
        .filter((y) => y !== 0)
        .map((y) => `M ${pt([ox - 2, px([0, y])[1]])} L ${pt([ox + 2, px([0, y])[1]])}`),
    ].join(" ");
    const widest = Math.max(0, ...xs.map((x) => textPx(notation.number(x))));
    const kx = labelStep(step, s, widest + 8);
    const ky = labelStep(step, s, 16);
    const on = (v: number, k: number) =>
      v !== 0 && Math.abs(v / (k * step) - Math.round(v / (k * step))) < 1e-6;
    const originNamed = fig.points.some((p) => p.at[0] === 0 && p.at[1] === 0);
    const numbers: AxisText[] = [
      ...xs
        .filter((x) => on(x, kx))
        .map((x) => ({
          key: `x${x}`,
          x: px([x, 0])[0],
          y: oy + 14,
          text: notation.number(x),
          anchor: "middle" as const,
        })),
      ...ys
        .filter((y) => on(y, ky))
        .map((y) => ({
          key: `y${y}`,
          x: ox - 6,
          y: px([0, y])[1] + 4,
          text: notation.number(y),
          anchor: "end" as const,
        })),
      ...(originNamed
        ? []
        : [{ key: "o", x: ox - 4, y: oy + 13, text: "0", anchor: "end" as const }]),
    ];
    axes = {
      lines: `M ${pt([left, oy])} L ${pt([tipX - 6, oy])} M ${pt([ox, bottom])} L ${pt([ox, tipY + 6])}`,
      arrows: `M ${pt([tipX, oy])} L ${pt([tipX - 7, oy - 3.5])} L ${pt([tipX - 7, oy + 3.5])} Z M ${pt([ox, tipY])} L ${pt([ox - 3.5, tipY + 7])} L ${pt([ox + 3.5, tipY + 7])} Z`,
      ticks: tickPath,
      numbers,
      // Above the x axis and right of the y axis, clear of the numbers.
      names: [
        { key: "nx", x: tipX - 2, y: oy - 6, text: "x", anchor: "end" },
        { key: "ny", x: ox + 7, y: tipY + 8, text: "y", anchor: "start" },
      ],
    };
  }

  // Shapes: polygons first so their fill lies under everything else.
  const order = [
    ...fig.shapes.map((shape, i) => ({ shape, i })).filter(({ shape }) => shape.draw === "polygon"),
    ...fig.shapes.map((shape, i) => ({ shape, i })).filter(({ shape }) => shape.draw !== "polygon"),
  ];
  const fills: Fill[] = [];
  const strokes: Stroke[] = [];
  const marks: Stroke[] = [];
  const heads: Fill[] = [];
  let traced = 0;
  let unmarked = 0;
  const stroke = (key: string, d: string, shape: CleanShape, traceable = true) => {
    if (!d) return;
    const { className, width: w, dashed } = look(shape);
    const trace = traceable && !dashed;
    strokes.push({
      key,
      d,
      className,
      width: w,
      trace,
      dashed,
      delay: trace ? Math.min(traced++, 10) * 60 : 0,
    });
  };
  const staticMark = (key: string, d: string, shape: CleanShape, width = 1.25) => {
    if (!d) return;
    const strong = shape.style === "highlight";
    marks.push({
      key,
      d,
      className: strong ? "stroke-chart-4" : "stroke-foreground",
      width: strong ? 2 : width,
      trace: false,
      dashed: false,
      delay: 0,
    });
  };

  for (const { shape, i } of order) {
    const key = `s${i}`;
    const [p, q, r] = shape.of.map(at);
    const [up, uq, ur] = shape.of.map((n) => units.get(n));
    switch (shape.draw) {
      case "segment": {
        if (!p || !q) break;
        stroke(key, path([p, q]), shape);
        staticMark(`${key}t`, segmentTicks(p, q, shape.marks), shape, 1.5);
        const n = outwardNormal(p, q, centroid);
        shapeLabel(key, shape, vec.add(vec.mul(vec.add(p, q), 0.5), vec.mul(n, 10)), n);
        break;
      }
      case "line":
      case "ray": {
        if (!up || !uq) break;
        const clipped = clipToWindow(up, uq, win, shape.draw === "ray");
        if (!clipped) break;
        const [a, b] = [px(clipped[0]), px(clipped[1])];
        stroke(key, path([a, b]), shape);
        const back = vec.unit(vec.sub(a, b));
        const n = outwardNormal(a, b, centroid);
        if (back) shapeLabel(key, shape, vec.add(vec.add(b, vec.mul(back, 16)), vec.mul(n, 10)), n);
        break;
      }
      case "vector": {
        if (!p || !q) break;
        const v = vectorPaths(p, q);
        if (!v) break;
        stroke(key, v.shaft, shape, false);
        heads.push({ key: `${key}h`, d: v.head, className: HEAD[shape.style ?? "solid"] });
        const n = outwardNormal(p, q, centroid);
        shapeLabel(key, shape, vec.add(vec.mul(vec.add(p, q), 0.5), vec.mul(n, 10)), n);
        break;
      }
      case "polygon": {
        const ps = shape.of.map(at).filter((x): x is Pt => x !== undefined);
        if (ps.length < 3) break;
        fills.push({
          key: `${key}f`,
          d: path(ps, true),
          className: shape.style === "highlight" ? "fill-chart-4/15" : "fill-foreground/5",
        });
        stroke(key, path(ps, true), shape);
        shapeLabel(key, shape, polygonCentroid(ps), [0, 0]);
        break;
      }
      case "circle": {
        if (!p) break;
        const radius = radiusOf(shape, units) * s;
        stroke(key, circlePath(p, radius), shape);
        const d: Dir = [Math.SQRT1_2, -Math.SQRT1_2];
        shapeLabel(key, shape, vec.add(p, vec.mul(d, radius + 4)), d);
        break;
      }
      case "arc": {
        if (!up || !uq || !ur) break;
        stroke(key, arcPath(up, uq, ur, px, s), shape);
        const arc = minorArc(up, uq, ur);
        if (!arc || !q) break;
        const mid = arc.from + arc.delta / 2;
        const onArc = px(vec.add(uq, [arc.r * Math.cos(mid), arc.r * Math.sin(mid)]));
        const out = vec.unit(vec.sub(onArc, q)) ?? [0, -1];
        shapeLabel(key, shape, vec.add(onArc, vec.mul(out, 4)), out);
        break;
      }
      case "angle": {
        if (!p || !q || !r) break;
        const mark = angleMark(p, q, r, shape.marks);
        if (!mark) break;
        if (mark.sector) {
          const tints = shape.style === "highlight" ? SECTOR_STRONG : SECTOR;
          fills.push({
            key: `${key}a`,
            d: mark.sector,
            className: tints[unmarked % tints.length] ?? "",
          });
          unmarked += 1;
        }
        mark.arcs.forEach((d, k) => staticMark(`${key}a${k}`, d, shape));
        shapeLabel(key, shape, vec.add(q, vec.mul(mark.bisector, mark.r0 + 12)), mark.bisector);
        break;
      }
      case "right_angle": {
        if (!p || !q || !r) break;
        const mark = rightAngleMark(p, q, r);
        if (!mark) break;
        staticMark(`${key}r`, mark.path, shape);
        shapeLabel(key, shape, vec.add(q, vec.mul(mark.bisector, mark.size + 12)), mark.bisector);
        break;
      }
    }
  }

  // Points: one marker and one label for names at the very same place.
  const neighbours = neighbourMap(fig);
  const markers: Marker[] = [];
  // Coincident within float noise of the drawn window, as the tool's span counts it.
  const span = Math.max(spanOf(fig.points), win.x1 - win.x0, win.y1 - win.y0);
  const grouped = groupPoints(fig.points, span);
  // Every point's mark, which no other point's label may cover.
  const markBoxes = grouped.map((g) => {
    const [x, y] = px(g.at);
    return { x0: x - 4, y0: y - 4, x1: x + 4, y1: y + 4 };
  });
  for (const [index, group] of grouped.entries()) {
    const where = px(group.at);
    markers.push({ key: group.names.join("="), kind: fig.marker, at: where });
    const near = group.names
      .flatMap((n) => neighbours.get(n) ?? [])
      .map(at)
      .filter((x): x is Pt => x !== undefined);
    const tex = group.names.map(nameTex).join(" = ");
    const parts: LabelPart[] = [{ kind: "tex", text: tex }];
    let w = textPx(`$${tex}$`);
    if (fig.showValues) {
      const text = notation.pair(group.at[0], group.at[1]);
      parts.push({ kind: "plain", text });
      w += textPx(text);
    }
    // Away from the shapes meeting there. When a label or another point's mark is
    // already there (a midpoint on a labelled segment, a dense repère), the other
    // side, then a quarter turn either way: the first that covers the fewest.
    const preferred = labelDirection(where, near, centroid);
    const crowd = (dir: Dir) => {
      const { box } = fit(vec.add(where, vec.mul(dir, 8)), dir, w);
      const others = markBoxes.filter((_, k) => k !== index);
      return [...boxes, ...others].filter((b) => overlaps(b, box)).length;
    };
    const quarter: Dir = [-preferred[1], preferred[0]];
    const candidates: Dir[] = [preferred, vec.mul(preferred, -1), quarter, vec.mul(quarter, -1)];
    const scored = candidates.map((d) => ({ d, n: crowd(d) }));
    const dir = scored.reduce((best, c) => (c.n < best.n ? c : best)).d;
    place(`p${group.names.join("=")}`, vec.add(where, vec.mul(dir, 8)), dir, parts, w);
  }

  // An axis number under a point's label, or on its mark, gives way.
  if (axes) {
    const marks = markers.map(({ at: [x, y] }) => ({ x0: x - 4, y0: y - 4, x1: x + 4, y1: y + 4 }));
    axes.numbers = axes.numbers.filter((n) => {
      const w = textPx(n.text);
      const x0 = n.anchor === "end" ? n.x - w : n.x - w / 2;
      const box = { x0, y0: n.y - 10, x1: x0 + w, y1: n.y + 2 };
      return ![...boxes, ...marks].some((b) => overlaps(b, box));
    });
  }

  return {
    width,
    height,
    clip: { x: left - 4, y: top - 4, width: right - left + 8, height: bottom - top + 8 },
    grid,
    axes,
    fills,
    strokes,
    marks,
    heads,
    markers,
    labels,
  };
}
