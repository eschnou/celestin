import { flowRows, GAP_PX, spreadRow, textPx, type Dir } from "./labels";
import { zoneKey, type CleanSets, type Pt } from "./sanitise";

/**
 * Diagrams of sets, laid out by their content. Overlapping and separate sets
 * have fixed zone slots (rectangles proven to lie in exactly their zone); nested
 * sets are rounded rectangles offset to the lower left, each ring with a label
 * band and a right-hand band as wide as its widest element.
 *
 * The layout is built at the smallest board's drawing (294 px, a 400 px board)
 * and only grows from there, so what `fits` accepts at 294 px fits everywhere.
 * `fits` makes the same decision as the tool's `crowded` rule, on the same
 * numbers: both sides read `__tests__/capacity.json`.
 */

export const BOARD_PX = 294;
export const MAX_LAYOUT_PX = 400;
export const MARGIN_PX = 14;
export const ROW_PX = 18;
export const MAX_PER_ZONE = 6;
/** The row above the diagram that holds the set names, and a nested ring's label band. */
export const LABEL_ROW = 20;
export const NESTED = {
  label_row: LABEL_ROW,
  gap: GAP_PX,
  band_min: 20,
  band_pad: 12,
  inner_min: 40,
  label_pad: 16,
} as const;

/** Each zone's capacity at 294 px: its width in px and its rows. Keys: the zone's set indices. */
export const SLOTS: Record<string, Record<string, [number, number]>> = {
  overlap2: { "0": [70, 4], "1": [70, 4], "01": [70, 4] },
  overlap3: {
    "0": [77, 2],
    "1": [77, 2],
    "2": [141, 2],
    "01": [53, 2],
    "02": [46, 2],
    "12": [46, 2],
    "012": [70, 2],
  },
  separate2: { "0": [84, 5], "1": [84, 5] },
  separate3: { "0": [54, 3], "1": [54, 3], "2": [54, 3] },
  outside: { "": [260, 2] },
};

/** A slot in unit space: its centre and half-sizes. */
export type UnitSlot = { c: Pt; hw: number; hh: number };
/** Overlapping or separate sets in unit space (y up): each set, and the zone slots. */
export type UnitDiagram = {
  centres: Pt[];
  rx: number;
  ry: number;
  /** Horizontal extent, and the top and bottom of the shapes. */
  width: number;
  top: number;
  bottom: number;
  slots: Record<string, UnitSlot>;
};

const OVERLAP3_D = 0.58;
const polar = (deg: number): Pt => [
  OVERLAP3_D * Math.cos((deg * Math.PI) / 180),
  OVERLAP3_D * Math.sin((deg * Math.PI) / 180),
];

/** Unit circles and their slots; each slot was sampled to lie in exactly its zone. */
export function unitDiagram(layout: "overlap" | "separate", n: number): UnitDiagram {
  if (layout === "overlap" && n === 2) {
    const hh = 0.41;
    return {
      centres: [
        [-0.5, 0],
        [0.5, 0],
      ],
      rx: 1,
      ry: 1,
      width: 3,
      top: 1,
      bottom: -1,
      slots: {
        "0": { c: [-1, 0], hw: 0.4, hh },
        "1": { c: [1, 0], hw: 0.4, hh },
        "01": { c: [0, 0], hw: 0.4, hh },
      },
    };
  }
  if (layout === "overlap") {
    const centres = [polar(150), polar(30), polar(270)];
    const half = OVERLAP3_D * Math.cos(Math.PI / 6) + 1;
    const hh = 0.205;
    return {
      centres,
      rx: 1,
      ry: 1,
      width: 2 * half,
      top: OVERLAP3_D * 0.5 + 1,
      bottom: -OVERLAP3_D - 1,
      slots: {
        "0": { c: [-0.95, 0.52], hw: 0.44, hh },
        "1": { c: [0.95, 0.52], hw: 0.44, hh },
        "2": { c: [0, -0.94], hw: 0.8, hh },
        "01": { c: [0, 0.64], hw: 0.3, hh },
        "02": { c: [-0.65, -0.4], hw: 0.26, hh },
        "12": { c: [0.65, -0.4], hw: 0.26, hh },
        "012": { c: [0, 0.1], hw: 0.4, hh },
      },
    };
  }
  const centres: Pt[] = Array.from({ length: n }, (_, i) => [(i - (n - 1) / 2) * 2.3, 0]);
  return {
    centres,
    rx: 1,
    ry: 1.25,
    width: 2 * n + 0.3 * (n - 1),
    top: 1.25,
    bottom: -1.25,
    slots: Object.fromEntries(centres.map((c, i) => [String(i), { c, hw: 0.68, hh: 0.85 }])),
  };
}

