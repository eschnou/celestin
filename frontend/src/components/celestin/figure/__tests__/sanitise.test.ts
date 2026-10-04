import { describe, expect, it } from "vitest";
import { MAX_MAGNITUDE, MIN_SPAN, sanitise } from "../sanitise";
import { NESTED, PLANE, SETS } from "./fixtures";

describe("sanitise", () => {
  it.each([
    {},
    null,
    undefined,
    [],
    "plane",
    42,
    { kind: "plane" },
    { kind: "plane", points: "x" },
    { kind: "plane", points: [], shapes: "x" },
    { kind: "number_line", intervals: "x", marks: {} },
    { kind: "sets", sets: "x" },
    { kind: "sets", sets: [{ id: "A" }] },
    { kind: "zzz" },
  ])("never throws, and gives nothing to draw for %j", (raw) => {
    expect(() => sanitise(raw)).not.toThrow();
    expect(sanitise(raw)).toBeNull();
  });

  it("drops shapes on missing points, bad pairs and non-finite coordinates", () => {
    const fig = sanitise({
      ...PLANE,
      points: { A: [0, 0], B: [4, 0], C: [Number.NaN, 3], D: [1], AB: [1, 1] },
      shapes: [
        { draw: "segment", of: ["A", "B"] },
        { draw: "segment", of: ["A", "C"] },
        { draw: "polygon", of: ["A", "B", "D"] },
        { draw: "curve", of: ["A", "B"] },
      ],
    });
    if (fig?.kind !== "plane") throw new Error("plane expected");
    expect(fig.points.map((p) => p.name)).toEqual(["A", "B"]);
    expect(fig.shapes).toHaveLength(1);
    expect(fig.marker).toBe("cross");
  });

  it("keeps a circle given one way or the other, and cuts shapes to their arity", () => {
    const fig = sanitise({
      kind: "plane",
      points: { O: [0, 0], A: [1, 0], B: [0, 1] },
      shapes: [
        { draw: "circle", of: ["O"], radius: 2 },
        { draw: "circle", of: ["O", "A"] },
        { draw: "circle", of: ["O"] },
        { draw: "segment", of: ["O", "A", "B"], marks: 7 },
        { draw: "circle", of: ["O", "A"], marks: 2 },
      ],
    });
    if (fig?.kind !== "plane") throw new Error("plane expected");
    expect(fig.shapes.map((s) => [s.draw, s.of.length, s.radius, s.marks])).toEqual([
      ["circle", 1, 2, 0],
      ["circle", 2, null, 0],
      ["segment", 2, null, 3],
      ["circle", 2, null, 0],
    ]);
  });

  it("swaps a reversed interval and never includes an infinite end", () => {
    const fig = sanitise({
      kind: "number_line",
      intervals: [
        { start: 5, end: 2, closed: "left" },
        { start: null, end: 2, closed: "both" },
        { start: 3, end: 3, closed: "both" },
        { start: Number.NaN, end: 3, closed: "both" },
      ],
      marks: [{ x: 1 }, { x: 1 }, { x: Number.POSITIVE_INFINITY }],
    });
    if (fig?.kind !== "number_line") throw new Error("number line expected");
    expect(fig.intervals).toEqual([
      { start: 2, end: 5, closed: "right", label: null },
      { start: null, end: 2, closed: "right", label: null },
    ]);
    expect(fig.marks).toEqual([{ x: 1, label: null }]);
    expect(fig.convention).toBe("brackets");
  });

  it("keeps three overlapping sets at most, and makes one set nested", () => {
    const four = sanitise({ ...SETS, sets: ["A", "B", "C", "D"].map((id) => ({ id, label: id })) });
    expect(four?.kind === "sets" && four.sets.map((s) => s.id)).toEqual(["A", "B", "C"]);
    const one = sanitise({ ...SETS, sets: [{ id: "A", label: "A" }] });
    expect(one?.kind === "sets" && one.layout).toBe("nested");
    const unknown = sanitise({ ...SETS, layout: "venn" });
    expect(unknown?.kind === "sets" && unknown.layout).toBe("nested");
  });

  it("drops what lies outside every set without a universe, and normalises nested zones", () => {
    const outside = sanitise({ ...SETS, elements: [{ text: "5", within: [] }], shade: [[]] });
    expect(outside?.kind === "sets" && [outside.elements, outside.shade]).toEqual([[], []]);
    const nested = sanitise({ ...NESTED, shade: [["Z"], ["N", "Z"], ["N"]] });
    if (nested?.kind !== "sets") throw new Error("sets expected");
    expect(nested.elements.at(-1)).toEqual({ text: "7", zone: [4] });
    expect(nested.shade).toEqual([[3], [4]]);
  });

  it("drops a set whose id is repeated or malformed", () => {
    const fig = sanitise({
      ...SETS,
      sets: [
        { id: "A", label: "x" },
        { id: "A", label: "y" },
        { id: "ABC", label: "z" },
        { id: "B", label: "w" },
      ],
    });
    expect(fig?.kind === "sets" && fig.sets.map((s) => s.label)).toEqual(["x", "w"]);
  });

  it("drops a number beyond the tool's magnitude, as it drops a non-finite one", () => {
    const fig = sanitise({
      kind: "plane",
      points: { A: [0, 0], B: [MAX_MAGNITUDE, -MAX_MAGNITUDE], C: [2e6, 0], D: [0, 1e308] },
      shapes: [{ draw: "circle", of: ["A"], radius: 1e7 }],
      x_range: [0, 1e12],
    });
    if (fig?.kind !== "plane") throw new Error("plane expected");
    expect(fig.points.map((p) => p.name)).toEqual(["A", "B"]);
    expect(fig.shapes).toEqual([]);
    expect(fig.xRange).toBeNull();
    const line = sanitise({
      kind: "number_line",
      intervals: [{ start: 0, end: 1e9, closed: "both" }],
      marks: [{ x: -1e7 }, { x: 3 }],
    });
    expect(line?.kind === "number_line" && [line.intervals, line.marks]).toEqual([
      [],
      [{ x: 3, label: null }],
    ]);
  });

  it("ignores a range narrower than MIN_SPAN", () => {
    const fig = sanitise({ kind: "plane", points: { A: [0, 0] }, x_range: [0, 1e-100] });
    expect(fig?.kind === "plane" && fig.xRange).toBeNull();
    const kept = sanitise({ kind: "plane", points: { A: [0, 0] }, x_range: [0, MIN_SPAN] });
    expect(kept?.kind === "plane" && kept.xRange).toEqual([0, MIN_SPAN]);
  });

  it("keeps a set, an element and a universe written blank, as the tool counted them", () => {
    const fig = sanitise({
      ...SETS,
      universe: " ",
      sets: [
        { id: "A", label: " " },
        { id: "B", label: "B" },
      ],
      elements: [
        { text: " ", within: ["A"] },
        { text: "5", within: [] },
      ],
    });
    if (fig?.kind !== "sets") throw new Error("sets expected");
    expect(fig.layout).toBe("overlap");
    expect(fig.sets.map((s) => s.label)).toEqual([" ", "B"]);
    expect(fig.universe).toBe(" ");
    expect(fig.elements).toEqual([
      { text: " ", zone: [0] },
      { text: "5", zone: [] },
    ]);
  });
});
