// @vitest-environment jsdom
/** The course page: chapter states, adding, retrying, deleting (005 R2, R4). */
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, mountRoutes, type Reply } from "@/test/route-harness";
import { Route as CourseFile } from "../_auth/courses/$courseId/index";
import { Route as CoursesFile } from "../_auth/courses/index";

const SUBJECTS = {
  subjects: [{ id: "sciences", label: "Physique", languages: ["fr"] }],
  limits: {
    chapter_text_min_chars: 20,
    chapter_text_max_chars: 200,
    pack_max_chars: 60000,
    document_max_bytes: 26214400,
    document_max_pages: 50,
    document_min_pixels: 800,
    document_types: ["application/pdf", "image/jpeg", "image/png", "image/webp"],
  },
};

const photo = (name: string) => new File(["jpeg"], name, { type: "image/jpeg" });

const row = (over: Record<string, unknown>) => ({
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
  id: "c1",
  name: "Physique 4e",
  subject: "sciences",
  subject_label: "Physique",
  language: "fr",
  chapters_total: 4,
  chapters_done: 0,
  last_chapter: { id: "h1", title: "Le MRU" },
  generating: 1,
  chapters: [
    row({}),
    row({
      id: "h2",
      position: 2,
      title: null,
      ready: false,
      state: "not_started",
      last: false,
      section_count: 0,
      done_count: 0,
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
      done_count: 0,
      authoring_state: "failed",
      authoring_stage: "pack",
      authoring_message: "Je n'ai pas réussi à organiser ce texte en chapitre.",
    }),
    row({
      id: "h4",
      position: 4,
      title: null,
      ready: false,
      state: "not_started",
      last: false,
      section_count: 0,
      done_count: 0,
      authoring_state: "failed",
      authoring_stage: "transcription",
      authoring_message: "Je n'ai pas pu lire certaines pages.",
    }),
  ],
};

function mount(extra?: (method: string, path: string, body: unknown) => Reply | undefined) {
  const calls = mockApi((method, path, body) => {
    const custom = extra?.(method, path, body);
    if (custom) return custom;
    if (path.endsWith("/api/subjects")) return { body: SUBJECTS };
    if (method === "GET" && path.endsWith("/api/courses/c1")) return { body: DETAIL };
    if (method === "GET" && path.endsWith("/api/courses")) return { body: { courses: [] } };
    return undefined;
  });
  const { router } = mountRoutes(
    [
      { path: "/courses/", file: CoursesFile },
      { path: "/courses/$courseId/", file: CourseFile },
    ],
    "/courses/c1",
  );
  return { calls, router };
}

/** A Radix menu opens on Enter (jsdom has no pointer events). */
const openMenu = (button: HTMLElement) => fireEvent.keyDown(button, { key: "Enter" });
const rowMenu = (item: HTMLElement) => within(item).getByRole("button", { name: /^Actions pour/ });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function stubObjectUrls() {
  let n = 0;
  vi.spyOn(URL, "createObjectURL").mockImplementation(() => `blob:page-${++n}`);
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
}

describe("/courses/$courseId", () => {
  it("shows the course's language, and marks the chapter titles with it", async () => {
    mockApi((method, path) => {
      if (path.endsWith("/api/subjects")) return { body: SUBJECTS };
      if (method === "GET" && path.endsWith("/api/courses/c1"))
        return { body: { ...DETAIL, language: "en" } };
      return undefined;
    });
    mountRoutes(
      [
        { path: "/courses/", file: CoursesFile },
        { path: "/courses/$courseId/", file: CourseFile },
      ],
      "/courses/c1",
    );
    const badge = await screen.findByTestId("course-language");
    expect([badge.textContent, badge.getAttribute("lang")]).toEqual(["English", "en"]);
    // The chapter's title is course text wherever it shows: in « reprends » and in the list.
    const titles = screen.getAllByText("Le MRU");
    expect(titles).toHaveLength(2);
    for (const title of titles) expect(title.closest("[lang]")?.getAttribute("lang")).toBe("en");
  });
  it("shows each chapter's state and the actions that fit it", async () => {
    mount();
    const rows = await screen.findAllByRole("listitem");
    expect(rows).toHaveLength(4);
    const [ready, generating, failed, unread] = rows as [
      HTMLElement,
      HTMLElement,
      HTMLElement,
      HTMLElement,
    ];
    expect(ready.textContent).toContain("en cours · Section 3 sur 9");
    expect(ready.textContent).toContain("c'est ici que tu en étais");
    expect(
      within(ready)
        .getByRole("progressbar", { name: "Section 3 sur 9" })
        .getAttribute("aria-valuenow"),
    ).toBe("2");
    expect(within(ready).queryByRole("link", { name: "Contenu du chapitre" })).toBeNull();
    expect(within(ready).getByRole("link", { name: "Reprendre" }).getAttribute("href")).toBe(
      "/courses/c1/chapters/h1",
    );
    expect(generating.textContent).toContain("Nouveau chapitre 2");
    expect(generating.textContent).toContain("Lecture des pages… (3/16)");
    expect(within(generating).queryByRole("link", { name: /Commencer|Reprendre/ })).toBeNull();
    expect(failed.textContent).toContain("Échec de la préparation");
    expect(failed.textContent).toContain("Je n'ai pas réussi à organiser ce texte en chapitre.");
    expect(within(failed).getByRole("button", { name: "Réessayer" })).toBeTruthy();
    // Failed before its pages were read: the document is not kept, so it is asked for again.
    expect(within(unread).queryByRole("button", { name: "Réessayer" })).toBeNull();
    expect(
      within(unread).getByRole("link", { name: "Redéposer le document" }).getAttribute("href"),
    ).toBe("/courses/c1/chapters/h4/content?tab=source");
    // The rarer actions are in the chapter's menu, not beside « Reprendre » (a menu hides the page
    // from the accessibility tree while it is open: it is the last thing this test does).
    openMenu(rowMenu(ready));
    expect(
      (await screen.findByRole("menuitem", { name: "Contenu du chapitre" })).getAttribute("href"),
    ).toBe("/courses/c1/chapters/h1/content");
  });

  it("offers one way back in, above the list: the chapter she was on", async () => {
    mount();
    const resume = await screen.findByRole("region", { name: "Reprends où tu en étais" });
    expect(resume.textContent).toContain("Le MRU");
    expect(resume.textContent).toContain("Section 3 sur 9");
    expect(
      within(resume)
        .getByRole("link", { name: /Reprendre/ })
        .getAttribute("href"),
    ).toBe("/courses/c1/chapters/h1");
  });

  it("offers the next chapter when the last one is finished", async () => {
    mockApi((method, path) => {
      if (path.endsWith("/api/subjects")) return { body: SUBJECTS };
      if (method === "GET" && path.endsWith("/api/courses/c1"))
        return {
          body: {
            ...DETAIL,
            chapters: [
              row({ state: "done", done_count: 9, last: true }),
              row({
                id: "h2",
                position: 2,
                title: "La vitesse",
                state: "not_started",
                done_count: 0,
                last: false,
              }),
            ],
          },
        };
      return undefined;
    });
    mountRoutes([{ path: "/courses/$courseId/", file: CourseFile }], "/courses/c1");
    const next = await screen.findByRole("region", { name: "Prochain chapitre" });
    expect(next.textContent).toContain("La vitesse");
    expect(
      within(next)
        .getByRole("link", { name: /Commencer/ })
        .getAttribute("href"),
    ).toBe("/courses/c1/chapters/h2");
  });

  it("does not repeat a single chapter above itself", async () => {
    mockApi((method, path) => {
      if (path.endsWith("/api/subjects")) return { body: SUBJECTS };
      if (method === "GET" && path.endsWith("/api/courses/c1"))
        return { body: { ...DETAIL, chapters: [row({})] } };
      return undefined;
    });
    mountRoutes([{ path: "/courses/$courseId/", file: CourseFile }], "/courses/c1");
    await screen.findAllByRole("listitem");
    expect(screen.queryByRole("region", { name: "Reprends où tu en étais" })).toBeNull();
  });

  it("retries a failed chapter", async () => {
    const { calls } = mount((method, path) =>
      method === "POST" && path.endsWith("/chapters/h3/retry")
        ? { status: 202, body: row({ id: "h3" }) }
        : undefined,
    );
    const rows = await screen.findAllByRole("listitem");
    fireEvent.click(within(rows[2]!).getByRole("button", { name: "Réessayer" }));
    await waitFor(() =>
      expect(calls.some((c) => c.path.endsWith("/chapters/h3/retry"))).toBe(true),
    );
  });

  it("adds a chapter from photos, in the order chosen", async () => {
    stubObjectUrls();
    const { calls } = mount((method, path) =>
      method === "POST" && path.endsWith("/api/courses/c1/chapters")
        ? { status: 202, body: row({ id: "h5" }) }
        : undefined,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Ajouter un chapitre" }));
    const input = await screen.findByLabelText("Le PDF ou les photos du cours");
    const submit = screen.getByRole("button", {
      name: "Préparer le chapitre",
    }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    fireEvent.change(input, { target: { files: [photo("a.jpg"), photo("b.jpg")] } });
    fireEvent.click(screen.getByRole("button", { name: "Monter la page 2" }));
    expect(submit.disabled).toBe(false);
    fireEvent.click(submit);
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const form = calls.find((c) => c.method === "POST")?.body as FormData;
    expect(form.getAll("files").map((f) => (f as File).name)).toEqual(["b.jpg", "a.jpg"]);
    await waitFor(() =>
      expect(screen.queryByLabelText("Le PDF ou les photos du cours")).toBeNull(),
    );
  });

  it("shows why adding was refused", async () => {
    stubObjectUrls();
    mount((method, path) =>
      method === "POST" && path.endsWith("/chapters")
        ? {
            status: 422,
            body: { code: "document_invalid", message: "La photo 1 est trop petite." },
          }
        : undefined,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Ajouter un chapitre" }));
    fireEvent.change(await screen.findByLabelText("Le PDF ou les photos du cours"), {
      target: { files: [photo("a.jpg")] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Préparer le chapitre" }));
    expect((await screen.findByRole("alert")).textContent).toBe("La photo 1 est trop petite.");
  });

  it("deletes a chapter only after a confirmation naming it", async () => {
    const { calls } = mount((method) =>
      method === "DELETE" ? { status: 204, body: {} } : undefined,
    );
    const rows = await screen.findAllByRole("listitem");
    openMenu(rowMenu(rows[0]!));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Supprimer" }));
    expect(await screen.findByText("Supprimer « Le MRU » ?")).toBeTruthy();
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Supprimer le chapitre" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "DELETE")?.path).toBe("/api/courses/c1/chapters/h1"),
    );
  });

  it("deletes the course after confirmation and goes back to « Mes cours »", async () => {
    const { calls, router } = mount((method) =>
      method === "DELETE" ? { status: 204, body: {} } : undefined,
    );
    openMenu(await screen.findByRole("button", { name: "Actions du cours" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Supprimer le cours" }));
    expect(await screen.findByText(/Ses 4 chapitres/)).toBeTruthy();
    const dialog = screen.getByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Supprimer le cours" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/courses"));
    expect(calls.find((c) => c.method === "DELETE")?.path).toBe("/api/courses/c1");
  });

  it("renames the course", async () => {
    const { calls } = mount((method) =>
      method === "PATCH" ? { body: { ...DETAIL, name: "Physique" } } : undefined,
    );
    openMenu(await screen.findByRole("button", { name: "Actions du cours" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Renommer" }));
    fireEvent.change(screen.getByLabelText("Nom du cours"), { target: { value: "  Physique " } });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ name: "Physique" }),
    );
  });
});
