import { describe, expect, it } from "vitest";
import type { PlotBlock } from "@/lib/tutor/types";
import { textWidth } from "../../charts/axes";
import type { Box } from "../labels";
import { layout, type Scene } from "../layout";
import { sanitise } from "../sanitise";
import { PLOTS, type PlotName } from "./fixtures";

const scene = (block: PlotBlock, width = 320) => layout(sanitise(block), width);

/** Realistic plots that stress the corners and the title band, beside the fixtures. */
const CORNERS = {
  // The vertical axis on the right edge: the y title goes left of it.
  rightAxis: {
    type: "plot",
    x_range: [-10, 1],
    y_range: [-2, 6],
    x_title: "$x$",
    y_title: "$f(x)$",
    curves: [{ expr: "0.5x+4", label: "$f$" }],
  },
  rightEdge: {
    type: "plot",
    x_range: [-10, -2],
    y_range: [-9, 2],
    x_title: "$x$",
    y_title: "$f(x)$",
    curves: [{ expr: "x/2+1", label: "$f$" }],
  },
  longTitle: {
    type: "plot",
    x_range: [-5, 5],
    y_range: [-4, 4],
    x_title: "$x$",
    y_title: "Distance parcourue par la bille (cm)",
    curves: [{ expr: "x" }],
  },
  // Both axes on edges, a corner shared by two first graduations.
  years: {
    type: "plot",
    x_range: [1990, 2030],
    y_range: [0, 250000],
    x_title: "Année",
    y_title: "Population",
    x_step: 10,
    curves: [{ expr: "5000(x-1990)" }],
  },
  // The vertical axis inside, the horizontal one on the bottom edge (y from 2).
  bottomEdge: {
    type: "plot",
    x_range: [-3, 3],
    y_range: [2, 12],
    x_title: "$x$",
    y_title: "$y$",
    x_step: 1,
    y_step: 2,
    curves: [{ expr: "x^2+3" }],
  },
  // The horizontal axis inside, the vertical one on the left edge (from 1990).
  leftEdge: {
    type: "plot",
    x_range: [1990, 2030],
    y_range: [-5, 5],
    x_title: "Année",
    y_title: "Écart (°C)",
    x_step: 10,
    curves: [{ expr: "(x-2010)/5" }],
  },
  bothEdges: {
    type: "plot",
    x_range: [-10, -2],
    y_range: [-8, -1],
    x_title: "$x$",
    y_title: "$y$",
    x_step: 1,
    y_step: 1,
    curves: [{ expr: "x/2" }],
  },
  topAxis: {
    type: "plot",
    x_range: [-4, 4],
    y_range: [-9, -1],
    x_title: "$x$",
    y_title: "$y$",
    curves: [{ expr: "-x^2-1" }],
  },
  vertex: {
    type: "plot",
    x_range: [-2, 3],
    y_range: [-3, 5],
    x_title: "$x$",
    y_title: "$y$",
    x_step: 0.5,
    y_step: 0.5,
    curves: [{ expr: "x^2-x-2", label: "$\\mathcal{C}_f$" }],
    points: [
      { x: 0.5, y: -2.25, label: "$S$" },
      { x: -1, y: 0, label: "$A$" },
      { x: 2, y: 0, label: "$B$" },
    ],
  },
  guides: {
    type: "plot",
    x_range: [-1, 5],
    y_range: [-1, 10],
    x_title: "$x$",
    y_title: "$y$",
    x_step: 1,
    y_step: 1,
    curves: [{ expr: "x^2/2", label: "$f$" }],
    points: [{ x: 3, y: 4.5, label: "$P$", guides: true, show_values: true }],
  },
} satisfies Record<string, PlotBlock>;

/** Where each tick label's ink is, from the scene (12 px digits, see layout.ts). */
function tickInk(s: Scene): (Box & { name: string })[] {
  const out: (Box & { name: string })[] = [];
  for (const t of s.xAxis.ticks) {
    if (!t.label) continue;
    const w = textWidth(t.label);
    out.push({
      left: t.px + t.shift - w / 2,
      top: s.xAxis.pos + 7,
      width: w,
      height: 11,
      name: `x ${t.label}`,
    });
  }
  for (const t of s.yAxis.ticks) {
    if (!t.label) continue;
    const w = textWidth(t.label);
    out.push({
      left: s.yAxis.pos - 6 - w,
      top: t.px + t.shift - 5,
      width: w,
      height: 11,
      name: `y ${t.label}`,
    });
  }
  if (s.origin) {
    const w = textWidth("0");
    out.push({ left: s.origin.x - w, top: s.origin.y - 9, width: w, height: 11, name: "origin" });
  }
  for (const f of s.feet) {
    const w = textWidth(f.text);
    const left = f.anchor === "end" ? f.x - w : f.x - w / 2;
    out.push({
      left,
      top: f.anchor === "end" ? f.y - 5 : f.y - 9,
      width: w,
      height: 11,
      name: `foot ${f.text}`,
    });
  }
  return out;
}