export type Rect = { x0: number; y0: number; x1: number; y1: number };
export type SetShape =
  | { kind: "ellipse"; cx: number; cy: number; rx: number; ry: number }
  | { kind: "rect"; x0: number; y0: number; x1: number; y1: number; r: number };

export type SetLabel = { key: string; x: number; y: number; dir: Dir; text: string; set: number };
export type ZoneBox = { key: string; rect: Rect; items: string[]; column: boolean };

export type SetsLayout = {
  /** The layout's own width (294 to 400 px) and height. */
  width: number;
  height: number;
  shapes: SetShape[];
  labels: SetLabel[];
  zones: ZoneBox[];
  universe: Rect | null;
  universeLabel: { x: number; y: number } | null;
};

const itemsIn = (fig: CleanSets, key: string) =>
  fig.elements.filter((e) => zoneKey(e.zone) === key).map((e) => e.text);

/** The layout width for a board drawing of W px. */
export const layoutWidth = (W: number) => Math.min(MAX_LAYOUT_PX, Math.max(BOARD_PX, W));

function fixedLayout(
  fig: CleanSets,
  L: number,
  top: number,
): Omit<SetsLayout, "universe" | "universeLabel"> & { bottom: number } {
  const n = fig.sets.length;
  const layout = fig.layout === "separate" ? "separate" : "overlap";
  const unit = unitDiagram(layout, n);
  const s = (L - 2 * MARGIN_PX) / unit.width;
  const shapesTop = top + LABEL_ROW;
  const px = ([x, y]: Pt): Pt => [L / 2 + x * s, shapesTop + (unit.top - y) * s];
  const shapes: SetShape[] = unit.centres.map((c) => {
    const [cx, cy] = px(c);
    return { kind: "ellipse", cx, cy, rx: unit.rx * s, ry: unit.ry * s };
  });
  // Set names in the row above; a third overlapping set's name goes below it.
  const above = layout === "overlap" && n === 3 ? [0, 1] : fig.sets.map((_, i) => i);
  const widths = above.map((i) => textPx(fig.sets[i]?.label ?? ""));
  const centres = spreadRow(
    above.map((i, k) => ({
      centre: shapes[i]?.kind === "ellipse" ? shapes[i].cx : L / 2,
      width: widths[k] ?? 0,
    })),
    MARGIN_PX,
    L - MARGIN_PX,
    2 * GAP_PX,
  );
  const labels: SetLabel[] = above.map((i, k) => ({
    key: `s${i}`,
    x: centres[k] ?? L / 2,
    y: top + LABEL_ROW / 2,
    dir: [0, 0],
    text: fig.sets[i]?.label ?? "",
    set: i,
  }));
  let bottom = shapesTop + (unit.top - unit.bottom) * s;
  if (layout === "overlap" && n === 3) {
    const c = shapes[2];
    labels.push({
      key: "s2",
      x: c?.kind === "ellipse" ? c.cx : L / 2,
      y: bottom + LABEL_ROW / 2,
      dir: [0, 0],
      text: fig.sets[2]?.label ?? "",
      set: 2,
    });
    bottom += LABEL_ROW;
  }
  const zones: ZoneBox[] = Object.entries(unit.slots).map(([key, slot]) => {
    const [cx, cy] = px(slot.c);
    return {
      key,
      rect: {
        x0: cx - slot.hw * s,
        y0: cy - slot.hh * s,
        x1: cx + slot.hw * s,
        y1: cy + slot.hh * s,
      },
      items: itemsIn(fig, key),
      column: false,
    };
  });
  return {
    width: L,
    height: 0,
    shapes,
    labels,
    zones: zones.filter((z) => z.items.length),
    bottom,
  };
}

/** The rings' right-hand bands: as wide as their widest element, 20 px at least. */
export function nestedBands(fig: CleanSets): number[] {
  const n = fig.sets.length;
  return Array.from({ length: Math.max(0, n - 1) }, (_, i) =>
    Math.max(
      NESTED.band_min,
      Math.max(0, ...itemsIn(fig, String(i)).map(textPx)) + NESTED.band_pad,
    ),
  );
}

