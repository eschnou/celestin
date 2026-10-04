import type { Figure, NumberLine, PlaneFigure, SetDiagram } from "@/lib/tutor/types";

/**
 * Valid figures, shared by the figure tests and the whiteboard's. They mirror
 * `VALID`, `NESTED`, `STATS` and `AXES_ONLY` in the backend's test_figure_models.py.
 */

export const PLANE: PlaneFigure = {
  kind: "plane",
  points: { A: [0, 0], B: [4, 0], C: [0, 3] },
  shapes: [
    { draw: "polygon", of: ["A", "B", "C"] },
    { draw: "right_angle", of: ["B", "A", "C"] },
    { draw: "segment", of: ["B", "C"], label: "$5$ cm" },
  ],
};

export const NUMBER_LINE: NumberLine = {
  kind: "number_line",
  intervals: [{ start: 2, end: null, closed: "left", label: "$S$" }],
  marks: [{ x: 0 }],
};

export const SETS: SetDiagram = {
  kind: "sets",
  layout: "overlap",
  sets: [
    { id: "A", label: "Diviseurs de 12" },
    { id: "B", label: "Diviseurs de 18" },
  ],
  elements: [
    { text: "4", within: ["A"] },
    { text: "12", within: ["A"] },
    { text: "1", within: ["A", "B"] },
    { text: "2", within: ["A", "B"] },
    { text: "3", within: ["A", "B"] },
    { text: "6", within: ["A", "B"] },
    { text: "9", within: ["B"] },
    { text: "18", within: ["B"] },
  ],
  shade: [["A", "B"]],
};

/** ℕ ⊂ ℤ ⊂ 𝔻 ⊂ ℚ ⊂ ℝ, outermost first; 7 is listed in every set and lands in ℕ. */
export const NESTED: SetDiagram = {
  kind: "sets",
  layout: "nested",
  sets: ["R", "Q", "D", "Z", "N"].map((id) => ({ id, label: `$\\mathbb{${id}}$` })),
  elements: [
    { text: "$\\sqrt{2}$", within: ["R"] },
    { text: "$\\pi$", within: ["R"] },
    { text: "$\\frac{1}{3}$", within: ["Q"] },
    { text: "0,5", within: ["D"] },
    { text: "−3", within: ["Z"] },
    { text: "0", within: ["N"] },
    { text: "7", within: ["N", "Z", "D", "Q", "R"] },
  ],
};

export const STATS: SetDiagram = {
  kind: "sets",
  layout: "nested",
  sets: [
    { id: "P", label: "Population" },
    { id: "E", label: "Échantillon" },
  ],
  elements: [{ text: "individu", within: ["E"] }],
};

export const AXES_ONLY: PlaneFigure = { kind: "plane", axes: true, grid: true };

/** S = ]−∞ ; 2] ∪ ]5 ; +∞[: two pieces, one set. */
export const UNION: NumberLine = {
  kind: "number_line",
  intervals: [
    { start: null, end: 2, closed: "right", label: "S" },
    { start: 5, end: null, closed: "neither", label: "S" },
  ],
};

export const FIGURES = {
  plane: PLANE,
  number_line: NUMBER_LINE,
  sets: SETS,
} satisfies Record<Figure["kind"], Figure>;
