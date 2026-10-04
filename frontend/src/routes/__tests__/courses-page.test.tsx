// @vitest-environment jsdom
/** « Mes cours » (005 R1). */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, mountRoutes } from "@/test/route-harness";
import { Route as CourseFile } from "../_auth/courses/$courseId/index";
import { Route as CoursesFile } from "../_auth/courses/index";

const SUBJECTS = {
  subjects: [
    { id: "mathematics", label: "Mathématiques", languages: ["fr"] },
    { id: "sciences", label: "Physique", languages: ["fr"] },
  ],
  limits: { chapter_text_min_chars: 300, chapter_text_max_chars: 100000, pack_max_chars: 60000 },
};

const COURSE = {
  id: "c1",
  name: "Mathématiques 5e",
  subject: "mathematics",
  subject_label: "Mathématiques",
  language: "fr",
  chapters_total: 2,
  chapters_done: 1,
  last_chapter: { id: "h1", title: "Les suites numériques" },
  generating: 1,
};

function mount(courses: unknown[], onPost?: (body: unknown) => { status?: number; body: unknown }) {
  const calls = mockApi((method, path, body) => {
    if (path.endsWith("/api/subjects")) return { body: SUBJECTS };
    if (method === "GET" && path.endsWith("/api/courses")) return { body: { courses } };
    if (method === "POST" && path.endsWith("/api/courses")) return onPost?.(body);
    if (path.endsWith("/api/courses/new1"))
      return {
        body: {
          ...COURSE,
          id: "new1",
          name: "Physique 5e",
          chapters: [],
          chapters_total: 0,
          last_chapter: null,
          generating: 0,
        },
      };
    return undefined;
  });
  const { router } = mountRoutes(
    [
      { path: "/courses/", file: CoursesFile },
      { path: "/courses/$courseId/", file: CourseFile },
    ],
    "/courses",
  );
  return { calls, router };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("/courses", () => {
  it("never shows an empty page", async () => {
    mount([]);
    await screen.findByText(/Tu n'as pas encore de cours/);
    expect(screen.getByRole("button", { name: "Nouveau cours" })).toBeTruthy();
  });

  it("lists courses with progress, preparation and a way back in", async () => {
    mount([COURSE]);
    const card = await screen.findByRole("article", { name: "Mathématiques 5e" });
    expect(card.textContent).toContain("1 / 2 chapitres terminé");
    expect(card.textContent).toContain("1 en préparation");
    const resume = screen.getByRole("link", { name: "Reprendre : Les suites numériques" });
    expect(resume.getAttribute("href")).toBe("/courses/c1/chapters/h1");
  });

  it("tells the courses apart by their language", async () => {
    mount([COURSE, { ...COURSE, id: "c2", name: "Physics 5", language: "en" }]);
    const french = await screen.findByRole("article", { name: "Mathématiques 5e" });
    const english = screen.getByRole("article", { name: "Physics 5" });
    const badge = (card: HTMLElement) => card.querySelector('[data-testid="course-language"]');
    expect([badge(french)?.textContent, badge(french)?.getAttribute("lang")]).toEqual([
      "Français",
      "fr",
    ]);
    expect([badge(english)?.textContent, badge(english)?.getAttribute("lang")]).toEqual([
      "English",
      "en",
    ]);
  });

  it("creates a course with a name and an available subject, then opens it", async () => {
    const { calls, router } = mount([], () => ({ status: 201, body: { ...COURSE, id: "new1" } }));
    fireEvent.click(await screen.findByRole("button", { name: "Nouveau cours" }));
    expect(await screen.findByText("La matière ne pourra plus être changée ensuite.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Créer le cours" }));
    expect(await screen.findByText("Donne un nom à ton cours.")).toBeTruthy();
    expect(screen.getByText("Choisis une matière.")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Nom du cours"), { target: { value: "Physique 5e" } });
    const subject = screen.getByLabelText("Matière") as HTMLSelectElement;
    expect([...subject.options].map((o) => o.textContent)).toEqual([
      "Choisis une matière",
      "Mathématiques",
      "Physique",
    ]);
    fireEvent.change(subject, { target: { value: "sciences" } });
    fireEvent.click(screen.getByRole("button", { name: "Créer le cours" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/courses/new1"));
    const post = calls.find((c) => c.method === "POST");
    expect(post?.body).toEqual({ name: "Physique 5e", subject: "sciences", language: "fr" });
  });

  it("shows the server's refusal under the form", async () => {
    mount([], () => ({
      status: 409,
      body: { code: "course_limit", message: "Tu as atteint le nombre maximum de cours." },
    }));
    fireEvent.click(await screen.findByRole("button", { name: "Nouveau cours" }));
    fireEvent.change(await screen.findByLabelText("Nom du cours"), { target: { value: "X" } });
    fireEvent.change(screen.getByLabelText("Matière"), { target: { value: "mathematics" } });
    fireEvent.click(screen.getByRole("button", { name: "Créer le cours" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Tu as atteint le nombre maximum de cours.",
    );
  });
});
