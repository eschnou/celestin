// @vitest-environment jsdom
/**
 * The English sweep (spec 010 R3, task 10.3): every screen of the application, with the
 * interface in English and the data an English account really receives (the server writes
 * English too), must hold no French outside a region marked `lang="fr"`. Course text is
 * French and marked as such; anything else with an accent is a string nobody translated.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LoginForm, RegisterForm, SetupForm } from "@/components/celestin/auth-forms";
import { frenchOutsideCourseText } from "@/test/english-sweep";
import { withLocale } from "@/test/locale";
import { mockApi, mountRoutes, type Handler } from "@/test/route-harness";
import { Route as ChapterFile } from "../_auth/courses/$courseId/chapters/$chapterId/index";
import { Route as ContentFile } from "../_auth/courses/$courseId/chapters/$chapterId/content";
import { Route as CourseFile } from "../_auth/courses/$courseId/index";
import { Route as CoursesFile } from "../_auth/courses/index";
import { Route as SettingsFile } from "../_auth/settings";

vi.mock("@/components/celestin/math", () => ({
  Math: ({ tex }: { tex: string }) => <span>{tex}</span>,
}));

const LIMITS = {
  chapter_text_min_chars: 10,
  chapter_text_max_chars: 500,
  pack_max_chars: 60000,
  document_max_bytes: 26214400,
  document_max_pages: 50,
  document_min_pixels: 800,
  document_types: ["application/pdf", "image/jpeg", "image/png", "image/webp"],
};
const SUBJECTS = {
  subjects: [{ id: "sciences", label: "Physics", languages: ["fr"] }],
  limits: LIMITS,
};

const summary = {
  id: "c1",
  name: "Physics Year 4",
  subject: "sciences",
  subject_label: "Physics",
  language: "fr",
  chapters_total: 3,
  chapters_done: 1,
  last_chapter: { id: "h1", title: "Uniform motion" },
  generating: 1,
};

const row = (over: Record<string, unknown> = {}) => ({
  id: "h1",
  position: 1,
  title: "Uniform motion",
  ready: true,
  section_count: 9,
  done_count: 2,
  state: "in_progress",
  last: true,
  authoring_state: "idle",
  authoring_message: null,
  authoring_stage: null,
  pages_done: 0,
  page_count: 0,
  ...over,
});

const DETAIL = {
  ...summary,
  chapters: [
    row(),
    row({
      id: "h2",
      position: 2,
      title: null,
      ready: false,
      state: "not_started",
      last: false,
      section_count: 0,
      authoring_state: "generating",
      authoring_stage: "transcription",
      pages_done: 3,
      page_count: 16,
    }),
    row({
      id: "h3",
      position: 3,
      title: null,
      ready: false,
      state: "not_started",
      last: false,
      section_count: 0,
      authoring_state: "failed",
      authoring_stage: "transcription",
      authoring_message: "Reading the pages took too long. Upload the document again.",
    }),
  ],
};

// The pack and the path are the course's: French, and marked `lang="fr"` where they show.
const CONTENT = {
  id: "h1",
  course_id: "c1",
  subject: "sciences",
  position: 1,
  version: 2,
  ready: true,
  title: "Le mouvement rectiligne uniforme",
  pack: "# Le MRU\n\n## 1. Objectif du chapitre\n\nDécrire un MRU.\n",
  curriculum: {
    title: "Le mouvement rectiligne uniforme",
    sections: [
      {
        id: "vitesse",
        index: 1,
        kind: "teach",
        title: "La vitesse moyenne",
        goal: "Définir la vitesse.",
        done_when: "Done",
        pack: ["§4.1"],
        beats: ["Citer la définition."],
        exercises: [],
        count: null,
      },
      {
        id: "calculs",
        index: 2,
        kind: "practise",
        title: "Calculs",
        goal: "Calculer v.",
        done_when: "Done",
        pack: [],
        beats: [],
        exercises: ["6.1.1", "6.1.2"],
        count: 2,
      },
    ],
  },
  source_text: "--- page 1 ---\n\nLe texte lu dans le document.\n",
  source_kind: "document",
  language: "fr",
  page_count: 2,
  authoring_state: "idle",
  authoring_message: null,
  has_progress: true,
};

const api =
  (extra?: Handler): Handler =>
  (method, path, body) => {
    const custom = extra?.(method, path, body);
    if (custom) return custom;
    if (path.endsWith("/api/subjects")) return { body: SUBJECTS };
    if (method === "GET" && path.endsWith("/api/courses/c1")) return { body: DETAIL };
    if (method === "GET" && path.endsWith("/api/courses")) return { body: { courses: [summary] } };
    if (method === "GET" && path.endsWith("/chapters/h1/content")) return { body: CONTENT };
    return undefined;
  };

const ROUTES = [
  { path: "/courses/", file: CoursesFile },
  { path: "/courses/$courseId/", file: CourseFile },
  { path: "/courses/$courseId/chapters/$chapterId/", file: ChapterFile },
  { path: "/courses/$courseId/chapters/$chapterId/content", file: ContentFile },
  { path: "/settings", file: SettingsFile },
];

/** Open `initial` as an English account. */
const open = (initial: string, handler?: Handler) => {
  mockApi(api(handler), { locale: "en", name: "Lea" });
  return mountRoutes(ROUTES, initial);
};

