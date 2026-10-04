// @vitest-environment jsdom
/** A plot described in English: our sentences change, the course's notation does not. */
import { describe as group, expect, it } from "vitest";
import type { PlotBlock } from "@/lib/tutor/types";
import { withLocale } from "@/test/locale";
import { ariaLabel, describe } from "../describe";
import { layout } from "../layout";
import { sanitise } from "../sanitise";
import { PLOTS } from "./fixtures";

const text = (block: PlotBlock) => {
  const plot = sanitise(block);
  return describe(plot, layout(plot, 320));
};
const drawn = (block: PlotBlock) =>
  text(block)
    .split(/(?<=\.) /)
    .filter((s) => !/ axis /.test(s));

group("plot describe in English", () => {
  it("names the axes, their windows and graduations, and the pieces of one curve", () =>
    withLocale("en", () => {
      const d = text(PLOTS.motion);
      expect(d).toContain("Horizontal axis t (s), from 0 to 16, marked every 2.");
      expect(d).toContain("Vertical axis v (m/s), from 0 to 12, marked every 2.");
      expect(d).toContain("One curve in 3 pieces.");
    }));

  it("names what is drawn, singular and plural", () =>
    withLocale("en", () => {
      expect(drawn(PLOTS.piecewise)).toEqual(["Curve f, in 2 pieces."]);
      expect(drawn(PLOTS.orthonormal)).toEqual(["Orthonormal coordinate plane.", "Curve d."]);
      expect(drawn(PLOTS.sequence)).toEqual(["Sequence u subscript n, as separate points."]);
      expect(drawn(PLOTS.hyperbola)).toEqual(["Curve h.", "1 dashed drawing."]);
      expect(drawn(PLOTS.data)).toEqual(["One broken line.", "5 marked points."]);
    }));

  it("gives a point's coordinates in the course's notation, only when Célestin writes them", () =>
    withLocale("en", () => {
      expect(text(PLOTS.parabola)).toContain("Point S (0 ; −4).");
      const hidden = { ...PLOTS.parabola, points: [{ x: 0, y: -4, label: "$S$" }] };
      expect(text(hidden)).toContain("Point S.");
      expect(text(hidden)).not.toContain("−4)");
    }));

  it("says when nothing could be drawn", () =>
    withLocale("en", () => {
      expect(text({ ...PLOTS.parabola, curves: [{ expr: "1/2x" }], points: [] })).toContain(
        "Empty graph.",
      );
    }));

  it("labels the plot", () =>
    withLocale("en", () => {
      expect(ariaLabel(sanitise(PLOTS.motion))).toBe("Graph: v (m/s) as a function of t (s)");
      expect(ariaLabel(sanitise({ ...PLOTS.motion, x_title: "", y_title: "" }))).toBe("Graph");
      expect(ariaLabel(sanitise({ ...PLOTS.motion, x_title: "", y_title: "v" }))).toBe("Graph: v");
    }));

  it("keeps the coordinates as the course writes them", async () => {
    const pairs = (s: string) => s.match(/\(−?\d+(,\d+)? ; −?\d+(,\d+)?\)/g);
    const french = text(PLOTS.parabola);
    const english = await withLocale("en", () => text(PLOTS.parabola));
    expect(pairs(french)).toEqual(["(0 ; −4)"]);
    expect(pairs(english)).toEqual(pairs(french));
    expect(english).not.toBe(french);
  });
});
