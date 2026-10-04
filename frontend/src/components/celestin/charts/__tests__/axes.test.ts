import { describe, expect, it } from "vitest";
import { fitLabel, lanes, textWidth, thinned } from "../axes";

describe("axis label layout", () => {
  it("keeps labels above while they fit, and moves a colliding one to the next lane", () => {
    expect(
      lanes([
        { at: 0, text: "7" },
        { at: 100, text: "10,5" },
        { at: 108, text: "11" },
        { at: 140, text: "12,5" },
      ]),
    ).toEqual([0, 0, 1, 0]);
  });

  it("uses a third lane when three labels crowd together", () => {
    const crowded = [100, 106, 112].map((at) => ({ at, text: "10,5" }));
    expect(lanes(crowded)).toEqual([0, 1, 2]);
  });

  it("thins crowded axis labels to every second one, keeping both ends", () => {
    const crowded = [0, 10, 20, 30, 40].map((at) => ({ at, text: "150" }));
    expect(thinned(crowded).map((l) => l.at)).toEqual([0, 20, 40]);
    const roomy = [0, 60, 120].map((at) => ({ at, text: "150" }));
    expect(thinned(roomy)).toHaveLength(3);
  });
});

describe("fitLabel", () => {
  it("keeps a label that fits and shortens one that does not", () => {
    expect(fitLabel("5A", 80)).toBe("5A");
    const long = "Classe de cinquième, option sciences";
    const fitted = fitLabel(long, 80);
    expect(fitted.endsWith("…")).toBe(true);
    expect(textWidth(fitted)).toBeLessThanOrEqual(80);
  });
});
