// @vitest-environment jsdom
/** Spec 011 R7.1–R7.3: the four drawings write the course's notation, whatever the interface. */
import { cleanup, render } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { CourseLanguageProvider, type CourseLanguage } from "@/lib/course-language";
import type { Chart, Figure, PlotBlock } from "@/lib/tutor/types";
import { withLocale } from "@/test/locale";
import { FigureView } from "../../figure/figure-view";
import { FIGURES, NUMBER_LINE, PLANE } from "../../figure/__tests__/fixtures";
import { PLOTS } from "../../plot/__tests__/fixtures";
import { PlotView } from "../../plot/plot-view";
import { ChartView } from "../chart-view";
import { CHARTS } from "./fixtures";

afterEach(cleanup);

const inCourse = (language: CourseLanguage, node: ReactNode) =>
  render(<CourseLanguageProvider language={language}>{node}</CourseLanguageProvider>);
const chart = (language: CourseLanguage, c: Chart) =>
  inCourse(language, <ChartView block={{ type: "chart", chart: c }} />);
const figure = (language: CourseLanguage, f: Figure) =>
  inCourse(language, <FigureView block={{ type: "figure", figure: f }} />);
const plot = (language: CourseLanguage, p: PlotBlock) => inCourse(language, <PlotView block={p} />);

describe("a chart", () => {
  it("writes percentages with a point and no space in an English course", () => {
    const { container } = chart("en", { ...CHARTS.pie, show_values: true });
    expect(container.textContent).toContain("62.5%");
    expect(container.querySelector("table")?.textContent).toContain("37.5%");
    expect(container.textContent).not.toContain("62,5");
  });

  it("still writes them the FWB way in a French course", () => {
    const { container } = chart("fr", { ...CHARTS.pie, show_values: true });
    expect(container.textContent).toContain("62,5 %");
  });

  it("lists classes as English intervals for a screen reader", () => {
    const { container } = chart("en", CHARTS.histogram);
    const cells = [...container.querySelectorAll("table td")].map((td) => td.textContent);
    expect(cells).toEqual(["[150, 160)", "[160, 180)"]);
  });

  it("names the value column in the course's language, under either interface language", async () => {
    const sticks = { ...CHARTS.sticks, show_values: true };
    const head = () => [...document.querySelectorAll("table th")].map((th) => th.textContent);
    chart("en", sticks);
    expect(head()).toContain("Frequency");
    cleanup();
    await withLocale("fr", () => {
      chart("en", sticks);
      expect(head()).toContain("Frequency");
    });
    cleanup();
    await withLocale("en", () => {
      chart("fr", sticks);
      expect(head()).toContain("Effectif");
    });
  });

  it("names a box plot's five numbers in the course's language", () => {
    const { container } = chart("en", { ...CHARTS.box, show_values: true });
    const head = [...container.querySelectorAll("table th")].map((th) => th.textContent);
    expect(head).toContain("Median");
    expect(head).not.toContain("Médiane");
  });
});

describe("a figure", () => {
  const items = (container: HTMLElement) =>
    [...container.querySelectorAll(".sr-only li")].map((li) => li.textContent);

  it("describes a number line's intervals in the English notation", () => {
    const { container } = figure("en", { ...NUMBER_LINE, show_values: true } as Figure);
    expect(items(container)).toContain("SS = [2, ∞)");
  });

  it("describes a plane's points with an English pair when values are shown", () => {
    const { container } = figure("en", { ...PLANE, show_values: true } as Figure);
    expect(items(container)).toContain("Points : A(0, 0), B(4, 0), C(0, 3)");
  });

  it("describes the same figures the French way in a French course", () => {
    const line = figure("fr", { ...NUMBER_LINE, show_values: true } as Figure);
    expect(items(line.container)).toContain("SS = [2 ; +∞[");
    cleanup();
    const plane = figure("fr", { ...PLANE, show_values: true } as Figure);
    expect(items(plane.container)).toContain("Points : A(0 ; 0), B(4 ; 0), C(0 ; 3)");
  });

  it("draws every fixture in both languages without error", () => {
    for (const language of ["fr", "en", "nl"] as const)
      for (const f of Object.values(FIGURES)) {
        const { container } = figure(language, f);
        expect(container.querySelector("svg")).not.toBeNull();
        cleanup();
      }
  });
});

describe("a plot", () => {
  const name = Object.keys(PLOTS)[0] as keyof typeof PLOTS;
  const sentence = (container: HTMLElement) => container.querySelector("p.sr-only")?.textContent;

  it("writes a point's coordinates with a comma and a point in an English course", () => {
    expect(sentence(plot("en", PLOTS[name]).container)).toContain("Point S (0, −4)");
  });

  it("writes them with the semicolon in a French course", () => {
    expect(sentence(plot("fr", PLOTS[name]).container)).toContain("Point S (0 ; −4)");
  });
});
