import { describe, expect, it } from "vitest";
import { compileExpression, CURVE_VARIABLES, SEQUENCE_VARIABLES } from "../expression";
import {
  clipBand,
  clipLine,
  endpointValue,
  sampleCurve,
  sequenceDots,
  type Run,
  type Win,
} from "../sample";

const f = (src: string) => {
  const fn = compileExpression(src, CURVE_VARIABLES);
  if (!fn) throw new Error(`does not compile: ${src}`);
  return fn;
};
const WIN: Win = { x0: -5, x1: 5, y0: -5, y1: 5 };
const sample = (src: string, win = WIN, from = -Infinity, to = Infinity) =>
  sampleCurve(f(src), from, to, win, 280, 210);

const inside = (runs: Run[], win: Win) =>
  runs.every((run) =>
    run.every(
      ([x, y]) =>
        x >= win.x0 - 1e-9 && x <= win.x1 + 1e-9 && y >= win.y0 - 1e-9 && y <= win.y1 + 1e-9,
    ),
  );

describe("sampleCurve", () => {
  it("breaks 1/x at its pole into two branches ending on the window's edges", () => {
    const { runs } = sample("1/x");
    expect(runs).toHaveLength(2);
    expect(runs.flat().every(([x]) => Math.abs(x) >= 0.1)).toBe(true);
    const [left, right] = runs as [Run, Run];
    expect(left[0]?.[0]).toBeCloseTo(-5, 6);
    expect(right.at(-1)?.[0]).toBeCloseTo(5, 6);
    expect(left.at(-1)?.[1]).toBeCloseTo(-5, 6);
    expect(right[0]?.[1]).toBeCloseTo(5, 6);
  });

  it("cuts a parabola where it leaves the window, precisely", () => {
    const win = { x0: -5, x1: 5, y0: -5, y1: 8 };
    const { runs } = sample("x^2-4", win);
    expect(runs).toHaveLength(1);
    const run = runs[0] as Run;
    expect(Math.abs((run[0]?.[0] ?? 0) + Math.sqrt(12))).toBeLessThan(1e-6);
    expect(Math.abs((run.at(-1)?.[0] ?? 0) - Math.sqrt(12))).toBeLessThan(1e-6);
  });

  it("starts sqrt where it is defined", () => {
    const { runs } = sample("sqrt(x)", { x0: -2, x1: 5, y0: -1, y1: 3 });
    expect(runs).toHaveLength(1);
    expect(Math.abs(runs[0]?.[0]?.[0] ?? 1)).toBeLessThan(1e-3);
  });

  it("starts ln on the bottom edge", () => {
    const { runs } = sample("ln(x)", { x0: -1, x1: 5, y0: -3, y1: 3 });
    expect(runs).toHaveLength(1);
    expect(runs[0]?.[0]?.[0]).toBeCloseTo(Math.exp(-3), 4);
  });

  it("draws tan in several branches, a constant in one", () => {
    expect(sample("tan(x)").runs.length).toBeGreaterThanOrEqual(3);
    expect(sample("3").runs).toHaveLength(1);
  });

  it("keeps a steep line", () => {
    expect(sample("1000(x-0.0123)", { x0: -5, x1: 5, y0: -1, y1: 1 }).runs).toHaveLength(1);
    // Still over a pixel's rise after 12 halvings: its midpoint splits the rise.
    expect(sample("1000000(x-0.01234)", { x0: -5, x1: 5, y0: -1, y1: 1 }).runs).toHaveLength(1);
  });

  // On [−4,3 ; 5] no sample lands on the jump, so only the halvings can find it.
  it.each([
    ["abs(x)/x", 0],
    ["x+abs(x-1)/(x-1)", 1],
    ["abs(x-0.3)/(x-0.3)+x", 0.3],
  ])("breaks %s at its jump, with no vertical stroke", (src, at) => {
    const { runs } = sample(src, { x0: -4.3, x1: 5, y0: -5, y1: 5 });
    expect(runs).toHaveLength(2);
    const [left, right] = runs as [Run, Run];
    expect(left.at(-1)?.[0]).toBeLessThan(at);
    expect(right[0]?.[0]).toBeGreaterThan(at);
    expect(Math.abs((left.at(-1)?.[0] ?? 0) - at)).toBeLessThan(1e-3);
    for (const run of runs) {
      for (let i = 1; i < run.length; i += 1) {
        const [xa, ya] = run[i - 1] as [number, number];
        const [xb, yb] = run[i] as [number, number];
        // A stroke steeper than 1 px across for 50 px up is the jump drawn as a wall.
        const across = (Math.abs(xb - xa) * 280) / 9.3;
        const up = (Math.abs(yb - ya) * 210) / 10;
        expect(up < 50 || across > 1).toBe(true);
      }
    }
  });

  it("draws a piece on its domain only", () => {
    const { runs } = sampleCurve(
      f("10-2.5(t-12)"),
      12,
      16,
      { x0: 0, x1: 16, y0: 0, y1: 12 },
      280,
      210,
    );
    expect(runs).toHaveLength(1);
    expect(runs[0]?.[0]).toEqual([12, 10]);
    expect(runs[0]?.at(-1)?.[0]).toBeCloseTo(16, 9);
  });

  it("draws nothing for a domain outside the window", () => {
    expect(sample("x", WIN, 7, 9)).toEqual({ runs: [], calls: 0 });
  });

  it("keeps to its budget on a wild curve", () => {
    let calls = 0;
    const spy = (v: number) => {
      calls += 1;
      return Math.sin(1 / v);
    };
    const result = sampleCurve(
      spy,
      -Infinity,
      Infinity,
      { x0: -1, x1: 1, y0: -2, y1: 2 },
      280,
      210,
      5000,
    );
    expect(calls).toBe(result.calls);
    expect(calls).toBeLessThanOrEqual(5000);
  });

  it.each(["1/x", "x^2-4", "tan(x)", "sin(1/x)", "abs(x)/x", "(x^2-1)/(x-1)", "cbrt(x)", "ln(x)"])(
    "gives runs of at least two vertices, inside the window (%s)",
    (src) => {
      const { runs } = sample(src);
      expect(runs.every((r) => r.length >= 2)).toBe(true);
      expect(inside(runs, WIN)).toBe(true);
    },
  );
});

