import { describe, expect, it } from "vitest";
import { sanitise } from "../graph";
import { arrange } from "../layout";
import { estimateSize, labelSizes, LADDER, measureItems } from "../measure";
import { boxFor, METRICS, rhombusHalf, shapeProps, type Size } from "../shapes";

const m = METRICS.compact;

/** Whether the label rectangle, centred at the origin, lies inside the rhombus. */
const inRhombus = (label: Size, A: number, B: number) =>
  label.w / 2 / A + label.h / 2 / B <= 1 + 1e-9;

describe("boxFor", () => {
  it.each([1, 2, 3])("sizes a rhombus around a %i-line label", (lines) => {
    for (const w of [10, 64, 120, 220]) {
      const label = { w, h: lines * m.line };
      const box = boxFor("decision", label, m, false);
      expect(box.w / box.h).toBeCloseTo(m.rho);
      expect(inRhombus(label, box.A!, box.h / 2)).toBe(true);
    }
  });

  it("leaves the label clear of a parallelogram's slanted sides", () => {
    const label = { w: 90, h: 32 };
    const box = boxFor("io", label, m, false);
    const shape = shapeProps(box, 0, 0, m);
    expect(shape.tag).toBe("polygon");
    // The left side runs from (−w/2 + skew, top) to (−w/2, bottom): at the label's
    // corners it is left of −label.w / 2.
    const top = -label.h / 2;
    const leftAt = (y: number) => -box.w / 2 + (m.skew * (box.h / 2 - y)) / box.h;
    expect(leftAt(top)).toBeLessThan(-label.w / 2);
    expect(leftAt(-top)).toBeLessThan(-label.w / 2);
  });

  it("gives a hidden box one size whatever it hides", () => {
    for (const kind of ["step", "io", "start", "end", "decision"] as const) {
      const small = boxFor(kind, { w: 10, h: 16 }, m, true);
      const large = boxFor(kind, { w: 220, h: 64 }, m, true);
      expect([small.w, small.h]).toEqual([large.w, large.h]);
    }
  });

  it("makes a pill of a start or an end, with room for its rounded ends", () => {
    const box = boxFor("start", { w: 30, h: 16 }, m, false);
    expect(box.rx).toBe(box.h / 2);
    expect(box.w).toBeGreaterThanOrEqual(30 + 2 * m.padX + box.h / 2);
  });
});

describe("a question's label width", () => {
  it("is the rung that makes the smallest rhombus", () => {
    const text = "Les quotients sont-ils égaux ?";
    const sizes = LADDER.map((rung) => estimateSize(text, rung, m.font, m.line));
    const halves = sizes.map((s) => rhombusHalf(s, m));
    const best = Math.min(...halves);
    // A 30-character question wraps to two lines at compact size.
    expect(sizes[halves.indexOf(best)]!.h).toBe(2 * m.line);
    const g = sanitise({
      type: "flowchart",
      nodes: [
        { id: "q", kind: "decision", text, next: [{ to: "a", label: "oui" }] },
        { id: "a", text: "A" },
      ],
    });
    const layout = arrange(g, labelSizes(g, measureItems(g), [], m).sizes, 268);
    expect(layout.nodes[0]!.box.A).toBeCloseTo(best);
  });
});
