// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Figure, FigureBlock, NumberLine } from "@/lib/tutor/types";
import { FigureView } from "../figure-view";
import { lineLayout } from "../line";
import { sanitise, type CleanSets } from "../sanitise";
import { SetDrawing } from "../sets";
import { setsLayout } from "../venn";
import { AXES_ONLY, FIGURES, NESTED, NUMBER_LINE, PLANE, SETS, STATS, UNION } from "./fixtures";

// The real layout, counted: a number line is laid out once per width, by its drawing.
vi.mock("../line", async (importOriginal) => {
  const line = await importOriginal<typeof import("../line")>();
  return { ...line, lineLayout: vi.fn(line.lineLayout) };
});

afterEach(cleanup);

const block = (figure: Figure): FigureBlock => ({ type: "figure", figure });
const mount = (figure: Figure) => render(<FigureView block={block(figure)} />);
const layerSpans = (root: Element) => [...root.querySelectorAll("div.pointer-events-none > span")];

describe("FigureView", () => {
  it.each([
    ...Object.entries(FIGURES),
    ["nested", NESTED],
    ["stats", STATS],
    ["axes", AXES_ONLY],
    ["union", UNION],
  ] as [string, Figure][])("draws the %s figure with a name and a description", (_, figure) => {
    const { container, getByRole } = mount(figure);
    const img = getByRole("img");
    expect(img.getAttribute("aria-label")).toBeTruthy();
    expect(container.querySelector("svg")).not.toBeNull();
    const described = img.getAttribute("aria-describedby") ?? "";
    expect(container.querySelector(`[id="${described}"]`)?.classList.contains("sr-only")).toBe(
      true,
    );
    expect(container.querySelectorAll(".sr-only li").length).toBeGreaterThan(0);
  });

  it("typesets $…$ labels with KaTeX, one line each, and leaves no raw $", () => {
    for (const figure of [PLANE, NUMBER_LINE, NESTED]) {
      const { container, unmount } = mount({ ...figure, caption: "Avec $x$" } as Figure);
      const layer = container.querySelector("div.pointer-events-none");
      expect(layer?.querySelector(".katex")).not.toBeNull();
      expect(container.textContent).not.toContain("$");
      for (const span of layerSpans(container)) expect(span.classList.contains("w-max")).toBe(true);
      unmount();
    }
  });

  it("reads maths in the description as MathML", () => {
    const { container } = mount(NESTED);
    expect(container.querySelector(".sr-only math")).not.toBeNull();
  });

  it("writes coordinates only when Célestin shows the values", () => {
    const hidden = mount(PLANE);
    expect(hidden.container.textContent).not.toContain("(0 ; 0)");
    hidden.unmount();
    const { container } = mount({ ...PLANE, show_values: true });
    const labels = layerSpans(container).map((s) => s.textContent);
    expect(labels).toContain("A(0 ; 0)");
    expect(container.querySelector(".sr-only")?.textContent).toContain("A(0 ; 0)");
  });

  it("writes an interval's notation only when Célestin shows the values", () => {
    const hidden = mount(UNION);
    expect(hidden.container.textContent).not.toContain("]−∞");
    expect(hidden.container.textContent).toContain("S");
    hidden.unmount();
    const { container } = mount({ ...UNION, show_values: true });
    expect(container.textContent).toContain("S = ]−∞ ; 2] ∪ ]5 ; +∞[");
  });

  it("hatches a shaded zone with a pattern, clipped and masked", () => {
    const { container } = mount(SETS);
    expect(container.querySelector("pattern")).not.toBeNull();
    expect(container.querySelector("mask")).not.toBeNull();
    expect(container.querySelector('[data-zone="01"] rect[mask]')).not.toBeNull();
  });

  it("hatches what does not belong on a hatched number line", () => {
    const { container } = mount({ ...NUMBER_LINE, convention: "hatched" });
    const hatch = container.querySelector("pattern")?.id ?? "";
    expect(hatch).not.toBe("");
    expect(container.querySelector(`rect[fill="url(#${hatch})"]`)).not.toBeNull();
  });

  it("hatches the axis once, only where neither unlabelled interval lies", () => {
    // x ≤ 2 ou x ≥ 5 in the hatched convention: ]2 ; 5[, never the whole axis.
    const figure: NumberLine = {
      kind: "number_line",
      convention: "hatched",
      intervals: [
        { start: null, end: 2, closed: "right" },
        { start: 5, end: null, closed: "left" },
      ],
    };
    const { container } = mount(figure);
    const rects = [...container.querySelectorAll("rect[data-hatch]")];
    expect(rects).toHaveLength(1);
    const clean = sanitise(figure);
    if (clean?.kind !== "number_line") throw new Error("a number line expected");
    const layout = lineLayout(clean, Number(container.querySelector("svg")?.getAttribute("width")));
    expect(Number(rects[0]?.getAttribute("x"))).toBeCloseTo(layout.x(2), 6);
    expect(Number(rects[0]?.getAttribute("width"))).toBeCloseTo(layout.x(5) - layout.x(2), 6);
    expect(rects[0]?.getAttribute("fill")).toBe(`url(#${container.querySelector("pattern")?.id})`);
  });

  it("hatches nothing on a hatched line that places numbers but no interval", () => {
    // An empty lane's complement is the whole axis, which would say no number fits.
    const { container } = mount({ kind: "number_line", convention: "hatched", marks: [{ x: 2 }] });
    expect(container.querySelectorAll("rect[data-hatch]")).toHaveLength(0);
  });

  it("lays a number line out once, for its drawing; the description needs no width", () => {
    const counted = vi.mocked(lineLayout);
    counted.mockClear();
    const { container } = mount({ ...UNION, convention: "hatched" });
    expect(counted).toHaveBeenCalledTimes(1);
    expect(container.querySelector(".sr-only")?.textContent).not.toMatch(/Droite graduée de/);
  });

  it("gives two figures on one card distinct ids", () => {
    const { container } = render(
      <>
        <FigureView block={block(SETS)} />
        <FigureView block={block({ ...SETS, shade: [["A"]] })} />
        <FigureView block={block(PLANE)} />
      </>,
    );
    const ids = [...container.querySelectorAll("[id]")].map((el) => el.id);
    expect(ids.length).toBeGreaterThan(4);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("has no tooltip and nothing that reacts to the pointer", () => {
    for (const figure of [PLANE, NUMBER_LINE, SETS, NESTED, UNION]) {
      const { container, unmount } = mount({ ...figure, show_values: true } as Figure);
      expect(container.querySelector("title")).toBeNull();
      const handlers = [...container.querySelectorAll("*")].flatMap((el) =>
        Object.keys(el)
          .filter((k) => k.startsWith("__reactProps"))
          .flatMap((k) =>
            Object.keys((el as unknown as Record<string, Record<string, unknown>>)[k] ?? {}).filter(
              (p) => p.startsWith("on"),
            ),
          ),
      );
      expect(handlers).toEqual([]);
      unmount();
    }
  });

  it.each([
    { kind: "plane", points: "x" },
    { kind: "zzz" },
    { kind: "sets", sets: [] },
    { kind: "number_line", intervals: [{ start: 3, end: 3, closed: "both" }] },
    null,
  ])("renders « Figure vide » for %j without throwing", (figure) => {
    const { container } = render(
      <FigureView block={{ type: "figure", figure } as unknown as FigureBlock} />,
    );
    expect(container.textContent).toContain("Figure vide");
  });

  it("survives shapes that collapse to nothing", () => {
    const broken = {
      kind: "plane",
      points: { A: [0, 0], B: [0, 0], C: [1e308, -1e308] },
      shapes: [
        { draw: "segment", of: ["A", "B"] },
        { draw: "angle", of: ["A", "B", "C"] },
        { draw: "arc", of: ["A", "B", "C"] },
        { draw: "circle", of: ["A", "B"] },
        { draw: "line", of: ["A", "B"] },
        { draw: "vector", of: ["A", "B"], style: "highlight" },
      ],
      axes: true,
    } as unknown as Figure;
    const { container } = mount(broken);
    expect(container.innerHTML).not.toContain("NaN");
  });

  it("draws points at the very same place as one mark", () => {
    const { container } = mount({ kind: "plane", points: { A: [0, 0], "A'": [0, 0], B: [3, 1] } });
    expect(container.querySelectorAll("[data-marker]")).toHaveLength(2);
    expect(layerSpans(container).some((s) => s.textContent?.includes("="))).toBe(true);
  });

  it("marks points with a cross or a dot, as the course does", () => {
    const cross = mount(PLANE);
    expect(cross.container.querySelectorAll('[data-marker="cross"]')).toHaveLength(3);
    expect(cross.container.querySelectorAll('[data-marker="cross"] path')).toHaveLength(6);
    cross.unmount();
    const { container } = mount({ ...PLANE, marker: "dot" });
    expect(container.querySelectorAll('circle[data-marker="dot"]')).toHaveLength(3);
  });

  it("fills an unmarked angle and draws arcs only for a codage", () => {
    const points = { A: [3, 0], B: [0, 0], C: [0, 3], D: [-3, 0] };
    const plain = mount({
      kind: "plane",
      points,
      shapes: [{ draw: "angle", of: ["A", "B", "C"] }],
    });
    const fills = [...plain.container.querySelectorAll("path")].filter((p) =>
      p.getAttribute("class")?.includes("fill-chart-1/30"),
    );
    expect(fills).toHaveLength(1);
    expect(plain.container.querySelectorAll("path[d*=' A ']:not([class*='fill-'])")).toHaveLength(
      0,
    );
    plain.unmount();
    const coded = mount({
      kind: "plane",
      points,
      shapes: [
        { draw: "angle", of: ["A", "B", "C"], marks: 2 },
        { draw: "angle", of: ["C", "B", "D"], marks: 2 },
      ],
    });
    expect(coded.container.querySelectorAll("path[d*=' A ']")).toHaveLength(4);
    expect(coded.container.querySelector("[class*='fill-chart-1/30']")).toBeNull();
  });

  it("never traces a dashed stroke", () => {
    const { container } = mount({
      ...PLANE,
      shapes: [
        { draw: "segment", of: ["A", "B"], style: "dashed" },
        { draw: "segment", of: ["A", "C"] },
      ],
    });
    const dashed = [...container.querySelectorAll("path[stroke-dasharray='6 4']")];
    expect(dashed).toHaveLength(1);
    expect(dashed[0]?.hasAttribute("pathLength")).toBe(false);
    expect(container.querySelectorAll("path.chart-trace[pathLength='1']").length).toBeGreaterThan(
      0,
    );
  });

  it.each([
    ["a number line 1e-100 wide", { kind: "number_line", marks: [{ x: 0 }, { x: 1e-100 }] }],
    ["a number line 1e-300 wide", { kind: "number_line", marks: [{ x: 5 }, { x: 5 + 1e-300 }] }],
    [
      "a gridded plane 1e-100 wide",
      { kind: "plane", points: { A: [0, 0], B: [1e-100, 0] }, grid: true },
    ],
    [
      "a plane 1e12 wide",
      {
        kind: "plane",
        points: { A: [0, 0], B: [1e12, 0], C: [0, 1e12] },
        shapes: [{ draw: "polygon", of: ["A", "B", "C"] }],
      },
    ],
    [
      "a plane a million wide, the largest the tool accepts",
      {
        kind: "plane",
        points: { A: [0, 0], B: [1e6, 0], C: [0, 1e6] },
        shapes: [{ draw: "polygon", of: ["A", "B", "C"] }],
        axes: true,
        grid: true,
      },
    ],
    [
      "a number line a thousandth wide, the smallest the tool accepts",
      { kind: "number_line", marks: [{ x: 0 }, { x: 1e-3 }], show_values: true },
    ],
  ])("draws %s without throwing, NaN or a runaway height", (_, figure) => {
    const { container } = render(
      <FigureView block={{ type: "figure", figure } as unknown as FigureBlock} />,
    );
    expect(container.innerHTML).not.toMatch(/NaN|Infinity/);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(Number(svg?.getAttribute("height"))).toBeLessThanOrEqual(400);
    expect(container.querySelectorAll(".sr-only li").length).toBeGreaterThan(0);
  });

  it("ticks every bound and mark, and dots every mark", () => {
    const { container } = mount({
      kind: "number_line",
      intervals: [{ start: 2, end: 5, closed: "right" }],
      marks: [{ x: 3 }, { x: 4, label: "$a$" }],
    });
    // 2, 3, 4 and 5 each have a 10 px tick; 3 and 4 have a dot.
    const ticks = [...container.querySelectorAll("path")].filter(
      (p) =>
        /^M [\d.]+ [\d.]+ V [\d.]+$/.test(p.getAttribute("d") ?? "") &&
        p.getAttribute("stroke-width") === "1.25",
    );
    expect(ticks).toHaveLength(4);
    expect(container.querySelectorAll("circle[data-mark]")).toHaveLength(2);
  });
});

describe("SetDrawing on a narrow board", () => {
  const fig = sanitise(SETS) as CleanSets;

  it("scales the 294 px layout down below 294 px, and only then", () => {
    const { height } = setsLayout(fig, 294);
    const narrow = render(<SetDrawing fig={fig} width={250} uid="n" />);
    const outer = narrow.container.firstElementChild as HTMLElement;
    const inner = outer.firstElementChild as HTMLElement;
    expect(inner.style.transform).toBe(`scale(${250 / 294})`);
    expect(inner.style.transformOrigin).toBe("top left");
    expect(inner.style.width).toBe("294px");
    expect(parseFloat(outer.style.height)).toBeCloseTo((height * 250) / 294);
    narrow.unmount();
    for (const W of [294, 400]) {
      const wide = render(<SetDrawing fig={fig} width={W} uid="w" />);
      const box = wide.container.firstElementChild?.firstElementChild as HTMLElement;
      expect(box.style.transform).toBe("");
      wide.unmount();
    }
  });
});
