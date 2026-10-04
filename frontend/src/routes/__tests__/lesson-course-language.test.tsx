// @vitest-environment jsdom
/**
 * Spec 011 task 4.6: an English course under each interface language. The course text is
 * English and says so with `lang="en"` (never `fr`), whatever the buttons around it say; and
 * under an English interface not a French word is left anywhere, course text included.
 */
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { stubLayoutApis } from "@/test/jsdom-stubs";

beforeEach(() => stubLayoutApis({ desktop: true }));

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
      yield { event: "text.delta", block_id: 0, text: "Hello, let's pick the sequences back up." };
      yield {
        event: "board.set",
        card: {
          kind: "check_question",
          question: "Why $q \\neq 1$ ?",
          options: [
            { id: "a", text: "Division by zero" },
            { id: "b", text: "Out of habit" },
          ],
          correct_option_id: "a",
          feedback: "Exactly.",
        },
        // What an English account's server sends: the marker and the error in English.
        marker: "question asked",
      };
      yield { event: "step.ready", marker: "next step offered" };
      yield { event: "error", code: "overloaded", message: "Célestin is very busy right now." };
      yield { event: "turn.end", reason: "end", usage: {} };
    }),
  };
});

import { frenchOutsideCourseText } from "@/test/english-sweep";
import { withLocale } from "@/test/locale";
import { mockApi, mountRoutes } from "@/test/route-harness";
import { Route as ChapterFile } from "../_auth/courses/$courseId/chapters/$chapterId/index";

const CHAPTER = {
  id: "suites",
  title: "Sequences",
  position: 1,
  course_id: "maths",
  course_name: "Maths Year 5",
  language: "en",
  subject: "mathematics",
  sections: [
    { id: "s1", index: 1, kind: "teach", title: "Number sequences", goal: "Read u_n." },
    { id: "s2", index: 2, kind: "practise", title: "Computing a term", goal: "g2" },
    { id: "s3", index: 3, kind: "synthesis", title: "Summary", goal: "g3" },
  ],
  progress: { done: ["s1"], active: "s2" },
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function mountLesson(locale: "fr" | "en") {
  mockApi(
    (_method, path) => {
      if (path.endsWith("/api/health")) return { body: { voice: false } };
      if (path.endsWith("/api/courses/maths/chapters/suites")) return { body: CHAPTER };
      return undefined;
    },
    { locale, name: "Lea" },
  );
  mountRoutes(
    [{ path: "/courses/$courseId/chapters/$chapterId/", file: ChapterFile }],
    "/courses/maths/chapters/suites",
  );
}

/** The `lang` of every region inside the page: the interface's own is on `<html>`. */
const regionLanguages = () =>
  new Set([...document.body.querySelectorAll("[lang]")].map((el) => el.getAttribute("lang")));

describe("an English course", () => {
  it("under a French interface: the course text is marked English, never French", () =>
    withLocale("fr", async () => {
      mountLesson("fr");
      await screen.findByText(/Hello, let's pick the sequences back up\./);
      expect(regionLanguages()).toEqual(new Set(["en"]));
      const badge = screen.getByTestId("course-language");
      expect([badge.textContent, badge.getAttribute("lang")]).toEqual(["English", "en"]);
      // The interface around it is French and unmarked.
      expect(screen.getByRole("button", { name: "Voir le parcours du chapitre" })).toBeTruthy();
    }));

  it("under an English interface: not a French word is left, in the chrome or in the course", () =>
    withLocale("en", async () => {
      mountLesson("en");
      await screen.findByText(/Hello, let's pick the sequences back up\./);
      await screen.findByText(/Célestin is very busy right now\./);
      expect(frenchOutsideCourseText()).toEqual([]);
      expect(regionLanguages()).toEqual(new Set(["en"]));
      fireEvent.click(screen.getByRole("button", { name: "See the chapter's path" }));
      await screen.findByRole("dialog");
      expect(frenchOutsideCourseText()).toEqual([]);
    }));

  it("a French word in English course text fails the sweep", () =>
    withLocale("en", async () => {
      mountLesson("en");
      await screen.findByText(/Hello, let's pick the sequences back up\./);
      const intruder = document.createElement("p");
      intruder.lang = "en";
      intruder.textContent = "Division par zéro";
      document.body.appendChild(intruder);
      expect(frenchOutsideCourseText()).toEqual(["Division par zéro"]);
    }));
});
