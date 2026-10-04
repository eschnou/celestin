import { describe, expect, it } from "vitest";
import type { PlotBlock } from "@/lib/tutor/types";
import { sanitise } from "../sanitise";
import { PLOTS } from "./fixtures";

const stored = (v: unknown) => sanitise(v as PlotBlock);

describe("sanitise", () => {
  it("keeps a valid plot, every field present", () => {
    const plot = sanitise(PLOTS.piecewise);
    expect(plot.x_range).toEqual([-3, 4]);
    expect(plot.grid).toBe(true);
    expect(plot.orthonormal).toBe(false);
    expect(plot.curves).toHaveLength(2);
    expect(plot.curves[0]?.f(0)).toBe(1);
    expect(plot.curves[0]).toMatchObject({ domain: [-3, 1], start_dot: "none", end_dot: "hollow" });
    expect(plot.sequences).toEqual([]);
    expect(plot.caption).toBeNull();
  });

  it("never throws, whatever JSON it is handed", () => {
    for (const v of [null, undefined, 42, "plot", [], { curves: "x" }, { x_range: "a" }]) {
      expect(() => stored(v)).not.toThrow();
    }
    expect(stored(null)).toMatchObject({ x_range: [-10, 10], curves: [], x_title: "" });
  });

  it("falls back on a range the scales cannot graduate, and sorts a reversed one", () => {
    expect(stored({ ...PLOTS.parabola, x_range: [0, 1e-200] }).x_range).toEqual([-10, 10]);
    expect(stored({ ...PLOTS.parabola, x_range: [0, 1e7] }).x_range).toEqual([-10, 10]);
    expect(stored({ ...PLOTS.parabola, x_range: [0, Number.NaN] }).x_range).toEqual([-10, 10]);
    expect(stored({ ...PLOTS.parabola, x_range: [4, -4] }).x_range).toEqual([-4, 4]);
  });

  it("keeps a thousandth-wide window despite float noise, as the tool does", () => {
    // 1.101 − 1.1 is 0.0009999999999998899.
    expect(stored({ ...PLOTS.parabola, x_range: [1.1, 1.101] }).x_range).toEqual([1.1, 1.101]);
    expect(stored({ ...PLOTS.parabola, y_range: [2.5, 2.501] }).y_range).toEqual([2.5, 2.501]);
    expect(stored({ ...PLOTS.parabola, x_range: [1.1, 1.1009] }).x_range).toEqual([-10, 10]);
  });

  it("drops a sequence whose first index lies beyond the model's 0 to 1000", () => {
    const at = (first: number, last: number) =>
      stored({ ...PLOTS.sequence, sequences: [{ expr: "n", first, last }] }).sequences.map((q) => [
        q.first,
        q.last,
      ]);
    expect(at(1e16, 1e16 + 3)).toEqual([]);
    expect(at(1001, 1003)).toEqual([]);
    expect(at(-1, 3)).toEqual([]);
    expect(at(1000, 1003)).toEqual([[1000, 1003]]);
    expect(at(0, 1e16)).toEqual([[0, 59]]);
  });

  it("drops a step it cannot write, or one that crowds the axis", () => {
    const at = (x_step: unknown, x_range = [0, 1]) =>
      stored({ ...PLOTS.parabola, x_range, x_step }).x_step;
    expect(at(0.25)).toBe(0.25);
    expect(at(0.00005, [0, 0.001])).toBeNull();
    expect(at(1 / 3)).toBeNull();
    expect(at(0)).toBeNull();
    expect(at(-1)).toBeNull();
    expect(at(0.01)).toBeNull(); // 100 intervals
    expect(at(2)).toBeNull(); // wider than the window
    expect(at("1")).toBeNull();
  });

  it("keeps orthonormal only when the window allows it", () => {
    expect(sanitise(PLOTS.orthonormal).orthonormal).toBe(true);
    expect(stored({ ...PLOTS.orthonormal, y_range: [-40, 40] }).orthonormal).toBe(false);
    expect(stored({ ...PLOTS.parabola, orthonormal: "yes" }).orthonormal).toBe(false);
  });

  it.each([
    [[-5, 5], [-10, 10], true], // exactly 2
    [[-5, 5], [-10, 10.01], false], // 2.001
    [[0, 10], [0, 4], true], // exactly 0.4
    [[0, 10], [0, 3.99], false], // 0.399
    // Float noise on the bounds the tool accepted: 0.39999999999999997 and 2.0000000000000004.
    [[0, 1], [0.3, 0.7], true],
    [[0.2, 0.3], [0, 0.2], true],
  ] as const)("keeps orthonormal on the tool's bounds: %j × %j", (x_range, y_range, kept) => {
    const plot = stored({ ...PLOTS.orthonormal, x_range, y_range });
    expect(plot.orthonormal).toBe(kept);
  });

  it("drops what cannot be drawn and keeps the rest", () => {
    const plot = stored({
      ...PLOTS.parabola,
      curves: [
        { expr: "1/2x" },
        { expr: 3 },
        { expr: "x", domain: [2, "a"], start_dot: "open", dashed: "yes" },
        null,
      ],
      sequences: [
        { expr: "n", last: 3 },
        { expr: "n", first: 2.7, last: 500 },
        { expr: "n", first: 5, last: 2 },
        { expr: "n", last: 4 }, // a fourth: over the limit
      ],
      points: [{ x: Number.NaN, y: 1 }, { x: 1, y: 1, mark: "star" }, "A"],
      lines: [{ vertices: [[0, 0]] }, { vertices: [[0, 0], [1, Infinity], [2, 2], [3]] }],
    });
    expect(plot.curves).toHaveLength(1);
    expect(plot.curves[0]).toMatchObject({ domain: null, start_dot: "none", dashed: false });
    expect(plot.sequences.map((s) => [s.first, s.last])).toEqual([
      [1, 3],
      [2, 61],
    ]);
    expect(plot.points).toEqual([
      { x: 1, y: 1, label: null, mark: "filled", guides: false, show_values: false },
    ]);
    expect(plot.lines).toEqual([
      {
        vertices: [
          [0, 0],
          [2, 2],
        ],
        dashed: false,
        label: null,
      },
    ]);
  });

  it("caps lists and texts at the limits", () => {
    const plot = stored({
      ...PLOTS.parabola,
      x_title: "  $t$ (s)  ",
      caption: "   ",
      curves: Array.from({ length: 9 }, () => ({ expr: "x", label: "L".repeat(80) })),
      points: Array.from({ length: 30 }, () => ({ x: 0, y: 0 })),
    });
    expect(plot.x_title).toBe("$t$ (s)");
    expect(plot.caption).toBeNull();
    expect(plot.curves).toHaveLength(6);
    expect(plot.curves[0]?.label).toHaveLength(40);
    expect(plot.points).toHaveLength(20);
  });
});