function nestedLayout(
  fig: CleanSets,
  L: number,
  top: number,
): Omit<SetsLayout, "universe" | "universeLabel"> & { bottom: number } {
  const n = fig.sets.length;
  const LH = LABEL_ROW;
  const G = NESTED.gap;
  const bands = nestedBands(fig);
  const rects: Rect[] = [{ x0: MARGIN_PX, y0: top, x1: L - MARGIN_PX, y1: 0 }];
  for (let i = 1; i < n; i += 1) {
    const prev = rects[i - 1] as Rect;
    rects.push({
      x0: prev.x0 + G,
      x1: prev.x1 - (bands[i - 1] ?? NESTED.band_min),
      y0: prev.y0 + LH,
      y1: 0,
    });
  }
  const inner = rects[n - 1] as Rect;
  const innerWidth = Math.max(0, inner.x1 - inner.x0);
  const innerRows =
    flowRows(itemsIn(fig, String(n - 1)).map(textPx), Math.max(1, innerWidth - 12)) ?? 1;
  let innerHeight = Math.max(
    NESTED.inner_min,
    LH + innerRows * ROW_PX + 8,
    ...bands.map((_, i) => itemsIn(fig, String(i)).length * ROW_PX + 8 - (n - 2 - i) * (LH + G)),
  );
  const content = (n - 1) * (LH + G) + innerHeight;
  const least = Math.round(0.45 * L) - 2 * MARGIN_PX;
  if (least > content) innerHeight += least - content;
  // Bottoms, from the innermost out: each ring ends G below the one inside it.
  const bottom0 = top + (n - 1) * (LH + G) + innerHeight;
  rects.forEach((r, i) => {
    r.y1 = bottom0 - i * G;
  });
  const radius = (r: Rect) => Math.min(14, 0.25 * Math.min(r.x1 - r.x0, r.y1 - r.y0));
  const shapes: SetShape[] = rects.map((r) => ({ kind: "rect", ...r, r: radius(r) }));
  const labels: SetLabel[] = rects.map((r, i) => ({
    key: `s${i}`,
    x: r.x0 + 10,
    y: r.y0 + LH / 2,
    dir: [1, 0],
    text: fig.sets[i]?.label ?? "",
    set: i,
  }));
  const zones: ZoneBox[] = rects.map((r, i) => {
    const next = rects[i + 1];
    const key = String(i);
    const rect = next
      ? { x0: next.x1, y0: next.y0, x1: r.x1, y1: r.y1 - radius(r) }
      : { x0: r.x0 + 6, y0: r.y0 + LH, x1: r.x1 - 6, y1: r.y1 - 4 };
    return { key, rect, items: itemsIn(fig, key), column: next !== undefined };
  });
  return {
    width: L,
    height: 0,
    shapes,
    labels,
    zones: zones.filter((z) => z.items.length),
    bottom: bottom0,
  };
}

/** The whole diagram at layout width L (294 to 400 px). */
export function setsLayout(fig: CleanSets, L: number): SetsLayout {
  const top = MARGIN_PX + (fig.universe ? LABEL_ROW : 0);
  const base = fig.layout === "nested" ? nestedLayout(fig, L, top) : fixedLayout(fig, L, top);
  const outside = itemsIn(fig, "");
  const [slot] = SLOTS["outside"]?.[""] ?? [260, 2];
  let bottom = base.bottom;
  const zones = [...base.zones];
  if (outside.length) {
    const left = (L - slot) / 2;
    zones.push({
      key: "",
      rect: { x0: left, y0: bottom + 6, x1: left + slot, y1: bottom + 6 + 2 * ROW_PX },
      items: outside,
      column: false,
    });
    bottom += 6 + 2 * ROW_PX;
  }
  const height = Math.round(bottom + MARGIN_PX);
  return {
    width: L,
    height,
    shapes: base.shapes,
    labels: base.labels,
    zones,
    universe: fig.universe ? { x0: 2, y0: 2, x1: L - 2, y1: height - 2 } : null,
    universeLabel: fig.universe ? { x: 10, y: 2 + LABEL_ROW / 2 } : null,
  };
}

/**
 * Whether the diagram fits the smallest board: the same decision, on the same
 * numbers, as the tool's `crowded` rule (`figures.py`, `_fits`).
 */
