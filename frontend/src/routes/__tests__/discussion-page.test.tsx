// @vitest-environment jsdom
/**
 * Discussion mode in the interface (spec 007). Two things are load-bearing: the
 * conversation is created once on a first open, and opening a discussion from
 * inside the lesson must not throw the séance away (R1.3) — its transcript and
 * board live in memory only.
 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/** jsdom has neither `matchMedia` nor `ResizeObserver`. `matches: false` takes
 *  the stacked layout, which needs no resizable panels. */
beforeEach(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

// Voice is not what is under test here, and WebRTC does not exist under jsdom.
vi.mock("@/components/celestin/use-voice-session", () => ({
  useVoiceSession: () => ({
    phase: "off",
    muted: false,
    capAt: null,
    supported: false,
    start: async () => {},
    stop: () => {},
    toggleMute: () => {},
    sendText: () => {},
  }),
}));

vi.mock("@/components/celestin/discussion-panel", () => ({
  DiscussionPanel: () => <div data-testid="discussion">discussion</div>,
}));

vi.mock("@/lib/tutor/client", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/tutor/client")>();
  return {
    ...mod,
    streamTurn: vi.fn(async function* () {
      yield { event: "turn.start", turn_id: "t1" };
      yield { event: "text.delta", block_id: 0, text: "Bonjour, on reprend les suites." };
      yield { event: "turn.end", reason: "end", usage: {} };
    }),
  };
});

import { streamTurn } from "@/lib/tutor/client";
import { Route as ChapterFile } from "../_auth/courses/$courseId/chapters/$chapterId/index";
import { Route as DiscussionFile } from "../_auth/courses/$courseId/chapters/$chapterId/discussion";
import { mockApi, mountRoutes } from "@/test/route-harness";

const CHAPTER = {
  id: "suites",
  title: "Les suites numériques",
  position: 1,
  course_id: "maths",
  course_name: "Mathématiques 5e",
  language: "fr",
  subject: "mathematics",
  sections: [{ id: "suites", index: 1, kind: "teach", title: "Suites", goal: "g" }],
  progress: { done: [], active: null },
};

const CHAPTER_PATH = "/api/courses/maths/chapters/suites";
const DISCUSSION_PATH = `${CHAPTER_PATH}/discussion`;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function mountLesson() {
  const calls = mockApi((method, path) => {
    if (path.endsWith("/api/health")) return { body: { voice: false } };
    if (path.endsWith(CHAPTER_PATH)) return { body: CHAPTER };
    return undefined;
  });
  mountRoutes(
    [
      { path: "/courses/$courseId/chapters/$chapterId/", file: ChapterFile },
      { path: "/courses/$courseId/chapters/$chapterId/discussion", file: DiscussionFile },
    ],
    "/courses/maths/chapters/suites",
  );
  return calls;
}

describe("Discussion inside the lesson", () => {
  it("keeps the séance alive across a round trip to the discussion", async () => {
    mountLesson();
    const opening = await screen.findByText(/Bonjour, on reprend les suites/);
    expect(opening).toBeTruthy();
    expect(vi.mocked(streamTurn)).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Discussion" }));
    await screen.findByTestId("discussion");
    // Hidden, not unmounted: the transcript is still in the document.
    expect(screen.getByText(/Bonjour, on reprend les suites/)).toBeTruthy();

    expect(screen.getByRole("button", { name: "Discussion" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: "Parcours" }));
    await waitFor(() => expect(screen.queryByTestId("discussion")).toBeTruthy());
    expect(screen.getByText(/Bonjour, on reprend les suites/)).toBeTruthy();
    // And the opening turn was never re-run.
    expect(vi.mocked(streamTurn)).toHaveBeenCalledTimes(1);
  });

  it("does not open a discussion until it is asked for", async () => {
    mountLesson();
    await screen.findByText(/Bonjour, on reprend les suites/);
    expect(screen.queryByTestId("discussion")).toBeNull();
  });
});

describe("the standalone discussion route", () => {
  it("sits under the lesson's bar: the way back to the course, and to the parcours", async () => {
    mockApi((method, path) => {
      if (path.endsWith("/api/health")) return { body: { voice: false } };
      if (path.endsWith(CHAPTER_PATH)) return { body: CHAPTER };
      return undefined;
    });
    mountRoutes(
      [{ path: "/courses/$courseId/chapters/$chapterId/discussion", file: DiscussionFile }],
      "/courses/maths/chapters/suites/discussion",
    );
    await screen.findByTestId("discussion");
    const back = screen.getByRole("link", { name: /Mathématiques 5e/ });
    expect(back.getAttribute("href")).toBe("/courses/maths");
    expect(screen.getByRole("link", { name: "Parcours" }).getAttribute("href")).toBe(
      "/courses/maths/chapters/suites",
    );
    expect(screen.getByRole("button", { name: "Discussion" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
  });
});
