// @vitest-environment jsdom
/**
 * The English sweep for the lesson (spec 010 R3, task 10.3): the bar, the tutor column, the
 * board, the chapter map, a server marker and a server error, all as an English account
 * receives them. Célestin's words and the board's content are French and say so with
 * `lang="fr"`; nothing else may be.
 */
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { stubLayoutApis } from "@/test/jsdom-stubs";

beforeEach(() => stubLayoutApis());

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
      yield {
        event: "board.set",
        card: {
          kind: "check_question",
          question: "Pourquoi $q \\neq 1$ ?",
          options: [
            { id: "a", text: "Division par zéro" },
            { id: "b", text: "Par habitude" },
          ],
          correct_option_id: "a",
          feedback: "Exactement.",
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
  title: "Les suites numériques",
  position: 1,
  course_id: "maths",
  course_name: "Maths Year 5",
  language: "fr",
  subject: "mathematics",
  sections: [
    { id: "s1", index: 1, kind: "teach", title: "Suites numériques", goal: "Savoir lire uₙ." },
    { id: "s2", index: 2, kind: "practise", title: "Calculer un terme", goal: "g2" },
    { id: "s3", index: 3, kind: "synthesis", title: "Synthèse", goal: "g3" },
  ],
  progress: { done: ["s1"], active: "s2", skipped: [] },
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function mountLesson(
  seance: unknown = null,
  start: { progress: unknown; seances: unknown } = {
    progress: CHAPTER.progress,
    seances: { s1: { cards: 3 } },
  },
) {
  mockApi(
    (_method, path) => {
      if (path.endsWith("/api/health")) return { body: { voice: false } };
      if (path.endsWith("/api/courses/maths/chapters/suites")) return { body: CHAPTER };
      // Boards stored for the first section (018): its row offers to reread them.
      if (path.endsWith("/api/courses/maths/chapters/suites/seance"))
        return { body: { seance, ...start } };
      return undefined;
    },
    { locale: "en", name: "Lea" },
  );
  mountRoutes(
    [{ path: "/courses/$courseId/chapters/$chapterId/", file: ChapterFile }],
    "/courses/maths/chapters/suites",
  );
}

describe.each([
  ["on a phone", false],
  ["on a desktop", true],
])("the English sweep: the lesson %s", (_layout, desktop) => {
  beforeEach(() => stubLayoutApis({ desktop }));

  it("the bar, the tutor column, the board, a marker and an error", () =>
    withLocale("en", async () => {
      mountLesson();
      await screen.findByText(/Bonjour, on reprend les suites/);
      await screen.findByText(/Célestin is very busy right now\./);
      expect(frenchOutsideCourseText()).toEqual([]);
    }));

  it("the chapter map, and its confirmation to start over", () =>
    withLocale("en", async () => {
      mountLesson();
      await screen.findByText(/Bonjour, on reprend les suites/);
      fireEvent.click(screen.getByRole("button", { name: "See the chapter's path" }));
      await screen.findByRole("dialog");
      expect(screen.getByRole("link", { name: "Reread" })).toBeTruthy();
      expect(frenchOutsideCourseText()).toEqual([]);
      fireEvent.click(screen.getByRole("button", { name: "Start the chapter over" }));
      await screen.findByRole("alertdialog");
      expect(frenchOutsideCourseText()).toEqual([]);
    }));
});

describe("the English sweep: a resumed séance (018)", () => {
  beforeEach(() => stubLayoutApis({ desktop: true }));

  it("the restored transcript and its « séance reprise » marker", () =>
    withLocale("en", async () => {
      mountLesson({
        id: "row1",
        section_id: "s2",
        entries: [
          { kind: "tutor", text: "On reprend le calcul d'un terme." },
          {
            kind: "tool",
            name: "start_section",
            arguments: { section_id: "s2" },
            review: false,
            marker: "question asked",
          },
          { kind: "learner", text: "D'accord." },
        ],
      });
      await screen.findByText(/session resumed/);
      expect(frenchOutsideCourseText()).toEqual([]);
    }));
});

describe("the English sweep: the lesson on a phone only", () => {
  beforeEach(() => stubLayoutApis());

  it("the conversation sheet", () =>
    withLocale("en", async () => {
      mountLesson();
      await screen.findByText(/Bonjour, on reprend les suites/);
      fireEvent.click(
        screen.getByRole("button", { name: "See the whole conversation with Célestin" }),
      );
      await screen.findByRole("dialog");
      expect(screen.getByText("Conversation with Célestin")).toBeTruthy();
      expect(frenchOutsideCourseText()).toEqual([]);
    }));
});

describe("the English sweep: the open path (spec 019)", () => {
  beforeEach(() => stubLayoutApis({ desktop: true }));

  it("a skipped section, a section to resume, and « Passer »", () =>
    withLocale("en", async () => {
      // s1 done, s2 skipped, s3 begun in an earlier séance and proposed next.
      mountLesson(null, {
        progress: { done: ["s1"], active: null, skipped: ["s2"] },
        seances: { s1: { cards: 3 }, s3: { cards: 0 } },
      });
      await screen.findByText(/Bonjour, on reprend les suites/);
      expect(screen.getAllByText(/1 done · 1 skipped/).length).toBeGreaterThan(0);
      fireEvent.click(screen.getByRole("button", { name: "See the chapter's path" }));
      const sheet = await screen.findByRole("dialog");
      expect(within(sheet).getByText("skipped")).toBeTruthy();
      expect(within(sheet).getByRole("button", { name: "Resume" })).toBeTruthy();
      expect(within(sheet).getAllByRole("button", { name: "Skip" }).length).toBe(1);
      expect(frenchOutsideCourseText()).toEqual([]);
    }));
});
