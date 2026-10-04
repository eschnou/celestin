import { describe, expect, it } from "vitest";
import {
  angleMark,
  clipToWindow,
  fitWindow,
  gridStep,
  groupPoints,
  labelDirection,
  labelStep,
  minorArc,
  nameTex,
  nameText,
  planeWindow,
} from "../geometry";
import { formatPair } from "../../charts/format";
import { LABEL_H, labelBox, overlaps, textPx, type PlacedLabel } from "../labels";
import { planeScene } from "../plane-scene";
import { sanitise, type CleanPlane } from "../sanitise";
import { AXES_ONLY, PLANE } from "./fixtures";

const plane = (figure: object): CleanPlane => {
  const fig = sanitise({ kind: "plane", ...figure });
  if (fig?.kind !== "plane") throw new Error("not a plane");
  return fig;
};

describe("planeWindow", () => {
  it("pads the content by a tenth of its larger span", () => {
    const win = planeWindow(plane({ points: { A: [0, 0], B: [4, 0], C: [0, 3] } }));
    expect(win.x0).toBeCloseTo(-0.4);
    expect(win.x1).toBeCloseTo(4.4);
    expect(win.y0).toBeCloseTo(-0.4);
    expect(win.y1).toBeCloseTo(3.4);
  });

  it("grows a given range to hold the content, and the origin with axes", () => {
    const win = planeWindow(
      plane({ points: { A: [5, 1] }, x_range: [0, 3], y_range: [2, 4], axes: true }),
    );
    expect(win.x1).toBeGreaterThanOrEqual(5);
    expect(win.y0).toBeLessThanOrEqual(0);
    expect(win.x0).toBeLessThanOrEqual(0);
  });

  it("never shrinks a given range", () => {
    const win = planeWindow(
      plane({ points: { A: [1, 1] }, x_range: [-10, 10], y_range: [-10, 10] }),
    );
    expect(win.x0).toBeLessThanOrEqual(-10);
    expect(win.x1).toBeGreaterThanOrEqual(10);
    expect(win.y0).toBeLessThanOrEqual(-10);
    expect(win.y1).toBeGreaterThanOrEqual(10);
  });

  it("widens flat content so nothing is squashed", () => {
    const win = planeWindow(plane({ points: { A: [0, 0], B: [8, 0] } }));
    expect(win.y1 - win.y0).toBeGreaterThanOrEqual(0.25 * (win.x1 - win.x0) - 1e-9);
  });

  it("is [−5 ; 5] when there is nothing to hold", () => {
    expect(planeWindow(plane(AXES_ONLY))).toEqual({ x0: -5, x1: 5, y0: -5, y1: 5 });
  });

  it.each([1e-100, 1e-300, Number.MIN_VALUE, 1e-12])(
    "shows content %s wide as one place, a unit around it",
    (gap) => {
      const win = planeWindow(plane({ points: { A: [0, 0], B: [gap, 0] }, grid: true }));
      expect(win.x1 - win.x0).toBeGreaterThanOrEqual(2);
      expect(win.y1 - win.y0).toBeGreaterThanOrEqual(2);
    },
  );

  it("snaps to the grid step with a grid", () => {
    const win = planeWindow(plane({ ...PLANE, grid: true }));
    for (const v of [win.x0, win.x1, win.y0, win.y1]) expect(Number.isInteger(v)).toBe(true);
    expect(win).toEqual({ x0: -1, x1: 5, y0: -1, y1: 4 });
  });
});

describe("gridStep", () => {
  it("is the quadrillage's unit from 4 to 20 units, a round step otherwise", () => {
    expect(gridStep(10, 6)).toBe(1);
    expect(gridStep(2, 1)).toBe(0.2);
    expect(gridStep(50, 20)).toBe(5);
  });

  it("is the unit step for a window too small or too large to count ticks in", () => {
    expect(gridStep(1e-100, 1e-100)).toBe(1);
    expect(gridStep(0, 0)).toBe(1);
    expect(gridStep(Number.POSITIVE_INFINITY, 1)).toBe(1);
    expect(gridStep(2e6, 1e6)).toBe(200_000);
  });
});

describe("labelStep", () => {
  it("thins numbers so none is closer than its width", () => {
    // [−10 ; 10] at 12,5 px per unit: « −10 » is 21 px wide.
    const k = labelStep(1, 12.5, 21 + 8);
    expect(k).toBeGreaterThanOrEqual(2);
    expect(k * 12.5).toBeGreaterThanOrEqual(29);
  });
});

