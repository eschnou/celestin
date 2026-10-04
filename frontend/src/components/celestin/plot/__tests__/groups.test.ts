import { describe, expect, it } from "vitest";
import type { PlotBlock } from "@/lib/tutor/types";
import { colourGroups, colourOf, MUTED, SERIES } from "../groups";
import { sanitise } from "../sanitise";
import { PLOTS } from "./fixtures";

const colours = (block: PlotBlock) => colourGroups(sanitise(block));

describe("colourGroups", () => {
  it("gives the three unlabelled pieces of a motion one colour", () => {
    const c = colours(PLOTS.motion);
    expect(c.groups).toHaveLength(1);
    expect(new Set(c.curve.map((g) => colourOf(c, g)))).toEqual(new Set([SERIES[0]]));
  });

  it("gives the pieces of one function, labelled alike, one group", () => {
    const c = colours(PLOTS.piecewise);
    expect(c.groups).toEqual([
      { label: "$f$", colour: SERIES[0], curves: [0, 1], sequences: [], lines: [] },
    ]);
  });

  it("gives two functions two colours", () => {
    const c = colours({
      ...PLOTS.parabola,
      curves: [
        { expr: "x", label: "$f$" },
        { expr: "2x", label: "$g$" },
        { expr: "3x", label: " $f$ " },
      ],
    });
    expect(c.groups.map((g) => g.label)).toEqual(["$f$", "$g$"]);
    expect(c.curve).toEqual([0, 1, 0]);
    expect(colourOf(c, 1)).toBe(SERIES[1]);
  });

  it("draws dashed layers in the muted ink, outside any group", () => {
    const c = colours(PLOTS.hyperbola);
    expect(c.line).toEqual([null]);
    expect(colourOf(c, c.line[0] ?? null)).toBe(MUTED);
    expect(c.groups).toHaveLength(1);
  });

  it("groups curves, sequences and lines by label across layers", () => {
    const c = colours({
      ...PLOTS.sequence,
      curves: [{ expr: "x", label: "$u_n$", dashed: false }],
      lines: [
        {
          vertices: [
            [0, 0],
            [1, 1],
          ],
        },
      ],
    });
    expect(c.groups.map((g) => [g.label, g.curves, g.sequences, g.lines])).toEqual([
      ["$u_n$", [0], [0], []],
      [null, [], [], [0]],
    ]);
  });

  it("never uses the two light series colours", () => {
    const many = colours({
      ...PLOTS.parabola,
      curves: ["a", "b", "c", "d", "e", "f"].map((l, i) => ({ expr: `x+${i}`, label: l })),
      lines: ["g", "h"].map((l) => ({
        vertices: [
          [0, 0],
          [1, 1],
        ] as [number, number][],
        label: l,
      })),
    });
    const used = many.groups.map((g) => g.colour);
    expect(used).not.toContain("var(--chart-3)");
    expect(used).not.toContain("var(--chart-7)");
    expect(used).toHaveLength(8);
  });
});
