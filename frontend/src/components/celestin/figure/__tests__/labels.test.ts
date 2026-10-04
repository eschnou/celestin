import { describe, expect, it } from "vitest";
import { anchorTransform, clampAnchor, flowRows, spreadRow, textPx } from "../labels";
import capacity from "./capacity.json";

/** `capacity.json` is copied verbatim from `backend/tests/fixtures/figure/`; a backend test keeps both identical. */

describe("textPx", () => {
  it.each(capacity.text_px as [string, number][])(
    "« %s » is %i px, as the tool counts it",
    (text, px) => {
      expect(textPx(text)).toBe(px);
    },
  );

  it("counts an astral letter once, as Python does", () => {
    expect(textPx("𝔻")).toBe(7);
  });
});

describe("flowRows", () => {
  it.each(capacity.rows)("packs $widths in $slot px as the tool does", ({ widths, slot, rows }) => {
    expect(flowRows(widths, slot)).toBe(rows);
  });
});

describe("anchorTransform", () => {
  it("puts the box beside its anchor on the side it points to", () => {
    expect(anchorTransform([1, 0])).toBe("translate(0%, -50%)");
    expect(anchorTransform([0, -1])).toBe("translate(-50%, -100%)");
    expect(anchorTransform([-1, 1])).toBe("translate(-100%, 0%)");
  });

  it("centres the box for no direction, and never writes NaN", () => {
    expect(anchorTransform([0, 0])).toBe("translate(-50%, -50%)");
    expect(anchorTransform([Number.NaN, 1])).toBe("translate(-50%, -50%)");
    expect(anchorTransform([Infinity, 0])).toBe("translate(-50%, -50%)");
  });
});

describe("clampAnchor", () => {
  const inside = (x: number, y: number, dir: [number, number], w: number, h: number) => {
    // Where the translated box lands, as anchorTransform places it.
    const m = Math.max(Math.abs(dir[0]), Math.abs(dir[1])) || 1;
    const left = x + w * (-0.5 + (0.5 * dir[0]) / m);
    const top = y + h * (-0.5 + (0.5 * dir[1]) / m);
    return left >= -1e-9 && top >= -1e-9 && left + w <= 294 + 1e-9 && top + h <= 200 + 1e-9;
  };

  it("keeps a label near the right edge inside the drawing", () => {
    const [x, y] = clampAnchor(290, 100, [1, 0], 105, 16, 294, 200);
    expect(inside(x, y, [1, 0], 105, 16)).toBe(true);
  });

  it("keeps a label above the top inside, and leaves an inner one alone", () => {
    const [x, y] = clampAnchor(4, 2, [0, -1], 40, 16, 294, 200);
    expect(inside(x, y, [0, -1], 40, 16)).toBe(true);
    expect(clampAnchor(150, 100, [1, 0], 40, 16, 294, 200)).toEqual([150, 100]);
  });
});

describe("spreadRow", () => {
  it("pushes two long labels ≥ 12 px apart and keeps them inside", () => {
    const [a = 0, b = 0] = spreadRow(
      [
        { centre: 102.7, width: 105 },
        { centre: 191.3, width: 105 },
      ],
      14,
      280,
      12,
    );
    expect(b - 52.5 - (a + 52.5)).toBeGreaterThanOrEqual(12 - 1e-9);
    expect(a - 52.5).toBeGreaterThanOrEqual(14);
    expect(b + 52.5).toBeLessThanOrEqual(280);
    // Pushed apart evenly, around where they wanted to be.
    expect((a + b) / 2).toBeCloseTo(147, 0);
  });

  it("leaves labels that do not collide where they are", () => {
    expect(
      spreadRow(
        [
          { centre: 50, width: 20 },
          { centre: 150, width: 20 },
        ],
        0,
        300,
        12,
      ),
    ).toEqual([50, 150]);
  });
});
