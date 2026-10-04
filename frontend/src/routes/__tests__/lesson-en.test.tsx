// @vitest-environment jsdom
/**
 * The lesson with the interface in English (spec 010 R3, R4). The chrome is English; Célestin's
 * messages, the board's content and the sentences the interface sends to the model on the
 * learner's behalf stay French; course regions say so with `lang="fr"`.
 */
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
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
        marker: "question posée",
      };
      yield { event: "step.ready", marker: "étape suivante proposée" };
      yield { event: "error", code: "overloaded", message: "Célestin est très sollicité." };
      yield { event: "turn.end", reason: "end", usage: {} };
    }),
  };
});

import { streamTurn } from "@/lib/tutor/client";
import { NEXT_STEP_MESSAGE } from "@/lib/tutor/prompts";
import { withLocale } from "@/test/locale";
import { mockApi, mountRoutes } from "@/test/route-harness";
import { Route as ChapterFile } from "../_auth/courses/$courseId/chapters/$chapterId/index";

const CHAPTER = {
  id: "suites",
  title: "Les suites numériques",
  position: 1,
  course_id: "maths",
  course_name: "Mathématiques 5e",
  language: "fr",
  subject: "mathematics",
  sections: [
    { id: "s1", index: 1, kind: "teach", title: "Suites numériques", goal: "Savoir lire uₙ." },
    { id: "s2", index: 2, kind: "practise", title: "Calculer un terme", goal: "g2" },
    { id: "s3", index: 3, kind: "synthesis", title: "Synthèse", goal: "g3" },
  ],
  progress: { done: ["s1"], active: "s2" },
};

const CHAPTER_PATH = "/api/courses/maths/chapters/suites";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function mountLesson() {
  mockApi(
    (_method, path) => {
      if (path.endsWith("/api/health")) return { body: { voice: false } };
      if (path.endsWith(CHAPTER_PATH)) return { body: CHAPTER };
      return undefined;
    },
    { locale: "en" },
  );
  mountRoutes(
    [{ path: "/courses/$courseId/chapters/$chapterId/", file: ChapterFile }],
    "/courses/maths/chapters/suites",
  );
}

/** The last thing the learner "said" in the most recent call to the model. */
const lastLearner = () => {
  const calls = vi.mocked(streamTurn).mock.calls;
  const history = calls[calls.length - 1]![1];
  const entry = history[history.length - 1]!;
  return entry.kind === "learner" ? entry.text : undefined;
};

describe("the lesson in English", () => {
  it("words the chrome in English and keeps course text French and marked as such", () =>
    withLocale("en", async () => {
      mountLesson();
      const greeting = await screen.findByText(/Bonjour, on reprend les suites/);
      // Célestin's words are French, and say so.
      expect(greeting.closest("[lang]")?.getAttribute("lang")).toBe("fr");

      // The bar: mode switch, content link, user menu.
      expect(screen.getByRole("button", { name: "Path" })).toBeTruthy();
      expect(screen.getByRole("button", { name: "Discussion" })).toBeTruthy();
      expect(screen.getByRole("link", { name: "Chapter content" })).toBeTruthy();
      const title = screen.getAllByText("Les suites numériques")[0]!;
      expect(title.closest("[lang]")?.getAttribute("lang")).toBe("fr");

      // The tutor column and its composer.
      expect(screen.getByText("Professor Célestin")).toBeTruthy();
      expect(screen.getByPlaceholderText("Write to Célestin…")).toBeTruthy();
      expect(screen.getByLabelText("Message for Célestin")).toBeTruthy();
      expect(screen.getByRole("button", { name: "Call (coming soon)" })).toBeTruthy();
      expect(screen.getByRole("button", { name: "See the chapter's path" })).toBeTruthy();

      // The board's own words follow the interface; the card is Célestin's.
      expect(screen.getByText("Board")).toBeTruthy();
      expect(screen.getByText("Let's check that you understood")).toBeTruthy();
      expect(screen.getAllByText("Question").length).toBeGreaterThan(0);
      const option = screen.getByText("Division par zéro");
      expect(option.closest("[lang]")?.getAttribute("lang")).toBe("fr");
      expect(screen.getByText("Board").closest("[lang]")?.getAttribute("lang")).not.toBe("fr");
      expect(
        screen.getByText("Let's check that you understood").closest("[lang]")?.getAttribute("lang"),
      ).not.toBe("fr");

      // A marker and an error from the server are shown as received, outside the French regions.
      const marker = screen.getByText(/étape suivante proposée/);
      expect(marker.closest('[lang="fr"]')).toBeNull();
      const error = screen.getByText(/Célestin est très sollicité\./);
      expect(error.closest('[lang="fr"]')).toBeNull();
    }));

  it("sends the French answer sentence when a choice is picked", () =>
    withLocale("en", async () => {
      mountLesson();
      fireEvent.click(await screen.findByText("Division par zéro"));
      await waitFor(() => expect(vi.mocked(streamTurn)).toHaveBeenCalledTimes(2));
      expect(lastLearner()).toBe("Ma réponse à la question : « Division par zéro ».");
    }));

  it("sends the French next-step sentence from the English button", () =>
    withLocale("en", async () => {
      mountLesson();
      const next = await screen.findByRole("button", { name: "Next step" });
      await waitFor(() => expect((next as HTMLButtonElement).disabled).toBe(false));
      fireEvent.click(next);
      await waitFor(() => expect(vi.mocked(streamTurn)).toHaveBeenCalledTimes(2));
      expect(lastLearner()).toBe(NEXT_STEP_MESSAGE);
      expect(lastLearner()).toBe("Étape suivante.");
    }));

  it("words the chapter map in English and sends French sentences from its buttons", () =>
    withLocale("en", async () => {
      mountLesson();
      await screen.findByText(/Bonjour, on reprend les suites/);
      fireEvent.click(screen.getByRole("button", { name: "See the chapter's path" }));
      const sheet = await screen.findByRole("dialog");
      expect(within(sheet).getByText("1 of 3 sections done")).toBeTruthy();
      const rows = within(sheet).getAllByRole("listitem");
      expect(within(rows[0]!).getByText("Lesson")).toBeTruthy();
      expect(within(rows[1]!).getByText("Practice")).toBeTruthy();
      expect(within(rows[2]!).getByText("Summary")).toBeTruthy();
      expect(within(rows[0]!).getByText("done")).toBeTruthy();
      expect(within(rows[2]!).getByText("locked")).toBeTruthy();
      expect(within(sheet).getByRole("button", { name: "Start the chapter over" })).toBeTruthy();
      // The sections' own titles are the course's.
      expect(within(rows[0]!).getByText("Suites numériques")).toBeTruthy();

      fireEvent.click(within(rows[0]!).getByRole("button", { name: "Review" }));
      await waitFor(() => expect(vi.mocked(streamTurn)).toHaveBeenCalledTimes(2));
      expect(lastLearner()).toBe("Je voudrais revoir la section « Suites numériques ».");
    }));

  it("asks for confirmation to restart in English", () =>
    withLocale("en", async () => {
      mountLesson();
      await screen.findByText(/Bonjour, on reprend les suites/);
      fireEvent.click(screen.getByRole("button", { name: "See the chapter's path" }));
      fireEvent.click(await screen.findByRole("button", { name: "Start the chapter over" }));
      const dialog = await screen.findByRole("alertdialog");
      expect(dialog.textContent).toContain("Start the chapter over?");
      expect(dialog.textContent).toContain(
        "Your progress in this chapter will be erased from your account and a new session will start at the first section.",
      );
      expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeTruthy();
    }));
});
