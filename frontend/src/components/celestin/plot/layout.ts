import { textWidth } from "../charts/axes";
import { FRENCH, type Notation } from "../charts/format";
import { linear } from "../charts/scale";
import { colourGroups, colourOf } from "./groups";
import {
  labelSize,
  LABEL_HEIGHT,
  Occupancy,
  placeLabels,
  type Anchored,
  type Box,
  type LabelRequest,
} from "./labels";
import { clipLine, endpointValue, sampleCurve, sequenceDots, type Run, type Win } from "./sample";
import type { CleanPlot, Mark } from "./sanitise";
import { autoStep, axisAt, labelEvery, labelled, stepTicks } from "./ticks";

/**
 * Every geometric decision of a plot, in pixels, from the clean plot and the
 * board's width: the frame, both axes and their graduations, the sampled curves,
 * the marks, and where each title and label goes. Pure, so it is tested without
 * a DOM; `PlotView` only draws the scene.
 */

export type Frame = { left: number; right: number; top: number; bottom: number };
export type Tick = {
  px: number;
  value: number;
  label: string | null;
  /** The label's offset from its tick, along the axis: off the other axis's line at a corner. */
  shift: number;
};
export type Axis = {
  /** The axis line's position across it: y for the horizontal axis, x for the vertical. */
  pos: number;
  /** Where the line starts and ends along it (the arrow tip included). */
  from: number;
  to: number;
  arrow: boolean;
  step: number;
  ticks: Tick[];
};
export type TextBox = Anchored & { text: string };
export type PlotLabel = Anchored & {
  text: string | null;
  coords: string | null;
  /** The group's colour, as the label's underline; null for a point's label. */
  colour: string | null;
  dashed: boolean;
};
export type Legend = { label: string | null; curves: number; sequences: number; lines: number };
export type Scene = {
  width: number;
  height: number;
  frame: Frame;
  win: Win;
  xAxis: Axis;
  yAxis: Axis;
  /** The single « 0 » written below-left of the origin when both axes cross there. */
  origin: { x: number; y: number } | null;
  grid: boolean;
  runs: { points: string; colour: string; dashed: boolean }[];
  dots: { x: number; y: number; colour: string }[];
  endpoints: { x: number; y: number; colour: string; hollow: boolean }[];
  marks: { x: number; y: number; mark: Mark }[];
  guides: { x1: number; y1: number; x2: number; y2: number }[];
  feet: { x: number; y: number; text: string; anchor: "middle" | "end" }[];
  xTitle: TextBox | null;
  yTitle: TextBox | null;
  /** The x title went to the band under the plot: something is drawn at the arrow. */
  xTitleBelow: boolean;
  labels: PlotLabel[];
  /** What is visibly drawn, per colour group and for the dashed layers (for `describe`). */
  legend: Legend[];
  dashed: (string | null)[];
  points: number[];
  drawable: boolean;
};

const MIN_WIDTH = 160;
const TITLE_TOP = 2; // the y title's band over the plot, 2 to 22 px
const TITLE_BOTTOM = TITLE_TOP + LABEL_HEIGHT;
const TOP = TITLE_BOTTOM + 2; // the frame's top when the y title sits right of the arrow
const RIGHT = 16;
const MIN_LEFT = 10;
const MIN_BOTTOM = 10;
const ARROW = 10;
const TICK_GAP = 6; // y labels, right-aligned left of the axis
const TICK_HALF = 7; // half a tick label's box height
const X_LABEL_DY = 16; // x labels' baseline under the axis
const X_LABEL_BOTTOM = 20; // how far under the axis an x label reaches
// A tick label's ink, 12 px digits (a decimal comma's tail included): an x label
// from 7 to 18 px under the axis, a y label from 5 px over its tick to 6 px under.
const X_INK_TOP = 7;
const Y_INK_TOP = 5;
const INK_HEIGHT = 11;
// How far a corner label moves off the other axis's line: up (or down, when that
// axis is the window's top edge) for a y label; sideways, 3 px clear, for an x label.
const LIFT = 8;
const DROP = 7;
const SIDESTEP = 3;
const TITLE_GAP = 4;
const BAND = 22; // the band under the plot the x title may take
const ORTHONORMAL_MAX_HEIGHT = 480;
const TITLE_SCALE = 12 / 14;
const LABEL_FRACTIONS = [0.85, 0.7, 0.55, 0.4, 0.25, 0.95];

