// @vitest-environment jsdom
/** A chart in English: its names and table headers follow the interface, the vocabulary the
 *  board draws from the course (« Effectif », « Médiane ») and the notation do not. */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Chart } from "@/lib/tutor/types";
import { withLocale } from "@/test/locale";
import { ChartView } from "../chart-view";
import { CHARTS } from "./fixtures";

afterEach(cleanup);

const mount = (chart: Chart) => render(<ChartView block={{ type: "chart", chart }} />);
const head = (container: HTMLElement) =>
  [...container.querySelectorAll("table th")].map((th) => th.textContent);

describe("ChartView in English", () => {
  it("names each kind of chart", () =>
    withLocale("en", () => {
      const names: Record<Chart["kind"], string> = {
        bars: "Bar chart",
        sticks: "Stick chart",
        histogram: "Histogram",
        cumulative: "Cumulative polygon",
        pie: "Pie chart",
        box: "Box plot",
      };
      for (const [kind, name] of Object.entries(names) as [Chart["kind"], string][]) {
        const { getByRole, unmount } = mount(CHARTS[kind]);
        expect(getByRole("img").getAttribute("aria-label")).toContain(name);
        unmount();
      }
    }));

  it("words the first column and keeps the measure's name, the course's, under en", () =>
    withLocale("en", () => {
      const { container } = mount({ ...CHARTS.sticks, show_values: true });
      expect(head(container)).toEqual(["Value", "Effectif"]);
      cleanup();
      const bars = mount({ ...CHARTS.bars, show_values: true });
      expect(head(bars.container)[0]).toBe("Category");
    }));

  it("keeps the statistics vocabulary of a box plot, and words a missing series label", () =>
    withLocale("en", () => {
      const box = CHARTS.box as Extract<Chart, { kind: "box" }>;
      const { container } = mount({
        ...box,
        show_values: true,
        boxes: [{ ...box.boxes[0]!, label: null }],
      });
      expect(head(container)).toEqual(["Series", "Minimum", "Q1", "Médiane", "Q3", "Maximum"]);
      const cells = [...container.querySelectorAll("table tbody td")].map((td) => td.textContent);
      expect(cells[0]).toBe("Series 1");
      expect(cells.slice(1)).toEqual(["4", "9", "12", "14", "19"]);
    }));

  it("words a cumulative column and keeps the notation", () =>
    withLocale("en", () => {
      const { container } = mount({ ...CHARTS.cumulative, show_values: true });
      expect(head(container)).toEqual(["Bound", "Fréquence (cumulative)"]);
      const pie = mount({ ...CHARTS.pie, show_values: true });
      expect(pie.container.textContent).toContain("62,5\u00a0%");
      const histogram = mount(CHARTS.histogram);
      const cells = [...histogram.container.querySelectorAll("table td")].map(
        (td) => td.textContent,
      );
      expect(cells).toEqual(["[150 ; 160[", "[160 ; 180["]);
    }));

  it("words the empty chart and puts the table in the interface language", () =>
    withLocale("en", () => {
      const { container } = mount({ ...CHARTS.bars, values: [Number.NaN, -3] } as Chart);
      expect(container.textContent).toContain("Empty chart");
      expect(container.querySelector("table")?.getAttribute("lang")).toBe("en");
    }));
});