/** The axes' lines and arrow heads. */
function axisMarks(s: Scene): (Box & { name: string })[] {
  const { xAxis, yAxis } = s;
  const out = [
    {
      left: xAxis.from,
      top: xAxis.pos - 0.6,
      width: xAxis.to - xAxis.from,
      height: 1.2,
      name: "x axis",
    },
    {
      left: yAxis.pos - 0.6,
      top: yAxis.to,
      width: 1.2,
      height: yAxis.from - yAxis.to,
      name: "y axis",
    },
  ];
  if (xAxis.arrow)
    out.push({ left: xAxis.to - 10, top: xAxis.pos - 3.5, width: 10, height: 7, name: "x arrow" });
  if (yAxis.arrow)
    out.push({ left: yAxis.pos - 3.5, top: yAxis.to, width: 7, height: 10, name: "y arrow" });
  return out;
}

/** Every collision between what is written on a plot, by name; empty when it reads cleanly. */
function collisions(s: Scene): string[] {
  const ink = tickInk(s);
  const marks = axisMarks(s);
  const texts = [
    ...s.labels.map((l) => ({ ...l, name: `label ${l.text ?? l.coords ?? ""}` })),
    ...(s.xTitle ? [{ ...s.xTitle, name: "x title" }] : []),
    ...(s.yTitle ? [{ ...s.yTitle, name: "y title" }] : []),
  ];
  const out: string[] = [];
  for (const a of texts) {
    for (const b of [...ink, ...marks.filter((m) => m.name.endsWith("arrow"))]) {
      if (overlap(a, b)) out.push(`${a.name} on ${b.name}`);
    }
    if (a.left < 0 || a.left + a.width > s.width || a.top < 0 || a.top + a.height > s.height)
      out.push(`${a.name} outside`);
  }
  for (const a of ink) for (const m of marks) if (overlap(a, m)) out.push(`${a.name} on ${m.name}`);
  const all = [...ink, ...texts];
  for (let i = 0; i < all.length; i += 1) {
    for (let j = i + 1; j < all.length; j += 1) {
      const a = all[i] as Box & { name: string };
      const b = all[j] as Box & { name: string };
      if (overlap(a, b)) out.push(`${a.name} on ${b.name}`);
    }
  }
  return out;
}

const overlap = (a: Box, b: Box) =>
  a.left < b.left + b.width &&
  b.left < a.left + a.width &&
  a.top < b.top + b.height &&
  b.top < a.top + a.height;

/** The px of a data point, from the scene's frame and window. */
const at = (s: Scene, x: number, y: number) => ({
  x: s.frame.left + ((x - s.win.x0) / (s.win.x1 - s.win.x0)) * (s.frame.right - s.frame.left),
  y: s.frame.bottom - ((y - s.win.y0) / (s.win.y1 - s.win.y0)) * (s.frame.bottom - s.frame.top),
});

