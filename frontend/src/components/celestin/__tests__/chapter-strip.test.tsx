// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChapterStrip } from "../chapter-strip";
import { chapterModel } from "@/lib/tutor/chapter-model";
import type { Chapter } from "@/lib/tutor/types";
import { withLocale } from "@/test/locale";

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
    const m = chapterModel(CHAPTER, { done: ["s1"], active: "s2", skipped: [] });
    expect(m.doneCount).toBe(1);
    expect(m.segments).toEqual(["done", "active", "open"]);
    expect(m.focus).toEqual({ kind: "active", section: CHAPTER.sections[1] });
  });

  it("focuses the next section when nothing is active", () => {
    expect(chapterModel(CHAPTER, { done: ["s1"], active: null, skipped: [] }).focus).toEqual({
      kind: "next",
      section: CHAPTER.sections[1],
    });
  });

  it("counts skipped sections apart and focuses the proposed one past them (spec 019)", () => {
    const model = chapterModel(CHAPTER, { done: [], active: null, skipped: ["s1"] });
    expect(model.doneCount).toBe(0);
    expect(model.skippedCount).toBe(1);
    expect(model.segments).toEqual(["skipped", "available", "open"]);
    expect(model.focus).toEqual({ kind: "next", section: CHAPTER.sections[1] });
  });

  it("reports completion when every section is done or skipped", () => {
    expect(
      chapterModel(CHAPTER, { done: ["s1", "s3"], active: null, skipped: ["s2"] }).focus,
    ).toEqual({ kind: "complete" });
  });

  it("reports completion", () => {
    expect(
      chapterModel(CHAPTER, { done: ["s1", "s2", "s3"], active: null, skipped: [] }).focus,
    ).toEqual({
      kind: "complete",
    });
  });
});

describe("ChapterStrip", () => {
  it("renders one segment per section with its state, and the active line", () => {
    const { container } = render(
      <ChapterStrip
        chapter={CHAPTER}
        progress={{ done: ["s1"], active: "s2", skipped: [] }}
        onOpen={() => {}}
      />,
    );
    const segments = [...container.querySelectorAll("[data-state]")].map((el) =>
      el.getAttribute("data-state"),
    );
    expect(segments).toEqual(["done", "active", "open"]);
    expect(screen.getByText("Calculer un terme")).toBeTruthy();
    expect(screen.getByText(/2 · Exercices/)).toBeTruthy();
    expect(screen.getByText(/1 \/ 3/)).toBeTruthy();
  });

  it("is a card-less line on a phone: no chapter title, the count beside the section", () => {
    render(
      <ChapterStrip
        chapter={CHAPTER}
        progress={{ done: ["s1"], active: "s2", skipped: [] }}
        onOpen={() => {}}
        compact
      />,
    );
    expect(screen.queryByRole("heading")).toBeNull();
    expect(screen.getByText("Calculer un terme")).toBeTruthy();
    expect(screen.getByText(/1 \/ 3/)).toBeTruthy();
  });

  it("draws skipped segments apart and counts « faites · passées »", () => {
    const { container } = render(
      <ChapterStrip
        chapter={CHAPTER}
        progress={{ done: ["s1"], active: null, skipped: ["s2"] }}
        onOpen={() => {}}
      />,
    );
    const segments = [...container.querySelectorAll("[data-state]")];
    expect(segments.map((el) => el.getAttribute("data-state"))).toEqual([
      "done",
      "skipped",
      "available",
    ]);
    const classes = segments.map((el) => el.className);
    expect(classes[1]).not.toBe(classes[0]);
    expect(classes[1]).not.toBe(classes[2]);
    expect(screen.getByText(/1 faite · 1 passée/)).toBeTruthy();
    expect(screen.queryByText(/1 \/ 3/)).toBeNull();
    expect(screen.getByText(/À suivre · 3 · Synthèse/)).toBeTruthy();
  });

  it("counts in English and Dutch", async () => {
    const progress = { done: ["s1"], active: null, skipped: ["s2", "s3"] };
    for (const [locale, text] of [
      ["en", "1 done · 2 skipped"],
      ["nl", "1 afgerond · 2 overgeslagen"],
    ] as const) {
      await withLocale(locale, () => {
        render(<ChapterStrip chapter={CHAPTER} progress={progress} onOpen={() => {}} />);
        expect(screen.getByText(new RegExp(text))).toBeTruthy();
        cleanup();
      });
    }
  });

  it("says what comes next when nothing is active", () => {
    render(
      <ChapterStrip
        chapter={CHAPTER}
        progress={{ done: [], active: null, skipped: [] }}
        onOpen={() => {}}
      />,
    );
    expect(screen.getByText(/À suivre · 1 · Leçon/)).toBeTruthy();
  });

  it("says the chapter is complete", () => {
    render(
      <ChapterStrip
        chapter={CHAPTER}
        progress={{ done: ["s1", "s2", "s3"], active: null, skipped: [] }}
        onOpen={() => {}}
      />,
    );
    expect(screen.getByText("Chapitre terminé")).toBeTruthy();
  });

  it("opens the map on click", () => {
    const onOpen = vi.fn();
    render(
      <ChapterStrip
        chapter={CHAPTER}
        progress={{ done: [], active: null, skipped: [] }}
        onOpen={onOpen}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Voir le parcours du chapitre" }));
    expect(onOpen).toHaveBeenCalledOnce();
  });

  it("shows loading and unavailable states without a chapter", () => {
    const { rerender } = render(
      <ChapterStrip
        chapter={null}
        progress={{ done: [], active: null, skipped: [] }}
        onOpen={() => {}}
      />,
    );
    expect(screen.getByText(/Chargement/)).toBeTruthy();
    rerender(
      <ChapterStrip
        chapter={null}
        unavailable
        progress={{ done: [], active: null, skipped: [] }}
        onOpen={() => {}}
      />,
    );
    expect(screen.getByText(/indisponible/)).toBeTruthy();
  });
});
