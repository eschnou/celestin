import { describe, expect, it } from "vitest";
import { sanitise } from "../graph";
import { estimateSize, labelSizes, measureItems, sizesKey } from "../measure";
import { METRICS } from "../shapes";
import { HIDDEN, LOOP, SECRET } from "./fixtures";

const [font, line] = [12, 16];

describe("estimateSize", () => {
  it("wraps on words at the max width", () => {
    const one = estimateSize("Calculer les différences", 400, font, line);
    expect(one.h).toBe(line);
    const wrapped = estimateSize(
      "Calculer les différences entre termes consécutifs",
      120,
      font,
      line,
    );
    expect(wrapped.h).toBeGreaterThan(line);
    expect(wrapped.w).toBeLessThanOrEqual(120);
  });

  it("lets a word or a formula wider than the max width stick out, as min-content does", () => {
    const word = estimateSize("anticonstitutionnellement", 64, font, line);
    expect(word.w).toBeGreaterThan(64);
    expect(word.h).toBe(line);
    const formula = estimateSize("$u_{n+1} - u_n = r \\cdot n$", 30, font, line);
    expect(formula.w).toBeGreaterThan(30);
    expect(formula.h).toBe(line);
  });

  it("counts glyphs, not TeX source, and makes a fraction taller", () => {
    const command = estimateSize("$\\leqslant$", 220, font, line);
    const letter = estimateSize("$x$", 220, font, line);
    expect(command.w).toBe(letter.w);
    const frac = estimateSize("$\\frac{a}{b}$", 220, font, line);
    expect(frac.h).toBeGreaterThan(line);
  });
});

describe("measureItems", () => {
  it("measures every visible node at each rung and every exit label, never a hidden text", () => {
    const g = sanitise(HIDDEN);
    const items = measureItems(g);
    expect(items.filter((i) => i.kind === "node")).toHaveLength(5 * 5);
    expect(items.filter((i) => i.kind === "edge").map((i) => i.text)).toEqual([
      "oui",
      "non",
      "oui",
    ]);
    expect(JSON.stringify(items)).not.toContain(SECRET);
  });

  it("falls back to estimates for what measured 0, and says so", () => {
    const g = sanitise(LOOP);
    const items = measureItems(g);
    const measured = items.map(() => ({ w: 40, h: 16 }));
    expect(labelSizes(g, items, measured, METRICS.normal).estimated).toBe(false);
    measured[0] = { w: 0, h: 0 };
    const { sizes, estimated } = labelSizes(g, items, measured, METRICS.normal);
    expect(estimated).toBe(true);
    expect(sizes.node[0]![0]!.w).toBeGreaterThan(0);
  });

  it("keys the measurements on the texts and fonts, not the width", () => {
    const items = measureItems(sanitise(LOOP));
    expect(sizesKey(items, METRICS.normal)).toBe(sizesKey(items, METRICS.normal));
    expect(sizesKey(items, METRICS.normal)).not.toBe(sizesKey(items, METRICS.compact));
  });
});
