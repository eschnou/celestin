import { describe as group, expect, it } from "vitest";
import { ariaLabel, describe } from "../describe";
import { sanitise } from "../sanitise";
import { NESTED, NUMBER_LINE, PLANE, SETS, UNION } from "./fixtures";

const text = (figure: object) => describe(sanitise(figure)).join("\n");

group("describe", () => {
  it("names points without their coordinates unless values are shown", () => {
    const circle = { draw: "circle", of: ["A"], radius: 2 };
    const hidden = text({ ...PLANE, shapes: [...(PLANE.shapes ?? []), circle] });
    expect(hidden).toContain("Points : A, B, C");
    expect(hidden).not.toMatch(/\(\d/);
    expect(hidden).toContain("Cercle de centre A");
    expect(hidden).not.toContain("rayon");
    const shown = text({ ...PLANE, show_values: true, shapes: [circle] });
    expect(shown).toContain("A(0 ; 0)");
    expect(shown).toContain("de rayon 2");
  });

  it("says each shape as the course does", () => {
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
      ],
    });
    expect(all).toContain("Droite AB");
    expect(all).toContain("Demi-droite [AB (en pointillés)");
    expect(all).toContain("Segment [AC], codé de 2 traits");
    expect(all).toContain("Triangle ABC (mis en évidence)");
    expect(all).toContain("Angle droit en A");
    expect(all).toContain("Vecteur AA₁");
  });

  it("withholds interval notation unless values are shown", () => {
    const hidden = text(UNION);
    expect(hidden).not.toMatch(/[[\]]/);
    expect(hidden).toContain("S : tracé de la gauche jusqu'à 2, puis de 5 vers la droite");
    expect(text({ ...UNION, show_values: true })).toContain("S = ]−∞ ; 2] ∪ ]5 ; +∞[");
    expect(text({ ...NUMBER_LINE, convention: "hatched" })).toContain("Partie hachurée");
  });

  it("says a number line's numbers and intervals, never its graduations", () => {
    // The graduations follow the board's width; what the course says does not.
    expect(describe(sanitise(NUMBER_LINE))).toEqual([
      "Nombres placés : 0",
      "$S$ : tracé de 2 vers la droite",
    ]);
    expect(text(UNION)).not.toMatch(/de 0 à 7|Droite graduée/);
    // Under hatching, two unlabelled intervals are one solution.
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
      "Intervalle 1 : tracé de la gauche jusqu'à 2, puis de 5 vers la droite",
      "Partie hachurée : ce qui ne convient pas",
    ]);
  });

  it("says a bound by its mark's label, as the drawing writes it", () => {
    const fig = {
      kind: "number_line",
      intervals: [{ start: Math.SQRT2, end: 3, closed: "right" }],
      marks: [{ x: Math.SQRT2, label: "$\\sqrt{2}$" }],
    };
    expect(text(fig)).toContain("Intervalle 1 : tracé de $\\sqrt{2}$ à 3");
    expect(text({ ...fig, show_values: true })).toContain("Intervalle 1 : ]$\\sqrt{2}$ ; 3]");
  });

  it("lists the elements zone by zone", () => {
    const all = text(SETS);
    expect(all).toContain("Dans Diviseurs de 12 et Diviseurs de 18 : 1 ; 2 ; 3 ; 6");
    expect(all).toContain("Dans Diviseurs de 12 seulement : 4 ; 12");
    expect(all).toContain("Zone hachurée : Diviseurs de 12 et Diviseurs de 18");
    const nested = text(NESTED);
    expect(nested).toContain("Dans $\\mathbb{Z}$, hors de $\\mathbb{N}$ : −3");
    expect(nested).toContain("Dans $\\mathbb{N}$ : 0 ; 7");
  });

  it("labels the figure by its kind; the figcaption's MathML copy reads the caption", () => {
    expect(ariaLabel(sanitise({ ...PLANE, axes: true, caption: "Le triangle $ABC$" }))).toBe(
      "Figure géométrique dans un repère",
    );
    expect(ariaLabel(sanitise(NUMBER_LINE))).toBe("Droite graduée");
    expect(ariaLabel(null)).toBe("Figure vide");
  });
});