export function fits(fig: CleanSets): boolean {
  const n = fig.sets.length;
  const width = BOARD_PX - 2 * MARGIN_PX;
  const byZone = new Map<string, number[]>();
  for (const e of fig.elements) {
    const key = zoneKey(e.zone);
    byZone.set(key, [...(byZone.get(key) ?? []), textPx(e.text)]);
  }
  for (const widths of byZone.values()) if (widths.length > MAX_PER_ZONE) return false;
  if (fig.universe !== null && textPx(fig.universe) > width) return false;
  const holds = (widths: number[] | undefined, capacity: [number, number] | undefined) => {
    if (!widths) return true;
    if (!capacity) return false;
    const rows = flowRows(widths, capacity[0]);
    return rows !== null && rows <= capacity[1];
  };
  if (!holds(byZone.get(""), SLOTS["outside"]?.[""])) return false;
  const labels = fig.sets.map((s) => textPx(s.label));
  const widest = (key: string) => Math.max(0, ...(byZone.get(key) ?? [0]));
  if (fig.layout === "nested") {
    const bands = Array.from({ length: n - 1 }, (_, i) =>
      Math.max(NESTED.band_min, widest(String(i)) + NESTED.band_pad),
    );
    const inner = Math.max(
      (labels[n - 1] ?? 0) + NESTED.label_pad,
      widest(String(n - 1)) + NESTED.band_pad,
      NESTED.inner_min,
    );
    const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);
    if (sum(bands) + (n - 1) * NESTED.gap + inner > width) return false;
    return labels.every(
      (label, i) => label + NESTED.label_pad <= width - sum(bands.slice(0, i)) - i * NESTED.gap,
    );
  }
  const top = n === 3 && fig.layout === "overlap" ? labels.slice(0, 2) : labels;
  const rowWidth = top.reduce((a, b) => a + b, 0) + 2 * GAP_PX * (top.length - 1);
  if (rowWidth > width || Math.max(...labels) > width) return false;
  const slots = SLOTS[`${fig.layout}${n}`];
  for (const [key, widths] of byZone) {
    if (key === "") continue;
    if (!holds(widths, slots?.[key])) return false;
  }
  return true;
}

const f2 = (v: number) => Math.round(v * 100) / 100;

/** A set's outline as one path (so it can trace): an ellipse, or a rounded rectangle. */
export function shapePath(shape: SetShape): string {
  if (shape.kind === "ellipse") {
    const { cx, cy, rx, ry } = shape;
    if (!(rx > 0 && ry > 0)) return "";
    return `M ${f2(cx - rx)} ${f2(cy)} A ${f2(rx)} ${f2(ry)} 0 1 0 ${f2(cx + rx)} ${f2(cy)} A ${f2(rx)} ${f2(ry)} 0 1 0 ${f2(cx - rx)} ${f2(cy)}`;
  }
  const { x0, y0, x1, y1 } = shape;
  const r = Math.max(0, Math.min(shape.r, (x1 - x0) / 2, (y1 - y0) / 2));
  if (!(x1 > x0 && y1 > y0)) return "";
  return [
    `M ${f2(x0 + r)} ${f2(y0)}`,
    `H ${f2(x1 - r)}`,
    `A ${f2(r)} ${f2(r)} 0 0 1 ${f2(x1)} ${f2(y0 + r)}`,
    `V ${f2(y1 - r)}`,
    `A ${f2(r)} ${f2(r)} 0 0 1 ${f2(x1 - r)} ${f2(y1)}`,
    `H ${f2(x0 + r)}`,
    `A ${f2(r)} ${f2(r)} 0 0 1 ${f2(x0)} ${f2(y1 - r)}`,
    `V ${f2(y0 + r)}`,
    `A ${f2(r)} ${f2(r)} 0 0 1 ${f2(x0 + r)} ${f2(y0)}`,
    "Z",
  ].join(" ");
}

/**
 * How a hatched zone is cut out: the sets it lies in (each a clip), and the sets
 * it must leave out (masked). `-1` stands for the universe's frame.
 */
export function zoneCut(fig: CleanSets, zone: number[]): { inside: number[]; outside: number[] } {
  const all = fig.sets.map((_, i) => i);
  if (zone.length === 0) return { inside: [-1], outside: fig.layout === "nested" ? [0] : all };
  if (fig.layout === "nested") {
    const [i = 0] = zone;
    return { inside: [i], outside: i + 1 < fig.sets.length ? [i + 1] : [] };
  }
  if (fig.layout === "separate") return { inside: zone, outside: [] };
  return { inside: zone, outside: all.filter((i) => !zone.includes(i)) };
}
