import type { Chart } from "@/lib/tutor/types";

/** One valid chart of each kind, shared by the chart and whiteboard tests. */
export const CHARTS = {
  bars: {
    kind: "bars",
    measure: "effectif",
    categories: ["Vélo", "Bus", "À pied"],
    values: [12, 7, 5],
    y_title: "Effectifs",
  },
  sticks: {
    kind: "sticks",
    measure: "effectif",
    x: [12, 14, 16],
    values: [2, 5, 3],
    polygon: true,
    x_title: "Note",
    y_title: "Effectifs",
  },
  histogram: {
    kind: "histogram",
    measure: "effectif",
    bounds: [150, 160, 180],
    values: [10, 10],
    closed: "left",
    polygon: "closed",
    x_title: "Taille (cm)",
    y_title: "Effectif pour une amplitude de 10",
  },
  cumulative: {
    kind: "cumulative",
    measure: "frequence",
    bounds: [0, 10, 20],
    values: [0.4, 0.6],
    closed: "left",
    direction: "increasing",
    x_title: "Âge",
    y_title: "Fréquences cumulées",
  },
  pie: {
    kind: "pie",
    measure: "pourcentage",
    categories: ["Oui", "Non"],
    values: [62.5, 37.5],
  },
  box: {
    kind: "box",
    boxes: [{ label: "5A", minimum: 4, q1: 9, median: 12, q3: 14, maximum: 19 }],
    x_title: "Note sur 20",
  },
} satisfies Record<Chart["kind"], Chart>;
