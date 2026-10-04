import { describe as group, expect, it } from "vitest";
import type { PlotBlock } from "@/lib/tutor/types";
import { ariaLabel, describe } from "../describe";
import { layout } from "../layout";
import { sanitise } from "../sanitise";
import { PLOTS, type PlotName } from "./fixtures";

const text = (block: PlotBlock) => {
  const plot = sanitise(block);
  return describe(plot, layout(plot, 320));
};
/** The sentences after the two axes: what is drawn, by name. */
const drawn = (block: PlotBlock) =>
  text(block)
    .split(/(?<=\.) /)
    .filter((s) => !s.startsWith("Axe "));

group("describe", () => {
  it("names the axes, their windows and graduations, and the pieces of one curve", () => {
    const d = text(PLOTS.motion);
    expect(d).toContain("Axe horizontal t (s), de 0 à 16, gradué de 2 en 2.");
    expect(d).toContain("Axe vertical v (m/s), de 0 à 12, gradué de 2 en 2.");
    expect(d).toContain("Une courbe en 3 morceaux.");
  });

  it("names a function by its label, pieces included", () => {
    expect(drawn(PLOTS.piecewise)).toEqual(["Courbe f, en 2 morceaux."]);
    expect(drawn(PLOTS.orthonormal)).toEqual(["Repère orthonormé.", "Courbe d."]);
    expect(drawn(PLOTS.sequence)).toEqual(["Suite u indice n, en points isolés."]);
    expect(drawn(PLOTS.hyperbola)).toEqual(["Courbe h.", "1 tracé en pointillés."]);
    expect(drawn(PLOTS.data)).toEqual(["Une ligne brisée.", "5 points marqués."]);
  });

  it("never gives a domain, an endpoint, an expression or a range of n", () => {
    for (const name of Object.keys(PLOTS) as PlotName[]) {
      const d = text(PLOTS[name]);
      expect(d).not.toMatch(/[[\]]/);
      expect(d).not.toMatch(/creux|plein|ouvert|fermé/);
      expect(d).not.toMatch(/\^|\*|sqrt|\$|\\/);
      for (const sentence of drawn(PLOTS[name])) {
        if (!sentence.includes("("))
          expect(sentence).not.toMatch(/\d(?! (morceaux|points|tracés?))/);
      }
    }
    for (const curve of PLOTS.motion.curves) expect(text(PLOTS.motion)).not.toContain(curve.expr);
  });

  it("gives a point's coordinates only when Célestin writes them", () => {
    expect(text(PLOTS.parabola)).toContain("Point S (0 ; −4).");
    const hidden = { ...PLOTS.parabola, points: [{ x: 0, y: -4, label: "$S$" }] };
    expect(text(hidden)).toContain("Point S.");
    expect(text(hidden)).not.toContain("−4)");
    const guided = { ...PLOTS.parabola, points: [{ x: 0, y: -4, label: "$S$", guides: true }] };
    expect(text(guided)).not.toContain("(0 ; −4)");
  });

  it("says when nothing could be drawn", () => {
    expect(text({ ...PLOTS.parabola, curves: [{ expr: "1/2x" }], points: [] })).toContain(
      "Graphique vide.",
    );
  });
});

group("ariaLabel", () => {
  it("reads the quantities without LaTeX", () => {
    expect(ariaLabel(sanitise(PLOTS.motion))).toBe("Graphique : v (m/s) en fonction de t (s)");
    for (const name of Object.keys(PLOTS) as PlotName[]) {
      expect(ariaLabel(sanitise(PLOTS[name]))).not.toMatch(/[$\\]/);
    }
    expect(ariaLabel(sanitise({ ...PLOTS.motion, x_title: "", y_title: "" }))).toBe("Graphique");
  });
});