const r1 = (v: number) => Math.round(v * 10) / 10;
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

const overlaps = (a: Box, b: Box, pad = 0) =>
  a.left < b.left + b.width + pad &&
  b.left < a.left + a.width + pad &&
  a.top < b.top + b.height + pad &&
  b.top < a.top + a.height + pad;

/** A step that graduates the other window in 1 to 60 intervals: the same for both axes. */
const fits = (step: number, [a, b]: [number, number]) => {
  const count = (b - a) / step;
  return count >= 1 - 1e-9 && count <= 60 + 1e-9;
};

type Side = "right" | "left" | "row";

/**
 * Where the y title goes, in the band over the plot: right of the vertical axis's
 * arrow when it fits, else left of it, else on a row of its own.
 */
function titleSide(axisX: number, width: number, W: number): Side {
  if (axisX + 8 + width <= W) return "right";
  if (axisX - 8 - width >= 0) return "left";
  return "row";
}

/**
 * The frame's top, under the y title. Right of the arrow, nothing else is in the
 * band. Left of it, the top graduation's label (left of the axis too) moves down
 * clear of the title; on a row of its own, the arrow does as well.
 */
function frameTop(side: Side | null, arrow: boolean): number {
  if (side === null || side === "right") return TOP;
  const label = TITLE_BOTTOM + 1 + TICK_HALF;
  return side === "left" ? label : Math.max(label, TITLE_BOTTOM + 2 + (arrow ? ARROW : 0));
}

function titleBox(text: string, width: number, side: Side, axisX: number, W: number): TextBox {
  const box = { top: TITLE_TOP, width: Math.min(width, W), height: LABEL_HEIGHT, text };
  if (side === "right") return { ...box, left: axisX + 8, align: "left" };
  if (side === "left") return { ...box, left: axisX - 8 - width, align: "right" };
  const left = clamp(axisX - width / 2, 0, Math.max(0, W - width));
  return { ...box, left, align: left > 0 && left + width >= W - 0.5 ? "right" : "left" };
}

