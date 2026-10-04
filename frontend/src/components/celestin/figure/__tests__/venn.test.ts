import { describe, expect, it } from "vitest";
import { flowRows, textPx } from "../labels";
import { sanitise, type CleanSets, type Pt } from "../sanitise";
import {
  BOARD_PX,
  layoutWidth,
  MARGIN_PX,
  MAX_PER_ZONE,
  NESTED as NESTED_BANDS,
  ROW_PX,
  fits,
  setsLayout,
  SLOTS,
  unitDiagram,
  type Rect,
} from "../venn";
import capacity from "./capacity.json";
import { NESTED, SETS, STATS } from "./fixtures";

/** `capacity.json` is copied verbatim from `backend/tests/fixtures/figure/`; a backend test keeps both identical. */

const sets = (figure: object): CleanSets => {
  const fig = sanitise(figure);
  if (fig?.kind !== "sets") throw new Error("not sets");
  return fig;
};

describe("the shared capacity table", () => {
  it("holds this module's numbers", () => {
    expect(capacity.constants).toMatchObject({
      BOARD_PX,
      MARGIN_PX,
      ROW_PX,
      MAX_PER_ZONE,
    });
    expect(capacity.nested).toEqual(NESTED_BANDS);
    expect(capacity.slots).toEqual(SLOTS);
  });

  it.each(capacity.cases)(
    "$name: fits is $fits, as the tool decides",
    ({ figure, fits: expected }) => {
      expect(fits(sets(figure))).toBe(expected);
    },
  );
});

/** Which unit shapes a point lies in. */
function zoneAt([x, y]: Pt, centres: Pt[], rx: number, ry: number): string {
  return centres
    .map((c, i) => (((x - c[0]) / rx) ** 2 + ((y - c[1]) / ry) ** 2 < 1 ? String(i) : ""))
    .join("");
}

describe.each([
  ["overlap", 2],
  ["overlap", 3],
  ["separate", 2],
  ["separate", 3],
] as const)("%s diagram of %i sets", (layout, n) => {
  const unit = unitDiagram(layout, n);
  const s = (BOARD_PX - 2 * MARGIN_PX) / unit.width;
  const table = SLOTS[`${layout}${n}`] ?? {};

  it.each(Object.entries(unit.slots))("slot %s lies in exactly its zone", (key, slot) => {
    const samples = 81;
    for (let i = 0; i < samples; i += 1) {
      const t = -1 + (2 * i) / (samples - 1);
      const { c, hw, hh } = slot;
      const edge: Pt[] = [
        [c[0] + t * hw, c[1] - hh],
        [c[0] + t * hw, c[1] + hh],
        [c[0] - hw, c[1] + t * hh],
        [c[0] + hw, c[1] + t * hh],
      ];
      for (const p of edge) expect(zoneAt(p, unit.centres, unit.rx, unit.ry)).toBe(key);
    }
  });

  it.each(Object.entries(unit.slots))(
    "slot %s holds the table's capacity at 294 px",
    (key, slot) => {
      const [width = 0, rows = 0] = table[key] ?? [];
      expect(2 * slot.hw * s).toBeGreaterThanOrEqual(width);
      expect(Math.floor((2 * slot.hh * s) / ROW_PX)).toBeGreaterThanOrEqual(rows);
    },
  );

  it("has a slot for every zone the table names", () => {
    expect(Object.keys(unit.slots).sort()).toEqual(Object.keys(table).sort());
  });
});

describe("separate sets", () => {
  it("never touch one another", () => {
    for (const n of [2, 3]) {
      const unit = unitDiagram("separate", n);
      const [a, b] = unit.centres;
      expect((b?.[0] ?? 0) - (a?.[0] ?? 0)).toBeGreaterThan(2 * unit.rx);
    }
  });
});

