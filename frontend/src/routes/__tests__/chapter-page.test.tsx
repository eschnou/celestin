// @vitest-environment jsdom
/**
 * The lesson route (004 R5.2/R5.4, 005 R4.4). A failed *background* refetch must
 * not tear down a session in progress, and a chapter still in preparation shows
 * its state rather than a lesson.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRouteWithContext,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
  type AnyRoute,
} from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/celestin/lesson", () => ({
  LessonScreen: ({ chapter }: { chapter: { title: string } }) => (
    <div data-testid="lesson">séance : {chapter.title}</div>
  ),
}));

import { Route as AuthFile } from "../_auth";
import { Route as ChapterFile } from "../_auth/courses/$courseId/chapters/$chapterId/index";

const USER = { id: "u1", email: "lea@example.be", name: "Léa", role: "student" };
const CHAPTER = {
  id: "suites",
  title: "Les suites numériques",
  course_id: "maths",
  course_name: "Mathématiques 5e",
  language: "fr",
  subject: "mathematics",
  sections: [{ id: "suites", index: 1, kind: "teach", title: "Suites", goal: "g" }],
  progress: { done: [], active: "suites" },
};

const NOT_READY = { code: "chapter_not_ready", message: "Ce chapitre n'est pas encore prêt." };
const COURSE = {
  id: "maths",
  name: "Mathématiques 5e",
  subject: "mathematics",
  subject_label: "Mathématiques",
  language: "fr",
  chapters_total: 1,
  chapters_done: 0,
  last_chapter: null,
  generating: 0,
  chapters: [
    {
      id: "suites",
      position: 1,
      title: null,
      ready: false,
      section_count: 0,
      done_count: 0,
      state: "not_started",
      last: false,
      authoring_state: "failed",
      authoring_message: "Le service de préparation est indisponible pour le moment.",
      authoring_stage: "pack",
      pages_done: 12,
      page_count: 12,
    },
  ],
};
type Row = Omit<(typeof COURSE.chapters)[number], "authoring_message"> & {
  authoring_message: string | null;
};

function mockApi(chapterStatus = 200, row: Partial<Row> = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const path = String(url);
      if (path.endsWith("/api/auth/me"))
        return { ok: true, status: 200, json: async () => ({ user: USER }) };
      if (path.endsWith("/api/courses/maths"))
        return {
          ok: true,
          status: 200,
          json: async () => ({ ...COURSE, chapters: [{ ...COURSE.chapters[0], ...row }] }),
        };
      if (path.includes("/chapters/suites"))
        return {
          ok: chapterStatus < 400,
          status: chapterStatus,
          json: async () =>
            chapterStatus < 400
              ? CHAPTER
              : chapterStatus === 409
                ? NOT_READY
                : { code: "not_found", message: "Cette page n'existe pas." },
        };
      return { ok: false, status: 404, json: async () => ({}) };
    }),
  );
}

function mount() {
  const rootRoute = createRootRouteWithContext<{ queryClient: QueryClient }>()({
    component: () => <Outlet />,
  });
  const authRoute = createRoute({
    getParentRoute: () => rootRoute,
    id: "_auth",
    beforeLoad: AuthFile.options.beforeLoad as never,
    component: AuthFile.options.component as never,
  }) as unknown as AnyRoute;
  const loginRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/login",
    validateSearch: (s: Record<string, unknown>) => s,
    component: () => <p>login</p>,
  });
  const chapterRoute = createRoute({
    getParentRoute: () => authRoute,
    path: "/courses/$courseId/chapters/$chapterId/",
    loader: ChapterFile.options.loader as never,
    component: ChapterFile.options.component as never,
  });
  const queryClient = new QueryClient();
  const router = createRouter({
    routeTree: rootRoute.addChildren([
      loginRoute as never,
      authRoute.addChildren([chapterRoute as never]) as never,
    ]),
    context: { queryClient },
    history: createMemoryHistory({ initialEntries: ["/courses/maths/chapters/suites"] }),
  });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router as never} />
    </QueryClientProvider>,
  );
  return router;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the lesson route", () => {
  it("mounts the lesson once the chapter and its progress are loaded", async () => {
    mockApi();
    mount();
    expect(await screen.findByTestId("lesson")).toHaveProperty(
      "textContent",
      "séance : Les suites numériques",
    );
  });

  it("keeps a live lesson when a background refetch fails", async () => {
    mockApi();
    mount();
    await screen.findByTestId("lesson");
    // The cookie expires, the wifi blips, the backend restarts: the refetch 500s
    // while `data` is still held. Tearing down here would lose the whole session.
    mockApi(500);
    await waitFor(() => expect(screen.getByTestId("lesson")).toBeTruthy());
    expect(screen.queryByText("Cette page n'a pas pu s'afficher")).toBeNull();
  });

  it("shows the preparation state, with its message, for a chapter that is not ready", async () => {
    mockApi(409);
    mount();
    await screen.findByText("La préparation de ce chapitre a échoué");
    expect(
      screen.getByText("Le service de préparation est indisponible pour le moment."),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeTruthy();
    expect(screen.queryByTestId("lesson")).toBeNull();
  });

  it("counts the pages read while a document is being read", async () => {
    mockApi(409, {
      authoring_state: "generating",
      authoring_message: null,
      authoring_stage: "transcription",
      pages_done: 4,
    });
    mount();
    expect(await screen.findByText(/Lecture des pages… \(4\/12\)/)).toBeTruthy();
  });

  it("asks for the document again when its pages could not be read", async () => {
    mockApi(409, { authoring_stage: "transcription" });
    mount();
    const link = await screen.findByRole("link", { name: "Redéposer le document" });
    expect(link.getAttribute("href")).toBe("/courses/maths/chapters/suites/content?tab=source");
    expect(screen.queryByRole("button", { name: "Réessayer" })).toBeNull();
  });

  it("shows why a retry was refused", async () => {
    mockApi(409);
    const base = vi.mocked(fetch).getMockImplementation()!;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) =>
        String(url).endsWith("/retry")
          ? {
              ok: false,
              status: 429,
              json: async () => ({ code: "authoring_quota", message: "Réessaie après 18:30." }),
            }
          : base(url, init),
      ),
    );
    mount();
    const retry = await screen.findByRole("button", { name: "Réessayer" });
    fireEvent.click(retry);
    expect((await screen.findByRole("alert")).textContent).toBe("Réessaie après 18:30.");
  });

  it("shows the not-found card when the chapter never loaded", async () => {
    mockApi(404);
    mount();
    await screen.findByText("Cette page n'existe pas");
    expect(screen.queryByTestId("lesson")).toBeNull();
  });
});
