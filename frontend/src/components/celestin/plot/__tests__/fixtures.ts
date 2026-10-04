import type { PlotBlock } from "@/lib/tutor/types";

/**
 * One valid plot per use the design names (specs/009-board-drawings/plot.md
 * §2.3), the same seven as the backend's `tests/unit/test_plot_models.py`
 * VALID. Shared by the plot and whiteboard tests.
 */
export const PLOTS = {
  parabola: {
    type: "plot",
    x_range: [-4, 4],
    y_range: [-5, 6],
    x_title: "$x$",
    y_title: "$y$",
    curves: [{ expr: "x^2-4", label: "$f$" }],
    points: [{ x: 0, y: -4, label: "$S$", show_values: true }],
  },
  motion: {
    type: "plot",
    x_range: [0, 16],
    y_range: [0, 12],
    x_title: "$t$ (s)",
    y_title: "$v$ (m/s)",
    x_step: 2,
    y_step: 2,
    curves: [
      { expr: "2t", domain: [0, 5] },
      { expr: "10", domain: [5, 12] },
      { expr: "10-2.5(t-12)", domain: [12, 16] },
    ],
  },
  sequence: {
    type: "plot",
    x_range: [0, 8],
    y_range: [0, 22],
    x_title: "$n$",
    y_title: "$u_n$",
    x_step: 1,
    sequences: [{ expr: "2+3(n-1)", last: 7, label: "$u_n$" }],
  },
  hyperbola: {
    type: "plot",
    x_range: [-4, 6],
    y_range: [-5, 5],
    x_title: "$x$",
    y_title: "$y$",
    curves: [{ expr: "1/(x-1)", label: "$h$" }],
    lines: [
      {
        vertices: [
          [1, -5],
          [1, 5],
        ],
        dashed: true,
      },
    ],
  },
  piecewise: {
    type: "plot",
    x_range: [-3, 4],
    y_range: [-3, 5],
    x_title: "$x$",
    y_title: "$y$",
    curves: [
      { expr: "x+1", domain: [-3, 1], end_dot: "hollow", label: "$f$" },
      { expr: "4", domain: [1, 4], start_dot: "filled", label: "$f$" },
    ],
  },
  data: {
    type: "plot",
    x_range: [0, 2.5],
    y_range: [0, 60],
    x_title: "$t$ (s)",
    y_title: "$x$ (cm)",
    x_step: 0.5,
    y_step: 10,
    points: [
      { x: 0, y: 0, mark: "cross" },
      { x: 0.5, y: 12, mark: "cross" },
      { x: 1, y: 24, mark: "cross" },
      { x: 1.5, y: 36, mark: "cross" },
      { x: 2, y: 48, mark: "cross" },
    ],
    lines: [
      {
        vertices: [
          [0, 0],
          [2, 48],
        ],
      },
    ],
    caption: "Position de la bille (toutes les 0,5 s)",
  },
  orthonormal: {
    type: "plot",
    x_range: [-5, 5],
    y_range: [-2, 4],
    x_title: "$x$",
    y_title: "$y$",
    x_step: 1,
    y_step: 1,
    orthonormal: true,
    curves: [{ expr: "0.5x+1", label: "$d$" }],
  },
} satisfies Record<string, PlotBlock>;

export type PlotName = keyof typeof PLOTS;
