// @vitest-environment jsdom
/**
 * The English sweep for the discussion panel (spec 010 R3, task 10.3): a restored
 * conversation as an English account reads it back (the server marks the tool calls in
 * English), with the confirmation to start a new one. Célestin's words are French and say so.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { stubLayoutApis } from "@/test/jsdom-stubs";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children }: { children: React.ReactNode }) => <a href="#">{children}</a>,
}));
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

import { DiscussionPanel } from "../discussion-panel";
import type { ChapterView } from "@/lib/tutor/types";
import { frenchOutsideCourseText } from "@/test/english-sweep";
import { withLocale } from "@/test/locale";

const CHAPTER = {
  id: "suites",
  title: "Les suites numériques",
  position: 1,
  course_id: "maths",
  course_name: "Maths Year 5",
  language: "fr",
  subject: "mathematics",
  sections: [{ id: "suites", index: 1, kind: "teach", title: "Suites", goal: "g" }],
  progress: { done: [], active: null },
} as unknown as ChapterView;

const STORED = {
  id: "conv1",
  chapter_id: "suites",
  entry_count: 4,
  created_at: "",
  entries: [
    { kind: "learner", text: "Explique-moi les suites" },
    { kind: "tutor", text: "Regarde le tableau." },
    {
      kind: "tool",
      name: "display_board",
      marker: "explanation shown",
      arguments: {
        card: {
          kind: "explanation",
          title: "Les suites",
          blocks: [{ type: "text", text: "Une suite est une liste ordonnée." }],
        },
      },
    },
    { kind: "tutor", text: "Tu suis ?" },
  ],
};

beforeEach(() => {
  stubLayoutApis();
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      status: 200,
      body: null,
      json: async () => ({ conversation: STORED }),
    })),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the English sweep: the discussion", () => {
  it("a restored conversation and the confirmation to start a new one", () =>
    withLocale("en", async () => {
      render(
        <QueryClientProvider
          client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
        >
          <DiscussionPanel chapter={CHAPTER} />
        </QueryClientProvider>,
      );
      await screen.findByRole("button", { name: "New conversation" });
      await screen.findByText(/Tu suis/);
      expect(frenchOutsideCourseText()).toEqual([]);
      fireEvent.click(screen.getByRole("button", { name: "New conversation" }));
      await screen.findByRole("alertdialog");
      expect(frenchOutsideCourseText()).toEqual([]);
    }));
});
