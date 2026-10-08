// @vitest-environment jsdom
/** « Mes cours », the course, the chapter in preparation and the content editors, with the
 *  interface in English (spec 010 R3). What the server or the course wrote stays as received. */
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { withLocale } from "@/test/locale";
import { mockApi, mountRoutes, type Handler } from "@/test/route-harness";
import { Route as ChapterFile } from "../_auth/courses/$courseId/chapters/$chapterId/index";
import { Route as ContentFile } from "../_auth/courses/$courseId/chapters/$chapterId/content";
import { Route as CourseFile } from "../_auth/courses/$courseId/index";
import { Route as CoursesFile } from "../_auth/courses/index";

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
  subjects: [{ id: "sciences", label: "Physique", languages: ["fr"] }],
  limits: LIMITS,
};

const summary = (over: Record<string, unknown> = {}) => ({
  id: "c1",
  name: "Physique 4e",
  subject: "sciences",
  subject_label: "Physique",
  language: "fr",
  chapters_total: 2,
  chapters_done: 1,
  last_chapter: { id: "h1", title: "Le MRU" },
  generating: 1,
  ...over,
});

const row = (over: Record<string, unknown> = {}) => ({
  id: "h1",
  position: 1,
  title: "Le MRU",
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
  authoring_received_chars: 0,
  authoring_quiet_s: null,
  ...over,
});

const DETAIL = {
  ...summary({ chapters_total: 3 }),
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
      authoring_received_chars: 0,
      authoring_quiet_s: null,
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
      authoring_message: "Je n'ai pas pu lire certaines pages.",
    }),
  ],
};

const CONTENT = {
  id: "h1",
  course_id: "c1",
  subject: "sciences",
  position: 1,
  version: 2,
  ready: true,
  title: "Le MRU",
  pack: "# Le MRU\n\n## 1. Objectif du chapitre\n\nDécrire un MRU.\n",
  curriculum: {
    title: "Le MRU",
    sections: [
      {
        id: "vitesse",
        index: 1,
        kind: "teach",
        title: "La vitesse",
        goal: "Définir v.",
        done_when: "Question répondue.",
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
        done_when: "Deux exercices.",
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
  authoring_received_chars: 0,
  authoring_quiet_s: null,
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
    if (method === "GET" && path.endsWith("/api/courses")) return { body: { courses: [] } };
    return undefined;
  };

const ROUTES = [
  { path: "/courses/", file: CoursesFile },
  { path: "/courses/$courseId/", file: CourseFile },
  { path: "/courses/$courseId/chapters/$chapterId/", file: ChapterFile },
  { path: "/courses/$courseId/chapters/$chapterId/content", file: ContentFile },
];

/** Open `initial` as an English account. */
const open = (initial: string, handler?: Handler) => {
  mockApi(api(handler), { locale: "en" });
  return mountRoutes(ROUTES, initial);
};

/** The title a route's `head()` asks for, in the language current when it is read. */
const headTitle = (file: { options: { head?: unknown } }): string | undefined =>
  (file.options.head as () => { meta: { title?: string }[] })().meta[0]?.title;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("« My courses » in English", () => {
  it("words the empty state, the title and the create form", () =>
    withLocale("en", async () => {
      open("/courses");
      expect(await screen.findByText(/You don't have any courses yet/)).toBeTruthy();
      expect(screen.getByRole("heading", { name: "My courses" })).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: "New course" }));
      expect(await screen.findByText("The subject can't be changed afterwards.")).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: "Create the course" }));
      expect(await screen.findByText("Give your course a name.")).toBeTruthy();
      expect(screen.getByText("Choose a subject.")).toBeTruthy();
      expect(screen.getByPlaceholderText("Physics Year 5")).toBeTruthy();
      const subject = screen.getByLabelText("Subject") as HTMLSelectElement;
      // The subject label comes from the server: as received.
      expect([...subject.options].map((o) => o.textContent)).toEqual([
        "Choose a subject",
        "Physique",
      ]);
      expect(headTitle(CoursesFile)).toBe("Célestin — my courses");
    }));

  it("words a course card, its progress and its preparation", () =>
    withLocale("en", async () => {
      mockApi(
        api((method, path) =>
          method === "GET" && path.endsWith("/api/courses")
            ? { body: { courses: [summary()] } }
            : undefined,
        ),
        { locale: "en" },
      );
      mountRoutes(ROUTES, "/courses");
      const card = await screen.findByRole("article", { name: "Physique 4e" });
      expect(card.textContent).toContain("1 / 2 chapters completed");
      expect(card.textContent).toContain("1 being prepared");
      const resume = screen.getByRole("link", { name: "Resume: Le MRU" });
      expect(resume.getAttribute("href")).toBe("/courses/c1/chapters/h1");
      expect(screen.getByRole("link", { name: "Open" })).toBeTruthy();
    }));

  it("shows the server's refusal as received", () =>
    withLocale("en", async () => {
      open("/courses", (method, path) =>
        method === "POST" && path.endsWith("/api/courses")
          ? {
              status: 409,
              body: { code: "course_limit", message: "Tu as atteint le nombre maximum de cours." },
            }
          : undefined,
      );
      fireEvent.click(await screen.findByRole("button", { name: "New course" }));
      fireEvent.change(await screen.findByLabelText("Course name"), { target: { value: "X" } });
      fireEvent.change(screen.getByLabelText("Subject"), { target: { value: "sciences" } });
      fireEvent.click(screen.getByRole("button", { name: "Create the course" }));
      expect((await screen.findByRole("alert")).textContent).toBe(
        "Tu as atteint le nombre maximum de cours.",
      );
    }));
});