describe("layout: size and frame", () => {
  it("is three quarters as tall as wide, between 240 and 420 px", () => {
    expect(scene(PLOTS.parabola, 320).height).toBe(240);
    expect(scene(PLOTS.parabola, 800).height).toBe(420);
    expect(scene(PLOTS.parabola, 320).xTitleBelow).toBe(false);
  });

  it("keeps the units equal on both axes when orthonormal", () => {
    const s = scene(PLOTS.orthonormal, 320);
    const xUnit = (s.frame.right - s.frame.left) / 10;
    const yUnit = (s.frame.bottom - s.frame.top) / 6;
    expect(Math.abs(xUnit - yUnit) / xUnit).toBeLessThan(0.005);
    expect(s.xAxis.step).toBe(1);
  });

  it("uses the x step for an orthonormal y axis when Célestin gave none", () => {
    const s = scene({ ...PLOTS.orthonormal, x_step: null, y_step: null }, 320);
    expect(s.yAxis.step).toBe(s.xAxis.step);
  });

  it("gives an orthonormal plot square cells when Célestin gave one step", () => {
    // Automatic, the y step on [−2 ; 4] would be 2: a 1 × 2 grid, no slopes to read.
    expect(scene({ ...PLOTS.orthonormal, y_step: null }).yAxis.step).toBe(1);
    expect(scene({ ...PLOTS.orthonormal, x_step: null }).xAxis.step).toBe(1);
    expect(scene({ ...PLOTS.orthonormal, x_step: 2, y_step: null }).yAxis.step).toBe(2);
    // Not orthonormal: each axis its own step.
    expect(scene({ ...PLOTS.orthonormal, orthonormal: false, y_step: null }).yAxis.step).toBe(2);
    // A step wider than the other window stays on its own axis.
    expect(scene({ ...PLOTS.orthonormal, x_step: 10, y_step: null }).yAxis.step).not.toBe(10);
  });

  it("widens the left margin for the labels of a vertical axis on the edge, without an arrow", () => {
    const edge = scene({ ...PLOTS.parabola, x_range: [2, 10], y_range: [-1000, 1000], points: [] });
    const through = scene({
      ...PLOTS.parabola,
      x_range: [-4, 4],
      y_range: [-1000, 1000],
      points: [],
    });
    expect(edge.yAxis.arrow).toBe(false);
    expect(edge.yAxis.pos).toBe(edge.frame.left);
    expect(edge.frame.left).toBeGreaterThan(30);
    for (const t of edge.yAxis.ticks.filter((t) => t.label)) {
      expect(edge.yAxis.pos - 6 - (t.label?.length ?? 0) * 6.72).toBeGreaterThanOrEqual(0);
    }
    expect(through.yAxis.arrow).toBe(true);
  });

  it("writes a single « 0 » at the origin", () => {
    const s = scene(PLOTS.parabola);
    expect(s.origin).not.toBeNull();
    expect(s.xAxis.ticks.find((t) => t.value === 0)?.label).toBeNull();
    expect(s.yAxis.ticks.find((t) => t.value === 0)?.label).toBeNull();
    const edge = scene({ ...PLOTS.parabola, x_range: [2, 10], points: [] });
    expect(edge.origin).toBeNull();
  });

  it("thins 31 graduations at 300 px without overlap, keeping every tick", () => {
    const s = scene(
      { ...PLOTS.parabola, x_range: [-1.5, 1.5], x_step: 0.1, curves: [{ expr: "x" }], points: [] },
      300,
    );
    expect(s.xAxis.ticks).toHaveLength(31);
    const labelled = s.xAxis.ticks.filter((t) => t.label !== null);
    expect(labelled.map((t) => t.label)).toEqual(["−1,5", "−1", "−0,5", "0,5", "1", "1,5"]);
    for (let i = 1; i < labelled.length; i += 1) {
      const gap = (labelled[i]?.px ?? 0) - (labelled[i - 1]?.px ?? 0);
      expect(gap).toBeGreaterThan(30);
    }
  });

  it("never draws below 160 px, nor from a width that is not a number", () => {
    expect(scene(PLOTS.parabola, 0).width).toBe(160);
    expect(scene(PLOTS.parabola, Number.NaN).width).toBe(160);
  });
});