export function layout(plot: CleanPlot, measured: number, notation: Notation = FRENCH): Scene {
  const tickWidth = (t: number) => textWidth(notation.number(t));
  const W = Math.max(MIN_WIDTH, Math.round(Number.isFinite(measured) ? measured : MIN_WIDTH));
  const [x0, x1] = plot.x_range;
  const [y0, y1] = plot.y_range;
  const win: Win = { x0, x1, y0, y1 };
  const xAt = axisAt(y0, y1); // the horizontal axis, at this y
  const yAt = axisAt(x0, x1); // the vertical axis, at this x
  const integerX = plot.sequences.length > 0;

  // Pass 1: the steps, from an estimate of the plot's size. An orthonormal plot
  // uses the step Célestin gave on one axis for the other, so the grid's cells are square.
  const baseH = Math.round(clamp(0.75 * W, 240, 420));
  let estW = W - RIGHT - 40;
  let estH = baseH - TOP - 2 * MIN_BOTTOM;
  if (plot.orthonormal) {
    const unit = Math.min(estW / (x1 - x0), ORTHONORMAL_MAX_HEIGHT / (y1 - y0));
    estW = unit * (x1 - x0);
    estH = unit * (y1 - y0);
  }
  const shared = plot.orthonormal ? plot.y_step : null;
  const xStep =
    plot.x_step ??
    (shared !== null && fits(shared, plot.x_range) && (!integerX || Number.isInteger(shared))
      ? shared
      : autoStep(x0, x1, estW, integerX));
  const yStep =
    plot.y_step ??
    (plot.orthonormal && fits(xStep, plot.y_range) ? xStep : autoStep(y0, y1, estH, false));
  const xValues = stepTicks(x0, x1, xStep);
  const yValues = stepTicks(y0, y1, yStep);

  // Pass 2: the frame, across. The vertical axis's labels must fit left of it;
  // the left margin grows just enough.
  const right0 = W - RIGHT;
  const widestY = Math.max(0, ...yValues.map(tickWidth));
  const s = (yAt.at - x0) / (x1 - x0); // where the vertical axis sits, 0 = left edge
  const needLeft = widestY + TICK_GAP + 4;
  let left = s < 1 ? Math.max(MIN_LEFT, (needLeft - s * right0) / (1 - s)) : MIN_LEFT;
  let right = right0;
  let unit = 0;
  if (plot.orthonormal) {
    unit = Math.min((right - left) / (x1 - x0), ORTHONORMAL_MAX_HEIGHT / (y1 - y0));
    const plotW = unit * (x1 - x0);
    left += (right - left - plotW) / 2;
    right = left + plotW;
  }
  const frameLeft = r1(left);
  const frameRight = r1(right);
  const sx = linear([x0, x1], [frameLeft, frameRight]);
  const px = (x: number) => r1(sx(x));
  const axisX = px(yAt.at);

  // Pass 3: the frame, down. Its top leaves the y title its band; the horizontal
  // axis's labels must fit under it, so the bottom margin grows just enough.
  const yTitleWidth = plot.y_title ? labelSize(plot.y_title, null, TITLE_SCALE).width : 0;
  const side = plot.y_title ? titleSide(axisX, yTitleWidth, W) : null;
  const top = frameTop(side, yAt.arrow);
  const t = (xAt.at - y0) / (y1 - y0); // where the horizontal axis sits, 0 = bottom edge
  let bottom: number;
  let height: number;
  if (plot.orthonormal) {
    bottom = top + unit * (y1 - y0);
    const axisY = bottom - t * (bottom - top);
    height = Math.ceil(Math.max(bottom + MIN_BOTTOM, t < 1 ? axisY + X_LABEL_BOTTOM : 0));
  } else {
    height = baseH;
    // axisY = (1 − t)(H − m) + top·t must leave X_LABEL_BOTTOM under it.
    const m =
      t < 1
        ? Math.max(MIN_BOTTOM, height - (height - X_LABEL_BOTTOM - top * t) / (1 - t))
        : MIN_BOTTOM;
    bottom = height - m;
  }
  const frame: Frame = { left: frameLeft, right: frameRight, top, bottom: r1(bottom) };
  const sy = linear([y0, y1], [frame.bottom, frame.top]);
  const py = (y: number) => r1(sy(y));
  const axisY = py(xAt.at);
  const plotW = frame.right - frame.left;
  const plotH = frame.bottom - frame.top;

  // What is drawn: curves, sequences, lines, points.
  const colours = colourGroups(plot);
  const occupancy = new Occupancy(W, height + BAND);
  const runs: Scene["runs"] = [];
  const groupVertices: [number, number][][] = colours.groups.map(() => []);
  const groupDots: [number, number][][] = colours.groups.map(() => []);
  const legend: Legend[] = colours.groups.map((g) => ({
    label: g.label,
    curves: 0,
    sequences: 0,
    lines: 0,
  }));
  const dashedVertices: { label: string | null; vertices: [number, number][] }[] = [];
  const endpoints: Scene["endpoints"] = [];
  const toPx = (run: Run): [number, number][] => run.map(([x, y]) => [px(x), py(y)]);
  const draw = (visible: [number, number][][], group: number | null, label: string | null) => {
    const colour = colourOf(colours, group);
    for (const run of visible) {
      runs.push({
        points: run.map(([x, y]) => `${x},${y}`).join(" "),
        colour,
        dashed: group === null,
      });
      occupancy.markPath(run);
    }
    const flat = visible.flat();
    if (group === null) {
      if (flat.length > 0) dashedVertices.push({ label, vertices: flat });
    } else groupVertices[group]?.push(...flat);
    return flat.length > 0;
  };

  plot.curves.forEach((curve, i) => {
    const group = colours.curve[i] ?? null;
    const from = curve.domain?.[0] ?? x0;
    const to = curve.domain?.[1] ?? x1;
    const { runs: sampled } = sampleCurve(curve.f, from, to, win, plotW, plotH);
    const visible = draw(sampled.map(toPx), group, curve.label);
    const entry = group === null ? undefined : legend[group];
    if (visible && entry) entry.curves += 1;
    if (!(to > from)) return;
    const colour = colourOf(colours, group);
    for (const [bound, inward, dot] of [
      [from, 1, curve.start_dot],
      [to, -1, curve.end_dot],
    ] as const) {
      const y = endpointValue(curve.f, bound, inward, to - from, dot);
      if (y === null || bound < x0 || bound > x1 || y < y0 || y > y1) continue;
      endpoints.push({ x: px(bound), y: py(y), colour, hollow: dot === "hollow" });
    }
  });

  const dots: Scene["dots"] = [];
  plot.sequences.forEach((seq, i) => {
    const group = colours.sequence[i] ?? 0;
    const colour = colourOf(colours, group);
    const terms = sequenceDots(seq.f, seq.first, seq.last, win).map(([n, u]): [number, number] => [
      px(n),
      py(u),
    ]);
    for (const [x, y] of terms) dots.push({ x, y, colour });
    const entry = legend[group];
    if (terms.length > 0 && entry) entry.sequences += 1;
    const last = terms.at(-1);
    const first = terms[0];
    if (last) groupDots[group]?.push(last);
    if (first && first !== last) groupDots[group]?.push(first);
  });

  plot.lines.forEach((line, i) => {
    const group = colours.line[i] ?? null;
    const visible = draw(clipLine(line.vertices, win).map(toPx), group, line.label);
    const entry = group === null ? undefined : legend[group];
    if (visible && entry) entry.lines += 1;
  });

  const marks: Scene["marks"] = [];
  const guides: Scene["guides"] = [];
  const feet: Scene["feet"] = [];
  const footBoxes: Box[] = [];
  const shownPoints: number[] = [];
  plot.points.forEach((p, i) => {
    if (p.x < x0 || p.x > x1 || p.y < y0 || p.y > y1) return;
    shownPoints.push(i);
    const x = px(p.x);
    const y = py(p.y);
    marks.push({ x, y, mark: p.mark });
    if (!p.guides) return;
    guides.push({ x1: x, y1: y, x2: x, y2: axisY }, { x1: x, y1: y, x2: axisX, y2: y });
    if (!p.show_values) return;
    const fx = notation.number(p.x);
    const fy = notation.number(p.y);
    feet.push({ x, y: axisY + X_LABEL_DY, text: fx, anchor: "middle" });
    feet.push({ x: axisX - TICK_GAP, y, text: fy, anchor: "end" });
    footBoxes.push(
      { left: x - tickWidth(p.x) / 2, top: axisY + 5, width: tickWidth(p.x), height: 14 },
      { left: axisX - TICK_GAP - tickWidth(p.y), top: y - 7, width: tickWidth(p.y), height: 14 },
    );
  });

  // Graduations: a mark at every tick, a label on every k-th, anchored at 0.
  const origin = xAt.arrow && yAt.arrow ? { x: axisX - TICK_GAP, y: axisY + X_LABEL_DY } : null;
  const originBox: Box | null = origin && {
    left: origin.x - tickWidth(0),
    top: axisY + 5,
    width: tickWidth(0),
    height: 14,
  };
  const everyX = labelEvery(
    xStep,
    plotW / ((x1 - x0) / xStep),
    Math.max(0, ...xValues.map(tickWidth)) + 6,
  );
  const everyY = labelEvery(yStep, plotH / ((y1 - y0) / yStep), 16);
  const clear = (box: Box) =>
    !footBoxes.some((f) => overlaps(box, f, 4)) && !(originBox && overlaps(box, originBox, 2));
  const tol = (a: number, b: number) => 1e-9 * (b - a);

  // A label on the other axis's line (a corner, or where an axis sits inside the
  // frame) moves off it, if the ticks leave room to tell whose label it is;
  // otherwise it is dropped. Each axis places its plain labels, then that one.
  const yBoxes: Box[] = [];
  const yInk: Box[] = [];
  const ySpacing = (plotH * yStep) / (y1 - y0);
  const yNudge = xAt.at === y1 ? DROP : -LIFT; // toward the inside of the frame
  const yOnLine = (v: number) => s > 0 && Math.abs(v - xAt.at) < tol(y0, y1);
  const yTry = (v: number, shift: number): boolean => {
    const c = py(v) + shift;
    const w = tickWidth(v);
    const box = { left: axisX - TICK_GAP - w, top: c - TICK_HALF, width: w, height: 14 };
    const ink = { left: box.left, top: c - Y_INK_TOP, width: w, height: INK_HEIGHT };
    if (!clear(box) || yInk.some((b) => overlaps(ink, b))) return false;
    yBoxes.push(box);
    yInk.push(ink);
    return true;
  };
  const yShift = new Map<number, number>();
  const yLabelled = yValues.filter((v) => labelled(v, yStep, everyY) && !(origin && v === 0));
  for (const v of yLabelled) if (!yOnLine(v) && yTry(v, 0)) yShift.set(v, 0);
  for (const v of yLabelled) {
    if (yOnLine(v) && ySpacing >= 3 * Math.abs(yNudge) && yTry(v, yNudge)) yShift.set(v, yNudge);
  }
  const yTicks: Tick[] = yValues.map((v) => {
    const shift = yShift.get(v);
    return {
      px: py(v),
      value: v,
      label: shift === undefined ? null : notation.number(v),
      shift: shift ?? 0,
    };
  });

  // The x labels give way to the y labels: their ink may not touch.
  const xBoxes: Box[] = [];
  const xSpacing = (plotW * xStep) / (x1 - x0);
  const xSide = yAt.at === x1 ? -1 : 1; // toward the inside of the frame
  const xOnLine = (v: number) => t > 0 && Math.abs(v - yAt.at) < tol(x0, x1);
  const xTry = (v: number, shift: number): boolean => {
    const c = px(v) + shift;
    const w = tickWidth(v);
    const box = { left: c - w / 2, top: axisY + 5, width: w, height: 14 };
    const ink = { ...box, top: axisY + X_INK_TOP, height: INK_HEIGHT };
    if (
      !clear(box) ||
      yInk.some((b) => overlaps(ink, b)) ||
      xBoxes.some((b) => overlaps(box, b, 4))
    )
      return false;
    xBoxes.push(box);
    return true;
  };
  const xShift = new Map<number, number>();
  const xLabelled = xValues.filter((v) => labelled(v, xStep, everyX) && !(origin && v === 0));
  for (const v of xLabelled) if (!xOnLine(v) && xTry(v, 0)) xShift.set(v, 0);
  for (const v of xLabelled) {
    const w = tickWidth(v);
    const shift = xSide * (w / 2 + SIDESTEP);
    if (xOnLine(v) && xSpacing >= w + 3 * SIDESTEP && xTry(v, shift)) xShift.set(v, shift);
  }
  const xTicks: Tick[] = xValues.map((v) => {
    const shift = xShift.get(v);
    return {
      px: px(v),
      value: v,
      label: shift === undefined ? null : notation.number(v),
      shift: shift ?? 0,
    };
  });

  const xAxis: Axis = {
    pos: axisY,
    from: frame.left,
    to: frame.right + (xAt.arrow ? ARROW : 0),
    arrow: xAt.arrow,
    step: xStep,
    ticks: xTicks,
  };
  const yAxis: Axis = {
    pos: axisX,
    from: frame.bottom,
    to: frame.top - (yAt.arrow ? ARROW : 0),
    arrow: yAt.arrow,
    step: yStep,
    ticks: yTicks,
  };
  occupancy.markPath([
    [xAxis.from, axisY],
    [xAxis.to, axisY],
  ]);
  occupancy.markPath([
    [axisX, yAxis.from],
    [axisX, yAxis.to],
  ]);
  if (xAxis.arrow) occupancy.markBox({ left: xAxis.to - 7, top: axisY - 4, width: 7, height: 8 });
  if (yAxis.arrow) occupancy.markBox({ left: axisX - 4, top: yAxis.to, width: 8, height: 7 });
  for (const box of [...xBoxes, ...yBoxes, ...footBoxes, ...(originBox ? [originBox] : [])]) {
    occupancy.markBox(box);
  }
  for (const d of dots) occupancy.markBox({ left: d.x - 4, top: d.y - 4, width: 8, height: 8 });
  for (const e of endpoints)
    occupancy.markBox({ left: e.x - 5, top: e.y - 5, width: 10, height: 10 });
  for (const m of marks) occupancy.markBox({ left: m.x - 5, top: m.y - 5, width: 10, height: 10 });
  for (const g of guides) {
    occupancy.markPath([
      [g.x1, g.y1],
      [g.x2, g.y2],
    ]);
  }

  // Titles. The y title in the band over the plot, beside the arrow (pass 3 made
  // room for it). The x title at the arrow's tip, over the axis, when nothing is
  // drawn there; otherwise in a band under the plot.
  const taken: Box[] = [];
  let yTitle: TextBox | null = null;
  if (plot.y_title && side) {
    yTitle = titleBox(plot.y_title, yTitleWidth, side, axisX, W);
    taken.push(yTitle);
    occupancy.markBox(yTitle);
  }
  let xTitle: TextBox | null = null;
  let xTitleBelow = false;
  if (plot.x_title) {
    const { width } = labelSize(plot.x_title, null, TITLE_SCALE);
    const atTip: TextBox = {
      left: xAxis.to - width,
      top: axisY - TITLE_GAP - LABEL_HEIGHT,
      width,
      height: LABEL_HEIGHT,
      align: "right",
      text: plot.x_title,
    };
    const onTop = xAt.at === y1;
    if (
      !onTop &&
      atTip.left >= 0 &&
      atTip.top >= 0 &&
      occupancy.free(atTip) &&
      !taken.some((b) => overlaps(atTip, b))
    ) {
      xTitle = atTip;
    } else {
      xTitleBelow = true;
      xTitle = {
        left: Math.max(0, frame.right - width),
        top: height + 1,
        width: Math.min(width, W),
        height: LABEL_HEIGHT,
        align: "right",
        text: plot.x_title,
      };
      height += BAND;
    }
    taken.push(xTitle);
    occupancy.markBox(xTitle);
  }

  // Labels: points first, then one per labelled colour group, then dashed layers.
  const requests: LabelRequest[] = [];
  const entries: Omit<PlotLabel, keyof Anchored>[] = [];
  for (const i of shownPoints) {
    const p = plot.points[i];
    if (!p) continue;
    const coords = p.show_values && !p.guides ? notation.pair(p.x, p.y) : null;
    if (!p.label && !coords) continue;
    const size = labelSize(p.label ?? "", coords);
    requests.push({ candidates: [[px(p.x), py(p.y)]], ...size });
    entries.push({ text: p.label, coords, colour: null, dashed: false });
  }
  const along = (vertices: [number, number][], extra: [number, number][] = []) => {
    const sorted = [...vertices].sort((a, b) => a[0] - b[0]);
    const picked = sorted.length
      ? LABEL_FRACTIONS.map(
          (f) =>
            sorted[Math.min(sorted.length - 1, Math.floor(f * sorted.length))] as [number, number],
        )
      : [];
    return [...picked, ...extra];
  };
  colours.groups.forEach((g, i) => {
    if (!g.label) return;
    const candidates = along(groupVertices[i] ?? [], groupDots[i] ?? []);
    if (candidates.length === 0) return;
    requests.push({ candidates, ...labelSize(g.label) });
    entries.push({ text: g.label, coords: null, colour: g.colour, dashed: false });
  });
  for (const d of dashedVertices) {
    if (!d.label) continue;
    requests.push({ candidates: along(d.vertices), ...labelSize(d.label) });
    entries.push({ text: d.label, coords: null, colour: colourOf(colours, null), dashed: true });
  }
  const boxes = placeLabels(requests, { width: W, height }, occupancy, taken);
  const labels: PlotLabel[] = boxes.map((box, i) => ({
    ...box,
    ...(entries[i] as Omit<PlotLabel, keyof Anchored>),
  }));

  return {
    width: W,
    height,
    frame,
    win,
    xAxis,
    yAxis,
    origin,
    grid: plot.grid,
    runs,
    dots,
    endpoints,
    marks,
    guides,
    feet,
    xTitle,
    yTitle,
    xTitleBelow,
    labels,
    legend: legend.filter((l) => l.curves + l.sequences + l.lines > 0),
    dashed: dashedVertices.map((d) => d.label),
    points: shownPoints,
    drawable: runs.length + dots.length + marks.length + endpoints.length > 0,
  };
}
