import { describe, expect, it } from "vitest";
import {
  classLabel,
  formatBound,
  formatInterval,
  formatNumber,
  formatPair,
  formatValue,
} from "../format";

describe("chart number format", () => {
  it("writes numbers the FWB way", () => {
    expect(formatNumber(0.45)).toBe("0,45");
    expect(formatNumber(12345)).toBe("12\u202f345");
    // A year, or any four-digit number, takes no space.
    expect(formatNumber(2018)).toBe("2018");
    expect(formatNumber(-3)).toBe("−3");
  });

  it("absorbs float noise", () => {
    expect(formatNumber(0.1 + 0.2)).toBe("0,3");
  });

  it("adds the percent sign after a no-break space", () => {
    expect(formatValue(12.5, "pourcentage")).toBe("12,5 %");
    expect(formatValue(12, "effectif")).toBe("12");
    expect(formatValue(0.25, "frequence")).toBe("0,25");
  });

  it("writes a class in the course's interval notation", () => {
    expect(classLabel(10, 20, "left")).toBe("[10 ; 20[");
    expect(classLabel(10, 20, "right")).toBe("]10 ; 20]");
    expect(classLabel(1.5, 2.5, "left")).toBe("[1,5 ; 2,5[");
    expect(classLabel(-2.5, 12500, "right")).toBe("]−2,5 ; 12\u202f500]");
  });
});

describe("coordinates and intervals", () => {
  it("writes a pair of coordinates the FWB way", () => {
    expect(formatPair(2, -1.5)).toBe("(2 ; −1,5)");
    expect(formatPair(12500, 0.25)).toBe("(12\u202f500 ; 0,25)");
    expect(formatPair(0.1 + 0.2, 0)).toBe("(0,3 ; 0)");
  });

  it("writes a bound: a number, text already written, or an infinity", () => {
    expect(formatBound(-0.5, "−∞")).toBe("−0,5");
    expect(formatBound("$\\sqrt{2}$", "+∞")).toBe("$\\sqrt{2}$");
    expect(formatBound(null, "−∞")).toBe("−∞");
    expect(formatBound(null, "+∞")).toBe("+∞");
  });

  it.each([
    [2, 5, true, false, "[2 ; 5["],
    [2, 5, false, true, "]2 ; 5]"],
    [2, 5, true, true, "[2 ; 5]"],
    [2, 5, false, false, "]2 ; 5["],
    [-1.5, 0.25, true, false, "[−1,5 ; 0,25["],
    [null, 2, false, true, "]−∞ ; 2]"],
    [5, null, true, false, "[5 ; +∞["],
    [null, null, false, false, "]−∞ ; +∞["],
    ["$\\sqrt{2}$", 3, false, true, "]$\\sqrt{2}$ ; 3]"],
    [0, "$\\pi$", true, true, "[0 ; $\\pi$]"],
  ] as const)("writes %s to %s (closed %s, %s) as %s", (a, b, left, right, expected) => {
    expect(formatInterval(a, b, left, right)).toBe(expected);
  });

  it("never closes an infinite end, whatever its closure says", () => {
    expect(formatInterval(null, 2, true, true)).toBe("]−∞ ; 2]");
    expect(formatInterval(5, null, true, true)).toBe("[5 ; +∞[");
    expect(formatInterval(null, null, true, true)).toBe("]−∞ ; +∞[");
  });
});