describe("layout: what is drawn", () => {
  it("draws the three pieces of a motion in one colour", () => {
    const s = scene(PLOTS.motion);
    expect(s.runs).toHaveLength(3);
    expect(new Set(s.runs.map((r) => r.colour))).toEqual(new Set(["var(--chart-1)"]));
    expect(s.legend).toEqual([{ label: null, curves: 3, sequences: 0, lines: 0 }]);
  });

  it("moves the motion's x title under the plot, where the last piece ends at the arrow", () => {
    const s = scene(PLOTS.motion, 560);
    expect(s.xTitleBelow).toBe(true);
    expect(s.height).toBe(420 + 22);
    expect(s.xTitle?.top).toBeGreaterThan(s.frame.bottom);
    expect(s.yTitle && s.yTitle.top + s.yTitle.height).toBeLessThanOrEqual(s.frame.top);
  });

  it("keeps the parabola's x title at the arrow, over the axis", () => {
    const s = scene(PLOTS.parabola);
    expect(s.xTitleBelow).toBe(false);
    expect(s.xTitle && s.xTitle.top + s.xTitle.height).toBeLessThanOrEqual(s.xAxis.pos);
  });

  it("puts the endpoint dots where the pieces end, hollow and filled", () => {
    const s = scene(PLOTS.piecewise);
    const hollow = s.endpoints.find((e) => e.hollow);
    const filled = s.endpoints.find((e) => !e.hollow);
    const h = at(s, 1, 2);
    const f = at(s, 1, 4);
    expect(hollow?.x).toBeCloseTo(h.x, 0);
    expect(hollow?.y).toBeCloseTo(h.y, 0);
    expect(filled?.x).toBeCloseTo(f.x, 0);
    expect(filled?.y).toBeCloseTo(f.y, 0);
  });

  it("draws a sequence's terms as dots, and a dashed asymptote muted", () => {
    expect(scene(PLOTS.sequence).dots).toHaveLength(7);
    const s = scene(PLOTS.hyperbola);
    expect(s.runs.filter((r) => r.dashed)).toEqual([
      expect.objectContaining({ colour: "var(--muted-foreground)" }),
    ]);
    expect(s.dashed).toEqual([null]);
  });

  it("writes values at the feet of reading guides, dropping the tick labels they cover", () => {
    const s = scene({
      ...PLOTS.parabola,
      x_step: 1,
      points: [{ x: 1.2, y: -2.56, guides: true, show_values: true }],
    });
    expect(s.guides).toHaveLength(2);
    expect(s.feet.map((f) => f.text)).toEqual(["1,2", "−2,56"]);
    const foot = s.feet[0];
    for (const t of s.xAxis.ticks) {
      // A tick label never sits over a foot; far enough away, it stays.
      if (t.label && foot) expect(Math.abs(t.px - foot.x)).toBeGreaterThan(14);
    }
    expect(s.xAxis.ticks.find((t) => t.value === 1)?.label).toBeNull();
    expect(s.xAxis.ticks.find((t) => t.value === 1)).toBeDefined(); // the mark stays
    expect(s.xAxis.ticks.find((t) => t.value === 3)?.label).toBe("3");
  });

  it("writes a point's coordinates only when asked, and never at the feet without guides", () => {
    const shown = scene(PLOTS.parabola);
    expect(shown.labels.find((l) => l.coords)?.coords).toBe("(0 ; −4)");
    expect(shown.feet).toEqual([]);
    const hidden = scene({ ...PLOTS.parabola, points: [{ x: 0, y: -4, label: "$S$" }] });
    expect(hidden.labels.every((l) => l.coords === null)).toBe(true);
  });

  it("is not drawable when the only curve failed to compile", () => {
    const s = scene({ ...PLOTS.parabola, curves: [{ expr: "1/2x" }], points: [] });
    expect(s.drawable).toBe(false);
    expect(scene(PLOTS.parabola).drawable).toBe(true);
  });
});

describe("layout: at 400 px", () => {
  // A 400 px board leaves about 320 px inside the card's padding.
  it.each(Object.keys(PLOTS) as PlotName[])("%s: labels and titles fit, apart", (name) => {
    const s = scene(PLOTS[name], 320);
    const boxes: Box[] = [
      ...s.labels,
      ...(s.xTitle ? [s.xTitle] : []),
      ...(s.yTitle ? [s.yTitle] : []),
    ];
    for (const b of boxes) {
      expect(b.left).toBeGreaterThanOrEqual(0);
      expect(b.left + b.width).toBeLessThanOrEqual(s.width);
      expect(b.top).toBeGreaterThanOrEqual(0);
      expect(b.top + b.height).toBeLessThanOrEqual(s.height);
    }
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        expect(overlap(boxes[i] as Box, boxes[j] as Box)).toBe(false);
      }
    }
    expect(s.drawable).toBe(true);
  });

  const ALL = { ...PLOTS, ...CORNERS } as Record<string, PlotBlock>;
  it.each(Object.keys(ALL).flatMap((name) => [300, 320, 360, 560].map((w) => [name, w] as const)))(
    "%s at %i px: no title, label, tick label, arrow or axis line on another",
    (name, width) => {
      expect(collisions(scene(ALL[name] as PlotBlock, width))).toEqual([]);
    },
  );

  it("underlines a group's label in the group's colour, never a point's", () => {
    const s = scene(PLOTS.parabola);
    const group = s.labels.find((l) => l.text === "$f$");
    const point = s.labels.find((l) => l.text === "$S$");
    expect(group?.colour).toBe("var(--chart-1)");
    expect(point?.colour).toBeNull();
  });

  it("gives the two pieces of f one label", () => {
    expect(scene(PLOTS.piecewise).labels.filter((l) => l.text === "$f$")).toHaveLength(1);
  });
});