describe("fitWindow", () => {
  it("uses one scale on both axes and caps the height", () => {
    const frame = fitWindow({ x0: -0.4, x1: 4.4, y0: -0.4, y1: 3.2 }, 294);
    const [ax, ay] = frame.px([0, 0]);
    const [bx] = frame.px([1, 0]);
    const [, cy] = frame.px([0, 1]);
    expect(bx - ax).toBeCloseTo(ay - cy);
    expect(frame.s).toBeCloseTo(254 / 4.8);
    expect(frame.height).toBeLessThanOrEqual(Math.min(1.1 * 294, 400));
    const tall = fitWindow({ x0: 0, x1: 1, y0: 0, y1: 100 }, 800);
    expect(tall.height).toBeLessThanOrEqual(400);
  });

  it.each([3e8, 1e9, 1e12, 1e300])(
    "draws a window %s units wide at a small scale, never taller than the cap",
    (span) => {
      const frame = fitWindow({ x0: 0, x1: span, y0: 0, y1: span }, 294);
      expect(frame.height).toBeLessThanOrEqual(Math.min(1.1 * 294, 400));
      const [left] = frame.px([0, 0]);
      const [right] = frame.px([span, 0]);
      expect(left).toBeGreaterThanOrEqual(0);
      expect(right).toBeLessThanOrEqual(294);
    },
  );
});

describe("clipToWindow", () => {
  const win = { x0: 0, x1: 10, y0: 0, y1: 10 };

  it("cuts a line through the window at both edges", () => {
    const seg = clipToWindow([2, 2], [3, 3], win, false);
    expect(seg?.[0]).toEqual([0, 0]);
    expect(seg?.[1]).toEqual([10, 10]);
  });

  it("cuts a ray only on its far side", () => {
    const seg = clipToWindow([2, 5], [3, 5], win, true);
    expect(seg?.[0]).toEqual([2, 5]);
    expect(seg?.[1]).toEqual([10, 5]);
  });

  it("is null for a line that misses the window", () => {
    expect(clipToWindow([-5, 20], [5, 20], win, false)).toBeNull();
    expect(clipToWindow([1, 1], [1, 1], win, false)).toBeNull();
  });
});

describe("minorArc", () => {
  it("turns counter-clockwise (sweep-flag 0) a quarter turn from (1 ; 0) to (0 ; 1)", () => {
    const arc = minorArc([1, 0], [0, 0], [0, 1]);
    expect(arc?.sweep).toBe(0);
    expect(arc?.delta).toBeCloseTo(Math.PI / 2);
  });

  it("turns the other way (sweep-flag 1) with the ends swapped, the same quarter", () => {
    const arc = minorArc([0, 1], [0, 0], [1, 0]);
    expect(arc?.sweep).toBe(1);
    expect(Math.abs(arc?.delta ?? 0)).toBeCloseTo(Math.PI / 2);
  });

  it("never turns more than a half turn", () => {
    for (let k = 1; k < 24; k += 1) {
      const t = (k * Math.PI) / 12;
      const arc = minorArc([1, 0], [0, 0], [Math.cos(t), Math.sin(t)]);
      expect(Math.abs(arc?.delta ?? 0)).toBeLessThanOrEqual(Math.PI + 1e-12);
    }
    expect(minorArc([1, 0], [0, 0], [-1, 0])?.sweep).toBe(0);
    expect(minorArc([0, 0], [0, 0], [1, 0])).toBeNull();
  });
});

describe("angleMark", () => {
  it("fills an unmarked angle and draws no arc", () => {
    const mark = angleMark([100, 0], [0, 0], [0, -100], 0);
    expect(mark?.sector).toMatch(/^M .* Z$/);
    expect(mark?.arcs).toEqual([]);
  });

  it("draws one arc per mark of the codage", () => {
    const mark = angleMark([100, 0], [0, 0], [0, -100], 2);
    expect(mark?.sector).toBe("");
    expect(mark?.arcs).toHaveLength(2);
  });

  it("gives nothing for arms of no length", () => {
    expect(angleMark([0, 0], [0, 0], [1, 1], 1)).toBeNull();
  });
});

describe("labelDirection", () => {
  it("points a triangle's vertex away from its centre", () => {
    const [dx, dy] = labelDirection(
      [0, 0],
      [
        [100, 0],
        [0, 100],
      ],
      [33, 33],
    );
    expect(dx).toBeLessThan(0);
    expect(dy).toBeLessThan(0);
    expect(Math.hypot(dx, dy)).toBeCloseTo(1);
  });

  it("takes the perpendicular at a midpoint, away from the figure", () => {
    const [dx, dy] = labelDirection(
      [50, 0],
      [
        [0, 0],
        [100, 0],
      ],
      [50, 80],
    );
    expect(dx).toBeCloseTo(0);
    expect(dy).toBeCloseTo(-1);
  });

  it("stays finite with coincident neighbours", () => {
    const dir = labelDirection(
      [10, 10],
      [
        [10, 10],
        [10, 10],
      ],
      [10, 10],
    );
    expect(dir.every(Number.isFinite)).toBe(true);
    expect(labelDirection([Number.NaN, 0], [], [0, 0]).every(Number.isFinite)).toBe(true);
  });
});

