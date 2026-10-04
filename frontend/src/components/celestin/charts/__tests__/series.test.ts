import { describe, expect, it } from "vitest";
import { CHARTS } from "./fixtures";
import {
  arcPath,
  boxGeometry,
  cumulativePoints,
  drawable,
  histogramRects,
  entries,
  pieArcs,
  polygonPoints,
  sanitise,
} from "../series";

describe("histogramRects", () => {
  it("uses the values as heights when amplitudes are equal", () => {
    expect(histogramRects([0, 10, 20], [4, 6]).map((r) => r.height)).toEqual([4, 6]);
  });

  it("keeps areas proportional when amplitudes differ", () => {
    // [0;10[ and [10;30[ with 10 each: the wide class is half as high.
    expect(histogramRects([0, 10, 30], [10, 10]).map((r) => r.height)).toEqual([10, 5]);
  });

  it("scales to an explicit reference amplitude", () => {
    expect(histogramRects([0, 10, 30], [10, 10], 5).map((r) => r.height)).toEqual([5, 2.5]);
  });
});

describe("polygonPoints", () => {
  const rects = histogramRects([0, 10, 20], [4, 6]);

  it("joins the middles of the tops", () => {
    expect(polygonPoints(rects, "open")).toEqual([
      [5, 4],
      [15, 6],
    ]);
  });

  it("closes on the axis half a class beyond each end", () => {
    const points = polygonPoints(rects, "closed");
    expect(points[0]).toEqual([-5, 0]);
    expect(points.at(-1)).toEqual([25, 0]);
  });
});

describe("cumulativePoints", () => {
  it("rises from 0 on the first bound to the total on the last", () => {
    expect(cumulativePoints([0, 10, 20, 30], [2, 5, 3], "increasing")).toEqual([
      [0, 0],
      [10, 2],
      [20, 7],
      [30, 10],
    ]);
  });

  it("falls from the total to 0 when decreasing", () => {
    expect(cumulativePoints([0, 10, 20, 30], [2, 5, 3], "decreasing")).toEqual([
      [0, 10],
      [10, 8],
      [20, 3],
      [30, 0],
    ]);
  });
});

describe("pieArcs", () => {
  it("covers the whole turn in proportion", () => {
    const arcs = pieArcs([1, 1, 2]);
    expect(arcs.at(-1)?.end).toBeCloseTo(2 * Math.PI);
    expect(arcs[2]!.end - arcs[2]!.start).toBeCloseTo(Math.PI);
  });

  it("draws nothing for an empty series and a full circle for one sector", () => {
    expect(pieArcs([0, 0])).toEqual([]);
    expect(arcPath(0, 0, 10, 0, 2 * Math.PI)).not.toContain("L");
  });
});

describe("boxGeometry", () => {
  it("orders a box stored out of order", () => {
    expect(boxGeometry({ minimum: 4, q1: 13, median: 12, q3: 14, maximum: 19 })).toEqual({
      minimum: 4,
      q1: 12,
      median: 13,
      q3: 14,
      maximum: 19,
    });
  });
});

describe("sanitise", () => {
  it("cuts mismatched lists and counts a bad value as zero", () => {
    const chart = sanitise({ ...CHARTS.bars, values: [12, Number.NaN, -3, 8] });
    expect(chart).toMatchObject({ categories: ["Vélo", "Bus", "À pied"], values: [12, 0, 0] });
  });

  it("stops classes at the first bound that is not finite or not increasing", () => {
    const chart = sanitise({
      ...CHARTS.histogram,
      bounds: [150, 160, 155, 180],
      values: [4, 6, 2],
    });
    expect(chart).toMatchObject({ bounds: [150, 160], values: [4] });
  });

  it("drops sticks on a value that is not a number", () => {
    const chart = sanitise({
      ...CHARTS.sticks,
      x: [12, Number.NaN, 16],
      values: [2, 5, 3],
    });
    expect(chart).toMatchObject({ x: [12, 16], values: [2, 3] });
  });

  it("leaves nothing to draw when every value is zero", () => {
    expect(drawable(sanitise({ ...CHARTS.bars, values: [0, 0, 0] }))).toBe(false);
    expect(drawable(sanitise(CHARTS.bars))).toBe(true);
  });
});

describe("entries", () => {
  it("labels each value as the course writes it", () => {
    expect(entries(CHARTS.histogram).map((e) => e.label)).toEqual(["[150 ; 160[", "[160 ; 180["]);
    expect(entries({ ...CHARTS.sticks, x: [1.5], values: [2] })).toEqual([
      { label: "1,5", value: 2 },
    ]);
  });
});
