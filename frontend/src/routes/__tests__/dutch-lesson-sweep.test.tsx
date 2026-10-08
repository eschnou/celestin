// @vitest-environment jsdom
/**
 * The Dutch sweep for the lesson (spec 017 R7.6): the bar, the tutor column, the board, the chapter
 * map, a server marker and a server error, all as a Dutch account receives them, on a French
 * course. Célestin's words and the board's content are French and say so with `lang="fr"`; nothing
 * else in French or English may be on screen.
 */
import { cleanup, fireEvent, screen } from "@testing-library/react";
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
        // What a Dutch account's server sends: the marker and the error in Dutch.
        marker: "vraag gesteld",
      };
      yield { event: "step.ready", marker: "volgende stap voorgesteld" };
      yield { event: "error", code: "overloaded", message: "Célestin is erg druk op dit moment." };
      yield { event: "turn.end", reason: "end", usage: {} };
    }),
  };
});

import { foreignTextOutside } from "@/test/english-sweep";
import { withLocale } from "@/test/locale";
import { mockApi, mountRoutes } from "@/test/route-harness";
import { Route as ChapterFile } from "../_auth/courses/$courseId/chapters/$chapterId/index";

const CHAPTER = {
  id: "suites",
  title: "Les suites numériques",
  position: 1,
  course_id: "maths",
  course_name: "Wiskunde 5e jaar",
  language: "fr",
  subject: "mathematics",
  sections: [
    { id: "s1", index: 1, kind: "teach", title: "Suites numériques", goal: "Savoir lire uₙ." },
    { id: "s2", index: 2, kind: "practise", title: "Calculer un terme", goal: "g2" },
    { id: "s3", index: 3, kind: "synthesis", title: "Synthèse", goal: "g3" },
  ],
  progress: { done: ["s1"], active: "s2" },
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function mountLesson() {
  mockApi(
    (_method, path) => {
      if (path.endsWith("/api/health")) return { body: { voice: false } };
      if (path.endsWith("/api/courses/maths/chapters/suites")) return { body: CHAPTER };
      return undefined;
    },
    { locale: "nl", name: "Lea" },
  );
  mountRoutes(
    [{ path: "/courses/$courseId/chapters/$chapterId/", file: ChapterFile }],
    "/courses/maths/chapters/suites",
  );
}

describe.each([
  ["on a phone", false],
  ["on a desktop", true],
])("the Dutch sweep: the lesson %s", (_layout, desktop) => {
  beforeEach(() => stubLayoutApis({ desktop }));

  it("the bar, the tutor column, the board, a marker and an error", () =>
    withLocale("nl", async () => {
      mountLesson();
      await screen.findByText(/Bonjour, on reprend les suites/);
      await screen.findByText(/Célestin is erg druk op dit moment\./);
      expect(foreignTextOutside("nl")).toEqual([]);
    }));

  it("the chapter map, and its confirmation to start over", () =>
    withLocale("nl", async () => {
      mountLesson();
      await screen.findByText(/Bonjour, on reprend les suites/);
      fireEvent.click(
        screen.getByRole("button", { name: "Het traject van het hoofdstuk bekijken" }),
      );
      await screen.findByRole("dialog");
      expect(foreignTextOutside("nl")).toEqual([]);
      fireEvent.click(screen.getByRole("button", { name: "Het hoofdstuk opnieuw beginnen" }));
      await screen.findByRole("alertdialog");
      expect(foreignTextOutside("nl")).toEqual([]);
    }));
});

describe("the Dutch sweep: the lesson on a phone only", () => {
  beforeEach(() => stubLayoutApis());

  it("the conversation sheet", () =>
    withLocale("nl", async () => {
      mountLesson();
      await screen.findByText(/Bonjour, on reprend les suites/);
      fireEvent.click(
        screen.getByRole("button", { name: "Het hele gesprek met Célestin bekijken" }),
      );
      await screen.findByRole("dialog");
      expect(screen.getByText("Gesprek met Célestin")).toBeTruthy();
      expect(foreignTextOutside("nl")).toEqual([]);
    }));
});