describe("layout: the y title", () => {
  it("sits right of the arrow when it fits, over a plot starting 24 px down", () => {
    const s = scene(PLOTS.parabola);
    expect(s.yTitle?.align).toBe("left");
    expect(s.yTitle?.left).toBeGreaterThan(s.yAxis.pos);
    expect(s.frame.top).toBe(24);
  });

  it.each(["rightAxis", "rightEdge"] as const)(
    "goes left of an axis near the right edge, the plot moving down under it (%s)",
    (name) => {
      const s = scene(CORNERS[name]);
      const title = s.yTitle as Box;
      expect(s.yTitle?.align).toBe("right");
      expect(title.left + title.width).toBeLessThan(s.yAxis.pos);
      expect(s.frame.top).toBe(30);
      // The top graduation keeps its label, clear under the title.
      const top = s.yAxis.ticks.filter((t) => t.label).sort((a, b) => a.px - b.px)[0];
      expect(top?.px).toBeDefined();
      expect((top?.px ?? 0) - 7).toBeGreaterThan(title.top + title.height);
    },
  );

  it("gets a row of its own when neither side has room, over the arrow", () => {
    const s = scene(CORNERS.longTitle);
    const title = s.yTitle as Box;
    expect(title.left).toBeGreaterThanOrEqual(0);
    expect(title.left + title.width).toBeLessThanOrEqual(s.width);
    expect(s.yAxis.arrow).toBe(true);
    expect(s.yAxis.to).toBeGreaterThanOrEqual(title.top + title.height + 2);
    expect(s.yAxis.ticks.find((t) => t.value === 4)?.label).toBe("4");
  });
});

describe("layout: axes on the window's edges", () => {
  it("moves a corner label off the other axis's line", () => {
    // Both axes on edges: x on the top (y < 0), y on the right (x < 0).
    const s = scene({
      ...PLOTS.parabola,
      x_range: [-10, -2],
      y_range: [-8, -1],
      curves: [{ expr: "x/2" }],
      points: [],
    });
    expect(s.xAxis.arrow || s.yAxis.arrow).toBe(false);
    const corner = s.xAxis.ticks.find((t) => t.value === -2);
    expect(corner?.label).toBe("−2");
    // Right-aligned 3 px left of the vertical axis, rather than across it.
    expect((corner?.px ?? 0) + (corner?.shift ?? 0) + textWidth("−2") / 2).toBeCloseTo(
      s.yAxis.pos - 3,
      5,
    );
    expect(s.xAxis.ticks.find((t) => t.value === -4)).toMatchObject({ label: "−4", shift: 0 });
    expect(s.xTitleBelow).toBe(true);
  });

  it("gives a shared corner to the y label when both would move into each other", () => {
    const s = scene(CORNERS.bothEdges);
    // −1 on the top edge moves down; −2 would move left, onto it.
    expect(s.yAxis.ticks.find((t) => t.value === -1)).toMatchObject({ label: "−1", shift: 7 });
    expect(s.xAxis.ticks.find((t) => t.value === -2)?.label).toBeNull();
    expect(s.xAxis.ticks.find((t) => t.value === -3)?.label).toBe("−3");
  });

  it("lifts the window's first value off an edge axis crossing the vertical one", () => {
    const s = scene(CORNERS.bottomEdge);
    expect(s.xAxis.pos).toBe(s.frame.bottom);
    expect(s.yAxis.ticks.find((t) => t.value === 2)).toMatchObject({ label: "2", shift: -8 });
    // Too close to the next graduation to tell whose it is: no label.
    const tight = scene({ ...CORNERS.bottomEdge, y_step: 0.5 });
    expect(tight.yAxis.ticks.find((t) => t.value === 2)?.label).toBeNull();
    expect(tight.yAxis.ticks.find((t) => t.value === 3)?.label).toBe("3");
  });

  it("sidesteps the first year off the vertical axis on the left edge", () => {
    const s = scene(CORNERS.leftEdge);
    const first = s.xAxis.ticks.find((t) => t.value === 1990);
    expect(first?.label).toBe("1990");
    expect(first?.shift).toBeCloseTo(textWidth("1990") / 2 + 3, 5);
  });

  it("keeps both first graduations where two edge axes meet", () => {
    const s = scene(CORNERS.years);
    expect(s.xAxis.ticks.find((t) => t.value === 1990)).toMatchObject({ label: "1990", shift: 0 });
    expect(s.yAxis.ticks.find((t) => t.value === 0)).toMatchObject({ label: "0", shift: 0 });
  });

  it("keeps a corner label outside the frame", () => {
    const s = scene({ ...PLOTS.parabola, x_range: [2, 10], y_range: [100, 1000], points: [] });
    expect(s.xAxis.pos).toBe(s.frame.bottom);
    expect(s.xAxis.ticks.find((t) => t.value === 2)?.label).toBe("2");
  });
});