const within = (inner: Rect, outer: Rect) =>
  inner.x0 >= outer.x0 - 1e-9 &&
  inner.y0 >= outer.y0 - 1e-9 &&
  inner.x1 <= outer.x1 + 1e-9 &&
  inner.y1 <= outer.y1 + 1e-9;

describe("nested sets", () => {
  const rectOf = (shape: unknown): Rect => shape as Rect;

  it.each([1, 2, 3, 4, 5])("with %i levels, each set lies inside the one before", (n) => {
    const fig = sets({ ...NESTED, sets: NESTED.sets.slice(0, n), elements: [] });
    const layout = setsLayout(fig, BOARD_PX);
    layout.shapes.forEach((shape, i) => {
      expect(shape.kind).toBe("rect");
      const prev = layout.shapes[i - 1];
      if (prev) expect(within(rectOf(shape), rectOf(prev))).toBe(true);
    });
  });

  it("holds ℕ ⊂ ℤ ⊂ 𝔻 ⊂ ℚ ⊂ ℝ, each ring's elements in its band", () => {
    const fig = sets(NESTED);
    expect(fits(fig)).toBe(true);
    const layout = setsLayout(fig, BOARD_PX);
    expect(layout.height).toBe(178);
    for (const zone of layout.zones) {
      const width = zone.rect.x1 - zone.rect.x0;
      const height = zone.rect.y1 - zone.rect.y0;
      const widths = zone.items.map(textPx);
      expect(Math.max(...widths)).toBeLessThanOrEqual(width);
      const rows = zone.column ? zone.items.length : (flowRows(widths, width) ?? Infinity);
      expect(rows * ROW_PX).toBeLessThanOrEqual(height + 1e-9);
    }
    // 7 is listed in every set and lands in ℕ, the innermost.
    expect(layout.zones.find((z) => z.key === "4")?.items).toEqual(["0", "7"]);
  });

  it("gives each ring a 20 px label band", () => {
    const layout = setsLayout(sets(STATS), BOARD_PX);
    const [outer, inner] = layout.shapes.map(rectOf);
    expect((inner?.y0 ?? 0) - (outer?.y0 ?? 0)).toBe(20);
    expect(layout.labels.map((l) => l.text)).toEqual(["Population", "Échantillon"]);
  });
});

describe("the whole diagram", () => {
  it("fits the divisors of 12 and 18 at 294 px", () => {
    const fig = sets(SETS);
    expect(fits(fig)).toBe(true);
    const layout = setsLayout(fig, BOARD_PX);
    expect(Math.round(layout.height)).toBe(225);
    // Both names in the row above, apart and inside the drawing.
    const [a, b] = layout.labels;
    expect((b?.x ?? 0) - (a?.x ?? 0)).toBeGreaterThanOrEqual(105 + 12 - 1e-9);
    expect((a?.x ?? 0) - 52.5).toBeGreaterThanOrEqual(MARGIN_PX - 1e-9);
    expect((b?.x ?? 0) + 52.5).toBeLessThanOrEqual(BOARD_PX - MARGIN_PX + 1e-9);
  });

  it("puts what lies outside every set in a strip inside the universe, below the sets", () => {
    const fig = sets({ ...SETS, universe: "Nombres", elements: [{ text: "5", within: [] }] });
    const layout = setsLayout(fig, BOARD_PX);
    const strip = layout.zones.find((z) => z.key === "");
    if (!strip || !layout.universe) throw new Error("strip and universe expected");
    expect(within(strip.rect, layout.universe)).toBe(true);
    for (const shape of layout.shapes) {
      if (shape.kind === "ellipse")
        expect(strip.rect.y0).toBeGreaterThanOrEqual(shape.cy + shape.ry);
    }
  });

  it("is laid out at 294 px below that width, and grows up to 400 px", () => {
    expect(layoutWidth(250)).toBe(294);
    expect(layoutWidth(350)).toBe(350);
    expect(layoutWidth(900)).toBe(400);
  });
});
