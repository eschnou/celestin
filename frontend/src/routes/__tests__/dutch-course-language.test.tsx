// @vitest-environment jsdom
/**
 * Spec 017 R2.6, R7.6: a Dutch course under each interface language, and an English course under a Dutch
 * interface. The course text says its own language with `lang` (never the interface's), whatever the buttons
 * around it say; and under a Dutch interface no French or English interface word is left anywhere.
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
      yield { event: "text.delta", block_id: 0, text: "Dag, we pakken de rijen weer op." };
      yield {
        event: "board.set",
        card: {
          kind: "check_question",
          question: "Waarom $q \\neq 1$ ?",
          options: [
            { id: "a", text: "Deling door nul" },
            { id: "b", text: "Uit gewoonte" },
          ],
          correct_option_id: "a",
          feedback: "Juist.",
        },
        // What an English account's server sends: the marker and the error in English.
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
import type { CourseLanguage } from "@/lib/course-language";
import type { Locale } from "@/lib/locale";

const chapter = (language: CourseLanguage) => ({
  id: "rijen",
  title: language === "nl" ? "Rijen" : "Sequences",
  position: 1,
  course_id: "maths",
  course_name: language === "nl" ? "Wiskunde 5e jaar" : "Maths Year 5",
  language,
  subject: "mathematics",
  sections: [
    { id: "s1", index: 1, kind: "teach", title: "Rijen", goal: "u_n lezen." },
    { id: "s2", index: 2, kind: "practise", title: "Een term berekenen", goal: "g2" },
    { id: "s3", index: 3, kind: "synthesis", title: "Samenvatting", goal: "g3" },
  ],
  progress: { done: ["s1"], active: "s2" },
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function mountLesson(locale: Locale, language: CourseLanguage) {
  mockApi(
    (_method, path) => {
      if (path.endsWith("/api/health")) return { body: { voice: false } };
      if (path.endsWith("/api/courses/maths/chapters/rijen")) return { body: chapter(language) };
      return undefined;
    },
    { locale, name: "Lea" },
  );
  mountRoutes(
    [{ path: "/courses/$courseId/chapters/$chapterId/", file: ChapterFile }],
    "/courses/maths/chapters/rijen",
  );
}

/** The `lang` of every region inside the page: the interface's own is on `<html>`. */
const regionLanguages = () =>
  new Set([...document.body.querySelectorAll("[lang]")].map((el) => el.getAttribute("lang")));

describe("a Dutch course", () => {
  it("under a French interface: the course text is marked Dutch, the chrome stays French", () =>
    withLocale("fr", async () => {
      mountLesson("fr", "nl");
      await screen.findByText(/Dag, we pakken de rijen weer op\./);
      expect(regionLanguages()).toEqual(new Set(["nl"]));
      const badge = screen.getByTestId("course-language");
      expect([badge.textContent, badge.getAttribute("lang")]).toEqual(["Nederlands", "nl"]);
      expect(screen.getByRole("button", { name: "Voir le parcours du chapitre" })).toBeTruthy();
    }));

  it("under an English interface: the course text is marked Dutch, the chrome stays English", () =>
    withLocale("en", async () => {
      mountLesson("en", "nl");
      await screen.findByText(/Dag, we pakken de rijen weer op\./);
      expect(regionLanguages()).toEqual(new Set(["nl"]));
      expect(screen.getByRole("button", { name: "See the chapter's path" })).toBeTruthy();
    }));

  it("under a Dutch interface: no French or English word is left, in the chrome or in the course", () =>
    withLocale("nl", async () => {
      mountLesson("nl", "nl");
      await screen.findByText(/Dag, we pakken de rijen weer op\./);
      await screen.findByText(/Célestin is erg druk op dit moment\./);
      expect(foreignTextOutside("nl")).toEqual([]);
      fireEvent.click(
        screen.getByRole("button", { name: "Het traject van het hoofdstuk bekijken" }),
      );
      await screen.findByRole("dialog");
      expect(foreignTextOutside("nl")).toEqual([]);
    }));
});

describe("another course under a Dutch interface", () => {
  it("an English course is marked English and its chrome is Dutch", () =>
    withLocale("nl", async () => {
      mountLesson("nl", "en");
      await screen.findByText(/Dag, we pakken de rijen weer op\./);
      expect(regionLanguages()).toEqual(new Set(["en"]));
      const badge = screen.getByTestId("course-language");
      expect([badge.textContent, badge.getAttribute("lang")]).toEqual(["English", "en"]);
      expect(
        screen.getByRole("button", { name: "Het traject van het hoofdstuk bekijken" }),
      ).toBeTruthy();
      expect(foreignTextOutside("nl")).toEqual([]); // the English text is marked, so it is not a leak
    }));
});
