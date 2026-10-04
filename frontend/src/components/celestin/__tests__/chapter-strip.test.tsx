// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChapterStrip } from "../chapter-strip";
import { chapterModel } from "@/lib/tutor/chapter-model";
import type { Chapter } from "@/lib/tutor/types";

const CHAPTER: Chapter = {
  id: "suites",
  title: "Les suites numériques",
  sections: [
    { id: "s1", index: 1, kind: "teach", title: "Suites numériques", goal: "g1" },
    { id: "s2", index: 2, kind: "practise", title: "Calculer un terme", goal: "g2" },
    { id: "s3", index: 3, kind: "synthesis", title: "Synthèse", goal: "g3" },
  ],
};

afterEach(cleanup);

describe("chapterModel", () => {
  it("counts and focuses the active section", () => {
    const m = chapterModel(CHAPTER, { done: ["s1"], active: "s2" });
    expect(m.doneCount).toBe(1);
    expect(m.segments).toEqual(["done", "active", "locked"]);
    expect(m.focus).toEqual({ kind: "active", section: CHAPTER.sections[1] });
  });

  it("focuses the next section when nothing is active", () => {
    expect(chapterModel(CHAPTER, { done: ["s1"], active: null }).focus).toEqual({
      kind: "next",
      section: CHAPTER.sections[1],
    });
  });

  it("reports completion", () => {
    expect(chapterModel(CHAPTER, { done: ["s1", "s2", "s3"], active: null }).focus).toEqual({
      kind: "complete",
    });
  });
});

describe("ChapterStrip", () => {
  it("renders one segment per section with its state, and the active line", () => {
    const { container } = render(
      <ChapterStrip
        chapter={CHAPTER}
        progress={{ done: ["s1"], active: "s2" }}
        onOpen={() => {}}
      />,
    );
    const segments = [...container.querySelectorAll("[data-state]")].map((el) =>
      el.getAttribute("data-state"),
    );
    expect(segments).toEqual(["done", "active", "locked"]);
    expect(screen.getByText("Calculer un terme")).toBeTruthy();
    expect(screen.getByText(/2 · Exercices/)).toBeTruthy();
    expect(screen.getByText(/1 \/ 3/)).toBeTruthy();
  });

  it("is a card-less line on a phone: no chapter title, the count beside the section", () => {
    render(
      <ChapterStrip
        chapter={CHAPTER}
        progress={{ done: ["s1"], active: "s2" }}
        onOpen={() => {}}
        compact
      />,
    );
    expect(screen.queryByRole("heading")).toBeNull();
    expect(screen.getByText("Calculer un terme")).toBeTruthy();
    expect(screen.getByText(/1 \/ 3/)).toBeTruthy();
  });

  it("says what comes next when nothing is active", () => {
    render(
      <ChapterStrip chapter={CHAPTER} progress={{ done: [], active: null }} onOpen={() => {}} />,
    );
    expect(screen.getByText(/À suivre · 1 · Leçon/)).toBeTruthy();
  });

  it("says the chapter is complete", () => {
    render(
      <ChapterStrip
        chapter={CHAPTER}
        progress={{ done: ["s1", "s2", "s3"], active: null }}
        onOpen={() => {}}
      />,
    );
    expect(screen.getByText("Chapitre terminé")).toBeTruthy();
  });

  it("opens the map on click", () => {
    const onOpen = vi.fn();
    render(
      <ChapterStrip chapter={CHAPTER} progress={{ done: [], active: null }} onOpen={onOpen} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Voir le parcours du chapitre" }));
    expect(onOpen).toHaveBeenCalledOnce();
  });

  it("shows loading and unavailable states without a chapter", () => {
    const { rerender } = render(
      <ChapterStrip chapter={null} progress={{ done: [], active: null }} onOpen={() => {}} />,
    );
    expect(screen.getByText(/Chargement/)).toBeTruthy();
    rerender(
      <ChapterStrip
        chapter={null}
        unavailable
        progress={{ done: [], active: null }}
        onOpen={() => {}}
      />,
    );
    expect(screen.getByText(/indisponible/)).toBeTruthy();
  });
});
