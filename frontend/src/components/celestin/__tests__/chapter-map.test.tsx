// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChapterMapSheet } from "../chapter-map";
import { CourseLanguageProvider } from "@/lib/course-language";
import type { ChapterView, Progress } from "@/lib/tutor/types";

const CHAPTER: Pick<ChapterView, "id" | "course_id" | "title" | "sections"> = {
  id: "suites",
  course_id: "maths",
  title: "Les suites numériques",
  sections: [
    { id: "s1", index: 1, kind: "teach", title: "Suites numériques", goal: "Savoir lire uₙ." },
    { id: "s2", index: 2, kind: "practise", title: "Calculer un terme", goal: "g2" },
    { id: "s3", index: 3, kind: "teach", title: "La somme", goal: "g3" },
    { id: "s4", index: 4, kind: "synthesis", title: "Synthèse", goal: "g4" },
  ],
};

function mount(progress: Progress, overrides: Partial<Parameters<typeof ChapterMapSheet>[0]> = {}) {
  const onSend = vi.fn();
  const onReset = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <ChapterMapSheet
      open
      onOpenChange={onOpenChange}
      chapter={CHAPTER}
      progress={progress}
      streaming={false}
      onSend={onSend}
      onReset={onReset}
      rereadable={new Set()}
      begun={new Set()}
      {...overrides}
    />,
  );
  return { onSend, onReset, onOpenChange };
}

afterEach(cleanup);

/** The labels of a row's buttons, in order. */
const buttons = (row: HTMLElement) => [...row.querySelectorAll("button")].map((b) => b.textContent);

