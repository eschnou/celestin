// @vitest-environment jsdom
/** A figure described in English: our sentences change, the course's notation does not
 *  (spec 010 R3.2, R4.2). */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe as group, expect, it } from "vitest";
import { withLocale } from "@/test/locale";
import { ariaLabel, describe } from "../describe";
import { FigureView } from "../figure-view";
import { sanitise } from "../sanitise";
import { NESTED, NUMBER_LINE, PLANE, SETS, UNION } from "./fixtures";

afterEach(cleanup);
const text = (figure: object) => describe(sanitise(figure)).join("\n");

group("describe in English", () => {
  it("names points, and gives coordinates and radii in the course's notation only when shown", () =>
    withLocale("en", () => {
      const circle = { draw: "circle", of: ["A"], radius: 2 };
      const hidden = text({ ...PLANE, shapes: [...(PLANE.shapes ?? []), circle] });
      expect(hidden).toContain("Points: A, B, C");
      expect(hidden).toContain("Circle with centre A");
      expect(hidden).not.toContain("radius");
      const shown = text({ ...PLANE, show_values: true, shapes: [circle] });
      expect(shown).toContain("A(0 ; 0)");
      expect(shown).toContain("and radius 2");
    }));

  it("says each shape", () =>
    withLocale("en", () => {
      const all = text({
        kind: "plane",
        points: { A: [0, 0], B: [2, 0], C: [0, 2], A_1: [1, 1] },
        shapes: [
          { draw: "line", of: ["A", "B"] },
          { draw: "ray", of: ["A", "B"], style: "dashed" },
          { draw: "segment", of: ["A", "C"], marks: 2 },
          { draw: "polygon", of: ["A", "B", "C"], style: "highlight" },
          { draw: "right_angle", of: ["B", "A", "C"] },
          { draw: "vector", of: ["A", "A_1"] },
          { draw: "segment", of: ["B", "C"], marks: 1, label: "$5$ cm" },
        ],
      });
      expect(all).toContain("Line AB");
      expect(all).toContain("Ray [AB (dashed)");
      expect(all).toContain("Segment [AC], marked with 2 ticks");
      expect(all).toContain("Triangle ABC (highlighted)");
      expect(all).toContain("Right angle at A");
      expect(all).toContain("Vector AA₁");
      expect(all).toContain("Segment [BC], marked with 1 tick: $5$ cm");
    }));

  it("withholds interval notation unless values are shown, and writes it as the course does", () =>
    withLocale("en", () => {
      const hidden = text(UNION);
      expect(hidden).not.toMatch(/[[\]]/);
      expect(hidden).toContain("S: drawn from the left up to 2, then from 5 to the right");
      expect(text({ ...UNION, show_values: true })).toContain("S = ]−∞ ; 2] ∪ ]5 ; +∞[");
      expect(text({ ...NUMBER_LINE, convention: "hatched" })).toContain(
        "Hatched part: what does not fit",
      );
    }));

  it("says a number line's numbers and intervals", () =>
    withLocale("en", () => {
      expect(describe(sanitise(NUMBER_LINE))).toEqual([
        "Numbers placed: 0",
        "$S$: drawn from 2 to the right",
      ]);
      expect(
        describe(
          sanitise({
            kind: "number_line",
            convention: "hatched",
            intervals: [
              { start: null, end: 2, closed: "right" },
              { start: 5, end: null, closed: "left" },
            ],
          }),
        ),
      ).toEqual([
        "Interval 1: drawn from the left up to 2, then from 5 to the right",
        "Hatched part: what does not fit",
      ]);
    }));

  it("lists the elements of a diagram of sets zone by zone", () =>
    withLocale("en", () => {
      const all = text(SETS);
      expect(all).toContain("Overlapping sets: Diviseurs de 12, Diviseurs de 18");
      expect(all).toContain("In Diviseurs de 12 and Diviseurs de 18: 1 ; 2 ; 3 ; 6");
      expect(all).toContain("In Diviseurs de 12 only: 4 ; 12");
      expect(all).toContain("Hatched zone: Diviseurs de 12 and Diviseurs de 18");
      const nested = text(NESTED);
      expect(nested).toContain("Inside $\\mathbb{Z}$, outside $\\mathbb{N}$: −3");
      expect(nested).toContain("Inside $\\mathbb{N}$: 0 ; 7");
    }));

  it("labels the figure by its kind", () =>
    withLocale("en", () => {
      expect(ariaLabel(sanitise({ ...PLANE, axes: true }))).toBe(
        "Geometric figure in a coordinate plane",
      );
      expect(ariaLabel(sanitise(NUMBER_LINE))).toBe("Number line");
      expect(ariaLabel(sanitise(SETS))).toBe("Set diagram");
      expect(ariaLabel(null)).toBe("Empty figure");
      expect(describe(null)).toEqual(["Empty figure"]);
    }));

  it("keeps the notation identical to French around different sentences", async () => {
    const french = text({ ...UNION, show_values: true });
    const english = await withLocale("en", () => text({ ...UNION, show_values: true }));
    expect(english).toBe(french); // a named interval is notation all the way
    const planeFr = text({ ...PLANE, show_values: true });
    const planeEn = await withLocale("en", () => text({ ...PLANE, show_values: true }));
    const pairs = (s: string) => s.match(/[A-Z]\(\d+ ; \d+\)/g);
    expect(pairs(planeEn)).toEqual(pairs(planeFr));
    expect(planeEn).not.toBe(planeFr);
  });
});

group("FigureView in English", () => {
  it("words the empty figure and puts the description in the interface language", () =>
    withLocale("en", () => {
      const { container } = render(<FigureView block={{ type: "figure", figure: PLANE }} />);
      const list = container.querySelector("ul.sr-only")!;
      expect(list.getAttribute("lang")).toBe("en");
      expect(list.textContent).toContain("Points: A, B, C");
      expect(screen.getByRole("img").getAttribute("aria-label")).toBe("Geometric figure");
      cleanup();
      const empty = render(<FigureView block={{ type: "figure", figure: "x" } as never} />);
      expect(empty.container.textContent).toContain("Empty figure");
    }));
});
