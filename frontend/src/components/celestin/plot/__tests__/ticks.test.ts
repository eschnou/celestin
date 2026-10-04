import { describe, expect, it } from "vitest";
import { autoStep, axisAt, decimalsOf, labelEvery, labelled, stepTicks } from "../ticks";

describe("axisAt", () => {
  it("puts the axis through 0 when the window holds it, with its arrow", () => {
    expect(axisAt(-3, 8)).toEqual({ at: 0, arrow: true });
    expect(axisAt(0, 16)).toEqual({ at: 0, arrow: true });
    expect(axisAt(-5, 0)).toEqual({ at: 0, arrow: true });
  });

  it("otherwise on the edge nearest 0, without an arrow", () => {
    expect(axisAt(2, 10)).toEqual({ at: 2, arrow: false });
    expect(axisAt(-10, -2)).toEqual({ at: -2, arrow: false });
  });
});

describe("steps and ticks", () => {
  it("counts a step's decimals", () => {
    expect(decimalsOf(1)).toBe(0);
    expect(decimalsOf(0.25)).toBe(2);
    expect(decimalsOf(0.1)).toBe(1);
    expect(decimalsOf(2000)).toBe(0);
  });

  it("writes every multiple of the step, without float noise", () => {
    expect(stepTicks(-5, 5, 1)).toHaveLength(11);
    expect(stepTicks(0, 2, 0.25)).toEqual([0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2]);
    expect(stepTicks(-4.9, -4.6, 0.01)).toHaveLength(31);
    expect(stepTicks(0, 0.3, 0.1)).toEqual([0, 0.1, 0.2, 0.3]);
    expect(stepTicks(-1, 1, 1).map((t) => Object.is(t, -0))).toEqual([false, false, false]);
  });

  it("stays bounded on a bad call", () => {
    expect(stepTicks(0, 1, 0)).toEqual([]);
    expect(stepTicks(0, 1e6, 1).length).toBeLessThanOrEqual(200);
  });

  it("picks a round automatic step, whole on a sequence's n axis", () => {
    expect(autoStep(0, 3, 280, true)).toBe(1);
    expect(autoStep(0, 3, 280, false)).toBe(0.5);
    expect(autoStep(-10, 10, 280, false)).toBe(5);
    expect(autoStep(0, 0.001, 280, false)).toBe(0.0002);
  });
});

describe("labelEvery", () => {
  it("thins labels to a round multiple of the step", () => {
    expect(labelEvery(0.1, 9.3, 33)).toBe(5);
    expect(labelEvery(1, 14, 26)).toBe(2);
    expect(labelEvery(2000, 44.8, 46)).toBe(2);
    expect(labelEvery(0.3, 8.4, 33)).toBe(4);
    expect(labelEvery(2, 35, 30)).toBe(1);
  });

  it("anchors labels at 0", () => {
    const ticks = stepTicks(-1.5, 1.5, 0.1);
    const shown = ticks.filter((t) => labelled(t, 0.1, 5));
    expect(shown).toEqual([-1.5, -1, -0.5, 0, 0.5, 1, 1.5]);
  });
});
