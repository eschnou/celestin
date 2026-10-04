import { describe, expect, it } from "vitest";
import { formatPair } from "../../charts/format";
import { clampBox, labelSize, Occupancy, placeLabels, plainText, type Box } from "../labels";

describe("plainText", () => {
  it("reads a label as a screen reader should say it", () => {
    expect(plainText("$\\mathcal{C}_f$")).toBe("C indice f");
    expect(plainText("$u_n$")).toBe("u indice n");
    expect(plainText("$u_{n+1}$")).toBe("u indice n+1");
    expect(plainText("$v$ (m/s)")).toBe("v (m/s)");
    expect(plainText("$x^2$")).toBe("x exposant 2");
    expect(plainText("$\\alpha$")).toBe("alpha");
    expect(plainText("$x_0 \\approx 1{,}4$")).toBe("x indice 0 approx 1,4");
    expect(plainText("Position (cm)")).toBe("Position (cm)");
    expect(plainText("")).toBe("");
  });

  it("leaves no dollar, backslash or brace", () => {
    for (const text of [
      "$\\frac{a}{b}$",
      "$\\sqrt{x}$",
      "$$f$$",
      "$\\mathrm{e}^{x}$",
      "$a_{\\text{max}}$",
    ]) {
      expect(plainText(text)).not.toMatch(/[$\\{}_^]/);
    }
  });
});

describe("labelSize and coordinates", () => {
  it("measures maths by its glyphs and prose by its characters", () => {
    expect(labelSize("$f$").width).toBeLessThan(labelSize("f(x) =").width);
    expect(labelSize("$\\mathcal{C}_f$").width).toBeLessThan(40);
    expect(labelSize("x".repeat(24)).width).toBeLessThanOrEqual(200);
    expect(labelSize("", "(2 ; −1,5)").width).toBeGreaterThan(60);
  });

  it("writes coordinates as the course does", () => {
    expect(formatPair(-1.5, 2)).toBe("(−1,5 ; 2)");
    expect(formatPair(12500, 0.25)).toBe("(12\u202f500 ; 0,25)");
  });
});

describe("placeLabels", () => {
  const area = { width: 300, height: 240 };
  const size = { width: 30, height: 20 };

  it("gives two points 3 px apart disjoint boxes", () => {
    const occupancy = new Occupancy(area.width, area.height);
    const [a, b] = placeLabels(
      [
        { candidates: [[150, 120]], ...size },
        { candidates: [[153, 120]], ...size },
      ],
      area,
      occupancy,
    );
    if (!a || !b) throw new Error("two boxes expected");
    const disjoint =
      a.left + a.width <= b.left ||
      b.left + b.width <= a.left ||
      a.top + a.height <= b.top ||
      b.top + b.height <= a.top;
    expect(disjoint).toBe(true);
  });

  it("avoids what is drawn when another place is free", () => {
    const occupancy = new Occupancy(area.width, area.height);
    // A curve through the north-east box of the candidate.
    occupancy.markPath([
      [150, 100],
      [200, 100],
    ]);
    const [box] = placeLabels([{ candidates: [[150, 120]], ...size }], area, occupancy);
    expect(box?.align).toBe("right");
    expect(box && box.left + box.width).toBeLessThanOrEqual(150);
  });

  it("tries the next candidate when every side of the first is taken", () => {
    const occupancy = new Occupancy(area.width, area.height);
    occupancy.markBox({ left: 100, top: 80, width: 100, height: 80 });
    const [box] = placeLabels(
      [
        {
          candidates: [
            [150, 120],
            [40, 200],
          ],
          ...size,
        },
      ],
      area,
      occupancy,
    );
    expect(box?.left).toBe(46);
  });

  it("keeps boxes inside the area, and falls back without throwing", () => {
    const occupancy = new Occupancy(area.width, area.height);
    occupancy.markBox({ left: 0, top: 0, width: 300, height: 240 });
    const boxes = placeLabels(
      [
        { candidates: [[295, 5]], ...size },
        { candidates: [], ...size },
        { candidates: [[10, 10]], width: 500, height: 20 },
      ],
      area,
      occupancy,
    );
    for (const b of boxes) {
      expect(b.left).toBeGreaterThanOrEqual(0);
      expect(b.top).toBeGreaterThanOrEqual(0);
      expect(b.left + b.width).toBeLessThanOrEqual(area.width);
      expect(b.top + b.height).toBeLessThanOrEqual(area.height);
    }
  });

  it("clamps a box into the area", () => {
    expect(clampBox({ left: 290, top: -5, width: 30, height: 20 }, area)).toEqual({
      left: 270,
      top: 0,
      width: 30,
      height: 20,
    });
  });
});