describe("clipBand and clipLine", () => {
  it("keeps an unclipped polyline as one run", () => {
    const piece: Run = [
      [0, 0],
      [1, 1],
      [2, 0],
      [3, 1],
    ];
    expect(clipBand(piece, -5, 5)).toEqual([piece]);
  });

  it("splits a polyline where it leaves the band", () => {
    const piece: Run = [
      [0, 0],
      [1, 10],
      [2, 0],
    ];
    const runs = clipBand(piece, -1, 5);
    expect(runs).toHaveLength(2);
    expect(runs[0]?.at(-1)).toEqual([0.5, 5]);
    expect(runs[1]?.[0]).toEqual([1.5, 5]);
  });

  it("cuts a line to the window", () => {
    expect(
      clipLine(
        [
          [0, -100],
          [0, 100],
        ],
        WIN,
      ),
    ).toEqual([
      [
        [0, -5],
        [0, 5],
      ],
    ]);
    expect(
      clipLine(
        [
          [10, 0],
          [20, 0],
        ],
        WIN,
      ),
    ).toEqual([]);
  });

  it("keeps consecutive visible segments as one run, and splits where one leaves", () => {
    const runs = clipLine(
      [
        [-4, 0],
        [0, 4],
        [4, 0],
        [4, 20],
        [0, 20],
        [0, 0],
      ],
      WIN,
    );
    expect(runs).toHaveLength(2);
    expect(runs[0]).toEqual([
      [-4, 0],
      [0, 4],
      [4, 0],
      [4, 5],
    ]);
    expect(runs[1]).toEqual([
      [0, 5],
      [0, 0],
    ]);
  });
});

describe("sequenceDots and endpointValue", () => {
  it("draws the terms inside the window, as isolated points", () => {
    const u = compileExpression("2+3(n-1)", SEQUENCE_VARIABLES);
    expect(u).not.toBeNull();
    if (!u) return;
    expect(sequenceDots(u, 1, 7, { x0: 0, x1: 8, y0: 0, y1: 15 })).toEqual([
      [1, 2],
      [2, 5],
      [3, 8],
      [4, 11],
      [5, 14],
    ]);
  });

  it("never runs past 60 terms, even where n + 1 is n", () => {
    let calls = 0;
    const u = (n: number) => {
      calls += 1;
      return n;
    };
    expect(sequenceDots(u, 1e16, 1e16 + 4, { x0: 0, x1: 10, y0: 0, y1: 10 })).toEqual([]);
    expect(calls).toBeLessThanOrEqual(60);
    calls = 0;
    sequenceDots(u, 1, 1000, { x0: 0, x1: 10, y0: 0, y1: 10 });
    expect(calls).toBe(60);
  });

  it("skips an undefined term", () => {
    const u = compileExpression("1/(n-3)", SEQUENCE_VARIABLES);
    if (!u) throw new Error("does not compile");
    expect(sequenceDots(u, 1, 5, { x0: 0, x1: 8, y0: -5, y1: 5 }).map(([n]) => n)).toEqual([
      1, 2, 4, 5,
    ]);
  });

  it("puts a hollow dot where the curve arrives, a filled one only where it is defined", () => {
    const hole = f("(x^2-1)/(x-1)");
    expect(endpointValue(hole, 1, -1, 4, "hollow")).toBeCloseTo(2, 6);
    expect(endpointValue(hole, 1, -1, 4, "filled")).toBeNull();
    expect(endpointValue(hole, -3, 1, 4, "filled")).toBe(-2);
    expect(endpointValue(hole, -3, 1, 4, "none")).toBeNull();
  });
});