describe("ChapterMapSheet", () => {
  it("renders the states and the active goal", () => {
    mount({ done: ["s1"], active: "s2", skipped: ["s3"] });
    const rows = screen.getAllByRole("listitem");
    expect(rows.map((r) => r.getAttribute("data-state"))).toEqual([
      "done",
      "active",
      "skipped",
      "open",
    ]);
    expect(screen.getByText("g2")).toBeTruthy();
    expect(screen.queryByText("Savoir lire uₙ.")).toBeNull();
    expect(screen.getByText("1 section faite sur 4 · 1 passée")).toBeTruthy();
  });

  it("says nothing of skipped sections when there are none", () => {
    mount({ done: ["s1"], active: "s2", skipped: [] });
    expect(screen.getByText("1 section faite sur 4")).toBeTruthy();
  });

  it("makes every row actionable, by state (spec 019)", () => {
    mount({ done: ["s1"], active: null, skipped: ["s3"] });
    const rows = screen.getAllByRole("listitem");
    expect(rows.map((r) => r.getAttribute("data-state"))).toEqual([
      "done",
      "available",
      "skipped",
      "open",
    ]);
    expect(buttons(rows[0]!)).toEqual(["Revoir"]);
    expect(buttons(rows[1]!)).toEqual(["Commencer", "Passer"]);
    expect(buttons(rows[2]!)).toEqual(["Commencer"]);
    expect(buttons(rows[3]!)).toEqual(["Commencer", "Passer"]);
    for (const row of rows) expect(row.getAttribute("aria-disabled")).toBeNull();
  });

  it("offers only « Passer » on the active row, and a start everywhere else not done", () => {
    mount({ done: ["s1"], active: "s2", skipped: [] });
    const rows = screen.getAllByRole("listitem");
    expect(buttons(rows[1]!)).toEqual(["Passer"]);
    expect(buttons(rows[2]!)).toEqual(["Commencer", "Passer"]);
    expect(buttons(rows[3]!)).toEqual(["Commencer", "Passer"]);
  });

  it("keeps the primary style for the proposed section only", () => {
    mount({ done: [], active: null, skipped: [] });
    const rows = screen.getAllByRole("listitem");
    const start = (row: HTMLElement) => row.querySelector("button")!;
    expect(start(rows[0]!).className).toContain("bg-primary");
    expect(start(rows[1]!).className).not.toContain("bg-primary");
    expect(rows[0]!.querySelectorAll("button")[1]!.className).not.toContain("bg-primary");
  });

  it("shows a skipped row with a visible « passée » badge", () => {
    mount({ done: [], active: null, skipped: ["s2"] });
    const row = screen.getAllByRole("listitem")[1]!;
    const badge = [...row.querySelectorAll("span")].find((el) => el.textContent === "passée");
    expect(badge).toBeTruthy();
    expect(badge!.className).not.toContain("sr-only");
  });

  it("never says « verrouillée »", () => {
    for (const progress of [
      { done: [], active: null, skipped: [] },
      { done: ["s1"], active: "s3", skipped: ["s2"] },
    ]) {
      mount(progress);
      expect(document.body.textContent).not.toMatch(/verrouill/i);
      cleanup();
    }
  });

  it("reads « Reprendre » on a section with a stored séance, « Commencer » elsewhere", () => {
    const { onSend } = mount(
      { done: [], active: null, skipped: ["s4"] },
      { begun: new Set(["s3", "s4"]) },
    );
    const rows = screen.getAllByRole("listitem");
    expect(buttons(rows[0]!)).toEqual(["Commencer", "Passer"]);
    expect(buttons(rows[2]!)).toEqual(["Reprendre", "Passer"]);
    expect(buttons(rows[3]!)).toEqual(["Reprendre"]);
    fireEvent.click(within(rows[2]!).getByText("Reprendre"));
    expect(onSend).toHaveBeenLastCalledWith("On reprend la section « La somme » ?");
  });

  it("sends the exact French sentences and closes", () => {
    const { onSend, onOpenChange } = mount({ done: ["s1"], active: null, skipped: [] });
    const rows = screen.getAllByRole("listitem");
    fireEvent.click(within(rows[0]!).getByText("Revoir"));
    expect(onSend).toHaveBeenCalledWith("Je voudrais revoir la section « Suites numériques ».");
    fireEvent.click(within(rows[1]!).getByText("Commencer"));
    expect(onSend).toHaveBeenCalledWith("On commence la section « Calculer un terme » ?");
    fireEvent.click(within(rows[2]!).getByText("Passer"));
    expect(onSend).toHaveBeenLastCalledWith("Je passe la section « La somme ».");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("skips the active section with the same sentence", () => {
    const { onSend } = mount({ done: [], active: "s1", skipped: [] });
    fireEvent.click(within(screen.getAllByRole("listitem")[0]!).getByText("Passer"));
    expect(onSend).toHaveBeenLastCalledWith("Je passe la section « Suites numériques ».");
  });

  it("disables actions while a turn streams", () => {
    mount({ done: ["s1"], active: null, skipped: ["s4"] }, { streaming: true });
    const all = screen.getAllByRole("button").filter((b) => b.closest("li"));
    expect(all.length).toBe(6);
    for (const b of all) expect((b as HTMLButtonElement).disabled).toBe(true);
  });

  it("resets only after confirmation", () => {
    const { onReset } = mount({ done: ["s1"], active: null, skipped: [] });
    fireEvent.click(screen.getByText("Recommencer le chapitre"));
    fireEvent.click(screen.getByText("Annuler"));
    expect(onReset).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Recommencer le chapitre"));
    fireEvent.click(screen.getByRole("button", { name: "Recommencer" }));
    expect(onReset).toHaveBeenCalledOnce();
  });
});

describe("ChapterMapSheet in an English course", () => {
  it("sends the learner's request in English", () => {
    const onSend = vi.fn();
    render(
      <CourseLanguageProvider language="en">
        <ChapterMapSheet
          open
          onOpenChange={vi.fn()}
          chapter={CHAPTER}
          progress={{ done: ["s1"], active: null, skipped: [] }}
          streaming={false}
          onSend={onSend}
          onReset={vi.fn()}
          rereadable={new Set()}
          begun={new Set()}
        />
      </CourseLanguageProvider>,
    );
    const first = screen.getAllByRole("listitem").map((r) => r.querySelector("button"));
    fireEvent.click(first[0]!);
    expect(onSend).toHaveBeenLastCalledWith("I'd like to review the section “Suites numériques”.");
    fireEvent.click(first[1]!);
    expect(onSend).toHaveBeenLastCalledWith("Shall we start the section “Calculer un terme”?");
    fireEvent.click(within(screen.getAllByRole("listitem")[2]!).getByText("Passer"));
    expect(onSend).toHaveBeenLastCalledWith("I'm skipping the section “La somme”.");
  });

  it("still sends the French request in a French course", () => {
    const onSend = vi.fn();
    mount({ done: ["s1"], active: null, skipped: [] }, { onSend });
    fireEvent.click(screen.getAllByRole("listitem")[0]!.querySelector("button")!);
    expect(onSend).toHaveBeenLastCalledWith("Je voudrais revoir la section « Suites numériques ».");
  });
});

describe("ChapterMapSheet in a Dutch course", () => {
  it("skips and resumes in Dutch", () => {
    const onSend = vi.fn();
    render(
      <CourseLanguageProvider language="nl">
        <ChapterMapSheet
          open
          onOpenChange={vi.fn()}
          chapter={CHAPTER}
          progress={{ done: [], active: null, skipped: [] }}
          streaming={false}
          onSend={onSend}
          onReset={vi.fn()}
          rereadable={new Set()}
          begun={new Set(["s2"])}
        />
      </CourseLanguageProvider>,
    );
    const rows = screen.getAllByRole("listitem");
    fireEvent.click(within(rows[0]!).getByText("Passer"));
    expect(onSend).toHaveBeenLastCalledWith("Ik sla de sectie “Suites numériques” over.");
    fireEvent.click(within(rows[1]!).getByText("Reprendre"));
    expect(onSend).toHaveBeenLastCalledWith("Gaan we verder met de sectie “Calculer un terme”?");
  });
});
