// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { withLocale } from "@/test/locale";
import type { PlotBlock } from "@/lib/tutor/types";
import { PlotView } from "../plot-view";
import { PLOTS, type PlotName } from "./fixtures";

afterEach(cleanup);

const mount = (block: PlotBlock) => render(<PlotView block={block} />);
const NAMES = Object.keys(PLOTS) as PlotName[];

/** Every `on…` prop React holds for the rendered elements. */
function handlers(container: HTMLElement): string[] {
  return [...container.querySelectorAll("*")].flatMap((el) =>
    Object.keys(el)
      .filter((k) => k.startsWith("__reactProps"))
      .flatMap((k) =>
        Object.keys((el as unknown as Record<string, Record<string, unknown>>)[k] ?? {}).filter(
          (p) => p.startsWith("on"),
        ),
      ),
  );
}

describe("PlotView", () => {
  it.each(NAMES)("draws the %s plot", (name) => {
    const { container, getByRole } = mount(PLOTS[name]);
    const img = getByRole("img");
    expect(img.getAttribute("aria-label")).toMatch(/^Graphique : /);
    expect(container.querySelector("svg")).not.toBeNull();
    expect(container.querySelectorAll("svg polyline, svg circle, svg path").length).toBeGreaterThan(
      0,
    );
    expect(container.querySelector("p.sr-only")?.textContent).toMatch(
      /^(Repère orthonormé\. )?Axe horizontal/,
    );
    expect(container.textContent).not.toContain("Graphique vide");
  });

  it("typesets Célestin's labels with KaTeX, inline even when written as display maths", () => {
    const { container } = mount({
      ...PLOTS.parabola,
      curves: [{ expr: "x^2-4", label: "$$f$$" }],
    });
    const labels = [...container.querySelectorAll("[data-plot-label]")];
    expect(labels.some((l) => l.querySelector(".katex"))).toBe(true);
    expect(container.querySelector(".katex-display")).toBeNull();
  });

  it("writes only numbers in the SVG, as the course writes them", () => {
    for (const name of NAMES) {
      const { container, unmount } = mount(PLOTS[name]);
      for (const t of container.querySelectorAll("svg text")) {
        expect(t.textContent).toMatch(/^[−\d,\s\u00a0\u202f]*$/);
      }
      unmount();
    }
    const { container } = mount(PLOTS.data);
    const ticks = [...container.querySelectorAll("svg text")].map((t) => t.textContent);
    expect(ticks).toContain("0,5");
    expect(ticks).not.toContain("0.5");
  });

  it("writes labels in the foreground ink, a group's underlined in its colour", () => {
    const { container } = mount(PLOTS.parabola);
    const labels = [...container.querySelectorAll<HTMLElement>("[data-plot-label]")];
    expect(labels).toHaveLength(2);
    for (const label of labels) expect(label.className).toContain("text-foreground");
    const underlined = labels.filter((l) => l.style.borderBottom.includes("var(--chart-"));
    expect(underlined).toHaveLength(1);
  });

  it("never writes an expression, a domain or an endpoint", () => {
    for (const name of NAMES) {
      const { container, unmount } = mount(PLOTS[name]);
      const text = container.textContent ?? "";
      const curves = "curves" in PLOTS[name] ? (PLOTS[name].curves as { expr: string }[]) : [];
      // A constant piece (« 10 ») reads like a tick; every other expression is never text.
      for (const { expr } of curves.filter((c) => /[a-z(^*/]/.test(c.expr))) {
        expect(text).not.toContain(expr);
      }
      expect(text).not.toMatch(/[[\]]|creux|plein/);
      unmount();
    }
  });

  it("writes a point's coordinates only when Célestin shows them", () => {
    const shown = mount(PLOTS.parabola);
    expect(shown.container.textContent).toContain("(0 ; −4)");
    shown.unmount();
    const hidden = mount({ ...PLOTS.parabola, points: [{ x: 0, y: -4, label: "$S$" }] });
    expect(hidden.container.textContent).not.toContain("−4)");
    expect(hidden.container.textContent).not.toContain("(0 ;");
  });

  it("has no tooltip and nothing that reacts to the pointer", () => {
    for (const name of NAMES) {
      const { container, unmount } = mount(PLOTS[name]);
      expect(container.querySelector("svg title")).toBeNull();
      expect(container.querySelector("[title]")).toBeNull();
      expect(handlers(container)).toEqual([]);
      unmount();
    }
  });

  it("animates solid curves only, with the utility reduced motion turns off", () => {
    const { container } = mount(PLOTS.hyperbola);
    const traced = container.querySelectorAll("polyline.chart-trace");
    const dashed = [...container.querySelectorAll("polyline")].filter(
      (p) => p.getAttribute("stroke-dasharray") === "6 4",
    );
    expect(traced.length).toBeGreaterThan(0);
    expect(dashed).toHaveLength(1);
    expect(dashed[0]?.classList.contains("chart-trace")).toBe(false);
  });

  it("renders the caption with its maths, and a copy a screen reader can read", () => {
    const { container } = mount({ ...PLOTS.data, caption: "Graphique de $f$" });
    const caption = container.querySelector("figcaption");
    const [shown, spoken] = [...(caption?.children ?? [])] as HTMLElement[];
    // KaTeX's html is aria-hidden, so the visible copy is hidden whole, prose included.
    expect(shown?.getAttribute("aria-hidden")).toBe("true");
    expect(shown?.querySelector(".katex")).not.toBeNull();
    expect(spoken?.className).toBe("sr-only");
    expect(spoken?.querySelector("math")).not.toBeNull();
    expect(spoken?.textContent).toContain("Graphique de");
  });

  it.each([
    ["a bad expression", { ...PLOTS.parabola, curves: [{ expr: "1/2x" }, { expr: "x" }] }],
    ["a reversed range", { ...PLOTS.parabola, x_range: [4, -4] }],
    ["a range too thin to graduate", { ...PLOTS.parabola, x_range: [0, 1e-200] }],
    ["a step with too many decimals", { ...PLOTS.parabola, x_step: 0.00005 }],
    ["a point that is not a number", { ...PLOTS.parabola, points: [{ x: Number.NaN, y: 1 }] }],
    ["a one-vertex line", { ...PLOTS.parabola, lines: [{ vertices: [[0, 0]] }] }],
    ["curves that are not a list", { ...PLOTS.parabola, curves: "x^2" }],
    ["a missing window", { type: "plot", curves: [{ expr: "x" }] }],
    [
      "labels that are not text",
      { ...PLOTS.parabola, x_title: 3, curves: [{ expr: "x", label: {} }] },
    ],
    ["a hostile expression", { ...PLOTS.parabola, curves: [{ expr: "(".repeat(5000) }] }],
    [
      "a sequence past the largest exact integer",
      { ...PLOTS.sequence, sequences: [{ expr: "n", first: 1e16, last: 1e16 + 3 }] },
    ],
  ])("survives %s", (_, block) => {
    expect(() => mount(block as unknown as PlotBlock)).not.toThrow();
  });

  it("says « Graphique vide » when nothing is left to draw", () => {
    const { container } = mount({
      ...PLOTS.parabola,
      curves: [{ expr: "\\frac{1}{x}" }],
      points: [{ x: 99, y: 99 }],
    });
    expect(container.textContent).toContain("Graphique vide");
    expect(container.querySelector("p.sr-only")?.textContent).toContain("Graphique vide.");
  });

  it("says it in the interface language, visibly and for screen readers", () =>
    withLocale("en", async () => {
      const { container } = mount({
        ...PLOTS.parabola,
        curves: [{ expr: "\\frac{1}{x}" }],
        points: [{ x: 99, y: 99 }],
      });
      expect(container.textContent).toContain("Empty graph");
      expect(container.textContent).not.toContain("Graphique vide");
      expect(container.querySelector("p.sr-only")?.textContent).toContain("Empty graph.");
    }));
});