const clean = () => expect(frenchOutsideCourseText()).toEqual([]);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the English sweep: signed out", () => {
  it("sign-in and registration, with their validation messages", () =>
    withLocale("en", () => {
      render(<LoginForm onSuccess={() => undefined} />);
      fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
      return screen.findByText("Enter your email address.").then(() => {
        clean();
        cleanup();
        render(<RegisterForm onSuccess={() => undefined} />);
        fireEvent.click(screen.getByRole("button", { name: "Create my account" }));
        return screen.findByText("Enter your first name.").then(() => {
          clean();
          cleanup();
          render(<SetupForm onSuccess={() => undefined} />);
          fireEvent.click(screen.getByRole("button", { name: "Create the administrator" }));
          return screen.findByText("Enter your first name.").then(clean);
        });
      });
    }));
});

describe("the English sweep: courses", () => {
  it("« My courses », empty, with the create form and its errors", () =>
    withLocale("en", async () => {
      open("/courses", (method, path) =>
        method === "GET" && path.endsWith("/api/courses") ? { body: { courses: [] } } : undefined,
      );
      await screen.findByText(/You don't have any courses yet/);
      clean();
      fireEvent.click(screen.getByRole("button", { name: "New course" }));
      fireEvent.click(await screen.findByRole("button", { name: "Create the course" }));
      await screen.findByText("Give your course a name.");
      clean();
    }));

  it("« My courses », with a course card", () =>
    withLocale("en", async () => {
      open("/courses");
      await screen.findByRole("article", { name: "Physics Year 4" });
      clean();
    }));

  it("a course: ready, preparing and failed chapters, rename and the document picker", () =>
    withLocale("en", async () => {
      open("/courses/c1");
      await screen.findByRole("heading", { name: "Physics Year 4" });
      clean();
      fireEvent.keyDown(screen.getByRole("button", { name: "Course actions" }), { key: "Enter" });
      await screen.findByRole("menuitem", { name: "Rename" });
      clean();
      fireEvent.click(screen.getByRole("menuitem", { name: "Rename" }));
      fireEvent.change(screen.getByLabelText("Course name"), { target: { value: "" } });
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
      await screen.findByText("The name must be between 1 and 80 characters long.");
      clean();
      fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
      fireEvent.click(screen.getByRole("button", { name: "Add a chapter" }));
      await screen.findByLabelText("The PDF or photos of the course");
      clean();
    }));

  it("a chapter in preparation, and a chapter that is not found", () =>
    withLocale("en", async () => {
      open("/courses/c1/chapters/h2", (method, path) =>
        path.includes("/chapters/h2") && method === "GET"
          ? {
              status: 409,
              body: { code: "chapter_not_ready", message: "This chapter isn't ready yet." },
            }
          : undefined,
      );
      await screen.findByText("This chapter is being prepared");
      clean();
      cleanup();
      open("/courses/c1/chapters/zz", (method, path) =>
        path.includes("/chapters/zz") && method === "GET"
          ? { status: 404, body: { code: "not_found", message: "This page doesn't exist." } }
          : undefined,
      );
      await screen.findByText("This course or chapter doesn't exist, or it isn't yours.");
      clean();
    }));
});

describe("the English sweep: the content page", () => {
  const tab = async (name: string) => {
    const el = await screen.findByRole("tab", { name });
    fireEvent.mouseDown(el);
    fireEvent.click(el);
  };

  it("the pack, the path and the text, read-only and in their editors", () =>
    withLocale("en", async () => {
      open("/courses/c1/chapters/h1/content");
      await screen.findByRole("tab", { name: "Content" });
      clean();
      fireEvent.click(screen.getByRole("button", { name: "Edit the content" }));
      clean();
      fireEvent.click(screen.getByRole("button", { name: "Save the content" }));
      await screen.findByRole("alertdialog");
      clean();
      cleanup();

      open("/courses/c1/chapters/h1/content");
      await tab("Path");
      await screen.findByText("1 · Lesson");
      clean();
      fireEvent.click(screen.getByRole("button", { name: "Edit the path" }));
      await screen.findByLabelText("Path title");
      clean();
      cleanup();

      open("/courses/c1/chapters/h1/content");
      await tab("Text extracted from the document");
      await screen.findByRole("button", { name: "Edit the text" });
      clean();
      fireEvent.click(screen.getByRole("button", { name: "Edit the text" }));
      await screen.findByText(/Fix what Célestin misread/);
      clean();
    }));

  it("an English account's refused edit lists English reasons", () =>
    withLocale("en", async () => {
      open("/courses/c1/chapters/h1/content", (method) =>
        method === "PUT"
          ? {
              status: 422,
              body: {
                code: "content_invalid",
                message: "The content isn't valid. Fix the points shown.",
                issues: [
                  {
                    where: "§ 5",
                    message: "section “## 5. Vocabulaire” is missing or has the wrong title",
                  },
                ],
              },
            }
          : undefined,
      );
      fireEvent.click(await screen.findByRole("button", { name: "Edit the content" }));
      fireEvent.click(screen.getByRole("button", { name: "Save the content" }));
      const dialog = await screen.findByRole("alertdialog");
      fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
      await screen.findByRole("alert");
      clean();
    }));
});

describe("the English sweep: settings and the user menu", () => {
  it("the settings screen", () =>
    withLocale("en", async () => {
      open("/settings");
      await screen.findByRole("heading", { name: "Settings" });
      clean();
    }));

  it("the open user menu", () =>
    withLocale("en", async () => {
      open("/courses");
      await screen.findByRole("button", { name: "Lea" });
      fireEvent.keyDown(screen.getByRole("button", { name: "Lea" }), { key: "Enter" });
      await screen.findByRole("menuitem", { name: "Settings" });
      clean();
    }));
});

import { within } from "@testing-library/react";
