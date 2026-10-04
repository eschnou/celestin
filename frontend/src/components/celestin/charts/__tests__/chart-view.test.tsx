// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Chart } from "@/lib/tutor/types";
import { ChartView } from "../chart-view";
import { CHARTS } from "./fixtures";

afterEach(cleanup);

const mount = (chart: Chart) => render(<ChartView block={{ type: "chart", chart }} />);

describe("ChartView", () => {
  it.each(Object.keys(CHARTS) as Chart["kind"][])("draws a %s chart", (kind) => {
    const { container, getByRole } = mount(CHARTS[kind]);
    expect(getByRole("img").getAttribute("aria-label")).toBeTruthy();
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("writes no value on the chart, nor in its table, unless asked", () => {
    const { container } = mount(CHARTS.bars);
    const text = [...container.querySelectorAll("svg text")].map((t) => t.textContent);
    // Axis ticks are numbers too; the bars' values (12, 7, 5) must not be written on marks.
    expect(container.querySelectorAll("svg text.font-semibold")).toHaveLength(0);
    expect(text).toContain("Vélo");
    expect(container.querySelector("table")?.textContent).not.toMatch(/\d/);
  });

  it("writes values when Célestin shows them, as the course writes numbers", () => {
    const { container } = mount({ ...CHARTS.pie, show_values: true });
    expect(container.textContent).toContain("62,5 %");
    expect(container.querySelector("table")?.textContent).toContain("37,5 %");
  });

  it("lists classes in the course's interval notation for screen readers", () => {
    const { container } = mount(CHARTS.histogram);
    const cells = [...container.querySelectorAll("table td")].map((td) => td.textContent);
    expect(cells).toEqual(["[150 ; 160[", "[160 ; 180["]);
  });

  it("names the value column after the measure, never twice the same", () => {
    const { container } = mount({ ...CHARTS.sticks, show_values: true });
    const head = [...container.querySelectorAll("table th")].map((th) => th.textContent);
    expect(head).toEqual(["Valeur", "Effectif"]);
  });

  it("lists a cumulative polygon's points as drawn, cumulated", () => {
    const { container } = mount({ ...CHARTS.cumulative, show_values: true });
    const cells = [...container.querySelectorAll("table tbody tr")].map((tr) =>
      [...tr.querySelectorAll("td")].map((td) => td.textContent),
    );
    expect(cells).toEqual([
      ["0", "0"],
      ["10", "0,4"],
      ["20", "1"],
    ]);
  });

  it("writes a percentage axis with its unit", () => {
    const { container } = mount({ ...CHARTS.bars, measure: "pourcentage", values: [50, 30, 20] });
    const ticks = [...container.querySelectorAll("svg text")].map((t) => t.textContent);
    expect(ticks).toContain("50\u00a0%");
  });

  it("has no tooltip and nothing that reacts to the pointer", () => {
    for (const chart of Object.values(CHARTS)) {
      const { container, unmount } = mount({ ...chart, show_values: true } as Chart);
      expect(container.querySelector("svg title")).toBeNull();
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

  it("shows a caption's maths with KaTeX and reads it from a MathML copy", () => {
    const { container } = mount({ ...CHARTS.sticks, caption: "Notes sur $20$, avec $\\bar{x}$" });
    const caption = container.querySelector("figcaption")!;
    const [visible, spoken] = [...caption.children] as [HTMLElement, HTMLElement];
    expect(caption.children).toHaveLength(2);
    // KaTeX's html is aria-hidden: the visible copy is hidden from screen readers…
    expect(visible.getAttribute("aria-hidden")).toBe("true");
    expect(visible.querySelector(".katex-html")).not.toBeNull();
    expect(visible.textContent).toContain("Notes sur");
    // …which read the sr-only copy, its maths as MathML.
    expect(spoken.classList.contains("sr-only")).toBe(true);
    expect(spoken.querySelectorAll("math")).toHaveLength(2);
    expect(spoken.querySelector(".katex-html")).toBeNull();
    expect(spoken.textContent).toContain("Notes sur");
    expect(caption.textContent).not.toContain("$");
  });

  it("survives a malformed stored chart", () => {
    const broken = { ...CHARTS.bars, values: [Number.NaN, -3] } as Chart;
    const { container } = mount(broken);
    expect(container.textContent).toContain("Graphique vide");
    const short = { ...CHARTS.histogram, values: [10] } as Chart;
    expect(() => mount(short)).not.toThrow();
  });
});
