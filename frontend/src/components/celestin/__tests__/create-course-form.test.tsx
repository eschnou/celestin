// @vitest-environment jsdom
/** Spec 011 R1.2/R1.3: the create form asks for the course's language. */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { withLocale } from "@/test/locale";
import type { Subject } from "@/lib/tutor/types";
import { CreateCourseForm } from "../create-course-form";

afterEach(cleanup);

const FRENCH_ONLY: Subject[] = [
  { id: "mathematics", label: "Mathématiques", languages: ["fr"] },
  { id: "sciences", label: "Physique", languages: ["fr"] },
];
const BOTH: Subject[] = [
  { id: "mathematics", label: "Mathématiques", languages: ["fr", "en"] },
  { id: "sciences", label: "Physique", languages: ["fr", "en"] },
];
const MIXED: Subject[] = [
  { id: "mathematics", label: "Mathématiques", languages: ["fr", "en"] },
  { id: "sciences", label: "Physique", languages: ["fr"] },
];

function mount(subjects: Subject[]) {
  const onCreate = vi.fn().mockResolvedValue({});
  render(<CreateCourseForm subjects={subjects} onCreate={onCreate} onCancel={() => {}} />);
  return onCreate;
}

function fill(subject: string) {
  fireEvent.change(screen.getByLabelText("Nom du cours"), { target: { value: "Cours" } });
  fireEvent.change(screen.getByLabelText("Matière"), { target: { value: subject } });
  fireEvent.click(screen.getByRole("button", { name: "Créer le cours" }));
}

describe("CreateCourseForm: the language", () => {
  it("asks nothing when only one language is offered, and sends it", async () => {
    const onCreate = mount(FRENCH_ONLY);
    expect(screen.queryByLabelText("Langue du cours")).toBeNull();
    fill("sciences");
    await waitFor(() => expect(onCreate).toHaveBeenCalledWith("Cours", "sciences", "fr"));
  });

  it("lists the languages the server offers, each by its own name, with the immutability note", async () => {
    const onCreate = mount(BOTH);
    const select = screen.getByLabelText("Langue du cours") as HTMLSelectElement;
    expect([...select.options].map((o) => [o.value, o.textContent, o.lang])).toEqual([
      ["fr", "Français", "fr"],
      ["en", "English", "en"],
    ]);
    expect(
      screen.getByText(
        "La langue dans laquelle ton cours est écrit : Célestin l'enseignera dans cette langue. La langue ne pourra plus être changée ensuite.",
      ),
    ).toBeTruthy();
    expect(select.value).toBe("fr"); // a French interface starts on French
    fireEvent.change(select, { target: { value: "en" } });
    fill("sciences");
    await waitFor(() => expect(onCreate).toHaveBeenCalledWith("Cours", "sciences", "en"));
  });

  it("starts on the interface language when the course can be written in it", async () => {
    await withLocale("en", () => {
      mount(BOTH);
      expect((screen.getByLabelText("Course language") as HTMLSelectElement).value).toBe("en");
      expect(
        screen.getByText(
          "The language your course is written in: Célestin will teach in it. The language can't be changed afterwards.",
        ),
      ).toBeTruthy();
    });
  });

  it("starts on French when the interface language is not offered", async () => {
    await withLocale("en", () => {
      mount(FRENCH_ONLY);
      expect(screen.queryByLabelText("Course language")).toBeNull();
    });
  });

  it("offers only the languages of the chosen subject", () => {
    mount(MIXED);
    fireEvent.change(screen.getByLabelText("Matière"), { target: { value: "sciences" } });
    const select = screen.getByLabelText("Langue du cours") as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(["fr"]);
  });
});