describe("points and their names", () => {
  it("merges points at the very same place under one mark", () => {
    const groups = groupPoints(
      [
        { name: "A", at: [0, 0] },
        { name: "A'", at: [0, 0] },
        { name: "B", at: [1, 0] },
      ],
      1,
    );
    expect(groups.map((g) => g.names)).toEqual([["A", "A'"], ["B"]]);
  });

  it("writes names and coordinates as the course does", () => {
    expect(nameTex("A_12")).toBe("A_{12}");
    expect(nameTex("M''")).toBe("M''");
    expect(nameText("A_1")).toBe("A₁");
    expect(formatPair(2, -1.5)).toBe("(2 ; −1,5)");
  });
});

describe("planeScene at the tool's limits", () => {
  it.each([
    ["a thousandth wide, the smallest the tool accepts", { A: [0, 0], B: [1e-3, 0], C: [0, 1e-3] }],
    ["a millionth wide (a stored card)", { A: [0, 0], B: [1e-6, 0], C: [0, 1e-6] }],
    ["a million wide, the largest the tool accepts", { A: [0, 0], B: [1e6, 0], C: [0, 1e6] }],
    ["closer than MIN_SPAN (a stored card)", { A: [0, 0], B: [1e-100, 0], C: [0, 1e-100] }],
  ])("draws a triangle %s inside 294 × 400 px, without NaN", (_, points) => {
    for (const extra of [{}, { grid: true }, { axes: true, grid: true, show_values: true }]) {
      const scene = planeScene(
        plane({ points, shapes: [{ draw: "polygon", of: ["A", "B", "C"] }], ...extra }),
        294,
      );
      expect(scene.width).toBe(294);
      expect(scene.height).toBeLessThanOrEqual(Math.min(1.1 * 294, 400));
      expect(JSON.stringify(scene)).not.toMatch(/NaN|Infinity/);
      for (const m of scene.markers) {
        expect(m.at[0]).toBeGreaterThanOrEqual(0);
        expect(m.at[0]).toBeLessThanOrEqual(294);
      }
    }
  });

  it("tells a thousandth-wide triangle's points and axis numbers apart", () => {
    const scene = planeScene(
      plane({ points: { A: [0, 0], B: [1e-3, 0], C: [0, 1e-3] }, axes: true, grid: true }),
      294,
    );
    expect(scene.markers).toHaveLength(3);
    const numbers = scene.axes?.numbers.map((n) => n.key[0] + n.text) ?? [];
    expect(numbers.length).toBeGreaterThan(2);
    expect(new Set(numbers).size).toBe(numbers.length);
  });
});

describe("point labels in a dense figure", () => {
  const width = (l: PlacedLabel) =>
    l.parts.reduce((t, p) => t + textPx(p.kind === "tex" ? `$${p.text}$` : p.text), 0);
  const lattice = Object.fromEntries(
    [..."ABCDEFGHIJKL"].map((n, i) => [n, [2 * (i % 4), 2 * Math.floor(i / 4)]]),
  );
  const medians = {
    points: { A: [0, 0], B: [6, 0], C: [2, 4], I: [3, 0], J: [4, 2], K: [1, 2], G: [8 / 3, 4 / 3] },
    shapes: [
      { draw: "polygon", of: ["A", "B", "C"] },
      { draw: "segment", of: ["A", "J"] },
      { draw: "segment", of: ["B", "K"] },
      { draw: "segment", of: ["C", "I"] },
    ],
  };

  it.each([
    ["12 points 2 units apart, with coordinates", { points: lattice, show_values: true }],
    [
      "the same in a gridded repère",
      { points: lattice, show_values: true, axes: true, grid: true },
    ],
    ["a triangle, its medians and centroid", { ...medians, show_values: true }],
  ])("keeps %s apart, off each other's marks, at 294 px", (_, figure) => {
    const scene = planeScene(plane(figure), 294);
    const boxes = scene.labels.map((l) => ({
      key: l.key,
      box: labelBox(l.x, l.y, l.dir, width(l), LABEL_H),
    }));
    for (const [i, a] of boxes.entries()) {
      for (const b of boxes.slice(i + 1))
        expect(overlaps(a.box, b.box), `${a.key} × ${b.key}`).toBe(false);
      for (const m of scene.markers) {
        if (a.key === `p${m.key}`) continue;
        const mark = { x0: m.at[0] - 4, y0: m.at[1] - 4, x1: m.at[0] + 4, y1: m.at[1] + 4 };
        expect(overlaps(a.box, mark), `${a.key} on ${m.key}`).toBe(false);
      }
      expect(a.box.x0).toBeGreaterThanOrEqual(0);
      expect(a.box.x1).toBeLessThanOrEqual(scene.width);
    }
  });
});