describe("the course page in English", () => {
  it("words the chapter rows, keeping the server's failure message", () =>
    withLocale("en", async () => {
      open("/courses/c1");
      await screen.findByRole("heading", { name: "Physique 4e" });
      const items = screen.getAllByRole("listitem");
      const [first, second, third] = items as [HTMLElement, HTMLElement, HTMLElement];
      expect(first.textContent).toContain("in progress · Section 3 of 9");
      expect(first.textContent).toContain("this is where you left off");
      expect(within(first).getByRole("link", { name: "Resume" })).toBeTruthy();
      expect(within(first).getByRole("link", { name: "Discuss" })).toBeTruthy();
      expect(second.textContent).toContain("New chapter 2");
      expect(second.textContent).toContain("Reading the pages… (3/16)");
      expect(third.textContent).toContain("Preparation failed");
      expect(third.textContent).toContain("Je n'ai pas pu lire certaines pages.");
      expect(within(third).getByRole("link", { name: "Upload the document again" })).toBeTruthy();
      expect(screen.getByRole("link", { name: "← My courses" })).toBeTruthy();
      expect(headTitle(CourseFile)).toBe("Célestin — course");
      fireEvent.keyDown(within(first).getByRole("button", { name: /^Actions for/ }), {
        key: "Enter",
      });
      expect(await screen.findByRole("menuitem", { name: "Chapter content" })).toBeTruthy();
    }));

  it("confirms a course deletion with the chapter count in the plural", () =>
    withLocale("en", async () => {
      open("/courses/c1");
      fireEvent.keyDown(await screen.findByRole("button", { name: "Course actions" }), {
        key: "Enter",
      });
      fireEvent.click(await screen.findByRole("menuitem", { name: "Delete the course" }));
      const dialog = await screen.findByRole("alertdialog");
      expect(dialog.textContent).toContain("Delete “Physique 4e”?");
      expect(dialog.textContent).toContain(
        "Its 3 chapters, their content and your progress will be erased. This can't be undone.",
      );
      expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeTruthy();
    }));

  it("words renaming and the document picker", () =>
    withLocale("en", async () => {
      open("/courses/c1");
      fireEvent.keyDown(await screen.findByRole("button", { name: "Course actions" }), {
        key: "Enter",
      });
      fireEvent.click(await screen.findByRole("menuitem", { name: "Rename" }));
      fireEvent.change(screen.getByLabelText("Course name"), { target: { value: "" } });
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
      expect(
        await screen.findByText("The name must be between 1 and 80 characters long."),
      ).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
      fireEvent.click(screen.getByRole("button", { name: "Add a chapter" }));
      expect(await screen.findByLabelText("The PDF or photos of the course")).toBeTruthy();
      expect(screen.getByText(/50 pages and 25 MB at most\./)).toBeTruthy();
      expect(screen.getByText("Choose a PDF or photos")).toBeTruthy();
      expect(screen.getByRole("button", { name: "Prepare the chapter" })).toBeTruthy();
    }));
});

describe("the chapter page in English", () => {
  it("says a chapter is being prepared", () =>
    withLocale("en", async () => {
      open("/courses/c1/chapters/h2", (method, path) =>
        path.includes("/chapters/h2") && method === "GET"
          ? { status: 409, body: { code: "chapter_not_ready", message: "Pas prêt." } }
          : undefined,
      );
      expect(await screen.findByText("This chapter is being prepared")).toBeTruthy();
      expect(
        await screen.findByText(
          "Reading the pages… (3/16) Then Célestin organises the content and builds the path. It takes a few minutes.",
        ),
      ).toBeTruthy();
      expect(screen.getByRole("link", { name: "Back to the course" })).toBeTruthy();
    }));

  it("words the not-found card", () =>
    withLocale("en", async () => {
      open("/courses/c1/chapters/zz", (method, path) =>
        path.includes("/chapters/zz") && method === "GET"
          ? { status: 404, body: { code: "not_found", message: "Introuvable." } }
          : undefined,
      );
      expect(await screen.findByText("This page doesn't exist")).toBeTruthy();
      expect(
        screen.getByText("This course or chapter doesn't exist, or it isn't yours."),
      ).toBeTruthy();
    }));
});

