// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChapterMapSheet } from "../chapter-map";
import { CourseLanguageProvider } from "@/lib/course-language";
import type { Chapter, Progress } from "@/lib/tutor/types";

const CHAPTER: Chapter = {
  id: "suites",
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
      {...overrides}
    />,
  );
  return { onSend, onReset, onOpenChange };
}

afterEach(cleanup);

describe("ChapterMapSheet", () => {
  it("renders the four states and the active goal", () => {
    mount({ done: ["s1"], active: "s2" });
    const rows = screen.getAllByRole("listitem");
    expect(rows.map((r) => r.getAttribute("data-state"))).toEqual([
      "done",
      "active",
      "locked",
      "locked",
    ]);
    expect(screen.getByText("g2")).toBeTruthy();
    expect(screen.queryByText("Savoir lire uₙ.")).toBeNull();
    expect(screen.getByText("1 section faite sur 4")).toBeTruthy();
  });

  it("offers a review on done rows only, and nothing on locked rows", () => {
    mount({ done: ["s1", "s2"], active: null });
    const rows = screen.getAllByRole("listitem");
    expect(rows[0]!.querySelector("button")?.textContent).toBe("Revoir");
    expect(rows[1]!.querySelector("button")?.textContent).toBe("Revoir");
    expect(rows[2]!.querySelector("button")?.textContent).toBe("Commencer");
    expect(rows[3]!.querySelector("button")).toBeNull();
    expect(rows[3]!.getAttribute("aria-disabled")).toBe("true");
  });

  it("does not offer to start while a section is active", () => {
    mount({ done: ["s1"], active: "s2" });
    expect(screen.queryByText("Commencer")).toBeNull();
  });

  it("sends the exact French sentences and closes", () => {
    const { onSend, onOpenChange } = mount({ done: ["s1"], active: null });
    fireEvent.click(screen.getByText("Revoir"));
    expect(onSend).toHaveBeenCalledWith("Je voudrais revoir la section « Suites numériques ».");
    fireEvent.click(screen.getByText("Commencer"));
    expect(onSend).toHaveBeenCalledWith("On commence la section « Calculer un terme » ?");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("disables actions while a turn streams", () => {
    mount({ done: ["s1"], active: null }, { streaming: true });
    expect((screen.getByText("Revoir") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByText("Commencer") as HTMLButtonElement).disabled).toBe(true);
  });

  it("resets only after confirmation", () => {
    const { onReset } = mount({ done: ["s1"], active: null });
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
          progress={{ done: ["s1"], active: null }}
          streaming={false}
          onSend={onSend}
          onReset={vi.fn()}
        />
      </CourseLanguageProvider>,
    );
    const buttons = screen.getAllByRole("listitem").map((r) => r.querySelector("button"));
    fireEvent.click(buttons[0]!);
    expect(onSend).toHaveBeenLastCalledWith("I'd like to review the section “Suites numériques”.");
    fireEvent.click(buttons[1]!);
    expect(onSend).toHaveBeenLastCalledWith("Shall we start the section “Calculer un terme”?");
  });

  it("still sends the French request in a French course", () => {
    const onSend = vi.fn();
    mount({ done: ["s1"], active: null }, { onSend });
    fireEvent.click(screen.getAllByRole("listitem")[0]!.querySelector("button")!);
    expect(onSend).toHaveBeenLastCalledWith("Je voudrais revoir la section « Suites numériques ».");
  });
});
