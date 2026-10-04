import { describe, expect, it } from "vitest";
import { linear, niceTicks } from "../scale";

describe("niceTicks", () => {
  it("covers a count axis with round steps", () => {
    expect(niceTicks(0, 37).ticks).toEqual([0, 10, 20, 30, 40]);
    expect(niceTicks(0, 12).ticks).toEqual([0, 2, 4, 6, 8, 10, 12]);
  });

  it("handles small decimals without float noise", () => {
    expect(niceTicks(0, 0.37).ticks).toEqual([0, 0.1, 0.2, 0.3, 0.4]);
  });

  it("covers a range that does not start at zero", () => {
    const { lo, hi } = niceTicks(4, 19);
    expect(lo).toBeLessThanOrEqual(4);
    expect(hi).toBeGreaterThanOrEqual(19);
  });

  it("widens a flat domain into a usable one", () => {
    const { lo, hi, ticks } = niceTicks(5, 5);
    expect(lo).toBeLessThan(5);
    expect(hi).toBeGreaterThan(5);
    expect(ticks.length).toBeGreaterThan(1);
    expect(niceTicks(0, 0).hi).toBeGreaterThan(0);
  });

  it("falls back to 0–1 on a non-finite domain (an empty series)", () => {
    expect(niceTicks(0, -Infinity).ticks.at(-1)).toBe(1);
  });
});

describe("linear", () => {
  it("maps the domain onto the range, inverted for SVG's y", () => {
    const y = linear([0, 40], [200, 0]);
    expect(y(0)).toBe(200);
    expect(y(40)).toBe(0);
    expect(y(10)).toBe(150);
  });
});