describe("the content page in English", () => {
  const openContent = (extra?: Handler, content: unknown = CONTENT) =>
    open("/courses/c1/chapters/h1/content", (method, path, body) => {
      const custom = extra?.(method, path, body);
      if (custom) return custom;
      if (method === "GET" && path.endsWith("/chapters/h1/content")) return { body: content };
      return undefined;
    });
  const tab = async (name: string) => {
    const el = await screen.findByRole("tab", { name });
    fireEvent.mouseDown(el);
    fireEvent.click(el);
  };

  it("words the heading, the tabs and the read views; course text stays as it is", () =>
    withLocale("en", async () => {
      openContent();
      expect(
        await screen.findByRole("heading", { level: 1, name: "Chapter 1 — Le MRU" }),
      ).toBeTruthy();
      expect(screen.getByRole("tab", { name: "Content" })).toBeTruthy();
      expect(screen.getByRole("button", { name: "Edit the content" })).toBeTruthy();
      await tab("Path");
      expect(await screen.findByText("La vitesse")).toBeTruthy();
      expect(screen.getByText("1 · Lesson")).toBeTruthy();
      expect(screen.getByText("2 · Practice")).toBeTruthy();
      expect(screen.getByText("2 exercises based on: 6.1.1 ; 6.1.2")).toBeTruthy();
      expect(screen.getByText("Done when: Deux exercices.")).toBeTruthy();
      await tab("Text extracted from the document");
      expect(await screen.findByText(/Le texte lu dans le document\./)).toBeTruthy();
      expect(
        screen.getByText("Read from the document you uploaded (2 pages). The file isn't kept."),
      ).toBeTruthy();
      expect(screen.getByRole("button", { name: "Replace with a document" })).toBeTruthy();
      expect(headTitle(ContentFile)).toBe("Célestin — chapter content");
    }));

  it("says a new version is being prepared and locks the editors", () =>
    withLocale("en", async () => {
      openContent(undefined, { ...CONTENT, authoring_state: "generating" });
      expect(
        await screen.findByText(
          "New version being prepared… The content below stays in use in the meantime.",
        ),
      ).toBeTruthy();
      expect(screen.getByText("You can edit it once the preparation is finished.")).toBeTruthy();
    }));

  it("confirms the progress reset in English and shows the validator's issues as received", () =>
    withLocale("en", async () => {
      openContent((method) =>
        method === "PUT"
          ? {
              status: 422,
              body: {
                code: "content_invalid",
                message: "Le contenu n'est pas valide.",
                issues: [{ where: "§ 5", message: "section « ## 5. Vocabulaire » manquante" }],
              },
            }
          : undefined,
      );
      fireEvent.click(await screen.findByRole("button", { name: "Edit the content" }));
      expect(screen.getByText(/Keep the numbered headings/)).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: "Save the content" }));
      const dialog = await screen.findByRole("alertdialog");
      expect(dialog.textContent).toContain("Save your changes?");
      expect(dialog.textContent).toContain(
        "The path of this chapter will start over from the beginning: your progress will be reset.",
      );
      fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
      expect((await screen.findByRole("alert")).textContent).toBe(
        "§ 5: section « ## 5. Vocabulaire » manquante",
      );
    }));

  it("words the path editor and its validation", () =>
    withLocale("en", async () => {
      openContent();
      await tab("Path");
      fireEvent.click(await screen.findByRole("button", { name: "Edit the path" }));
      expect(screen.getByLabelText("Path title")).toBeTruthy();
      expect(screen.getByLabelText("Kind of section 1")).toBeTruthy();
      expect(screen.getByRole("button", { name: "Move section 1 down" })).toBeTruthy();
      expect(screen.getByRole("button", { name: "Remove section 2" })).toBeTruthy();
      fireEvent.change(screen.getByLabelText("Title", { selector: "#section-0-title" }), {
        target: { value: "  " },
      });
      fireEvent.change(screen.getByLabelText("Steps (one per line)"), { target: { value: "" } });
      fireEvent.click(screen.getByRole("button", { name: "Save the path" }));
      const dialog = await screen.findByRole("alertdialog");
      fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
      expect(await screen.findByText("The title is required.")).toBeTruthy();
      expect(screen.getByText("A lesson has at least one step.")).toBeTruthy();
    }));

  it("words the text editor, with counts grouped for the interface language", () =>
    withLocale("en", async () => {
      openContent();
      await tab("Text extracted from the document");
      fireEvent.click(await screen.findByRole("button", { name: "Edit the text" }));
      expect(screen.getByText(/Fix what Célestin misread/)).toBeTruthy();
      fireEvent.change(screen.getByRole("textbox"), { target: { value: "abc" } });
      expect(screen.getByText("3 characters · at least 10")).toBeTruthy();
      fireEvent.change(screen.getByRole("textbox"), { target: { value: "a".repeat(501) } });
      expect(screen.getByText("501 characters · at most 500")).toBeTruthy();
      expect(screen.getByRole("button", { name: "Prepare again" })).toBeTruthy();
    }));
});
