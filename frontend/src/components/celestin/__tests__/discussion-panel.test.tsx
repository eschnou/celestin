// @vitest-environment jsdom
/**
 * The discussion panel (spec 007): a first open creates the conversation once, a
 * restored one is shown without a new opening turn, and « Nouvelle conversation »
 * asks before replacing.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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
} as unknown as ChapterView;

const PATH = "/api/courses/maths/chapters/suites/discussion";

function conversation(entries: unknown[] = []) {
  return {
    id: "conv1",
    chapter_id: "suites",
    entries,
    entry_count: entries.length,
    created_at: "",
  };
}

function api(replies: (method: string) => { status?: number; body: unknown } | undefined) {
  const calls: { method: string; path: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, path: String(url) });
      const reply = replies(method);
      const status = reply?.status ?? 200;
      return {
        ok: status < 400,
        status,
        body: null,
        json: async () => reply?.body ?? {},
      };
    }),
  );
  return calls;
}

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DiscussionPanel chapter={CHAPTER} />
    </QueryClientProvider>,
  );
}

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

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("DiscussionPanel", () => {
  it("creates a conversation exactly once when the chapter has none", async () => {
    const calls = api((method) =>
      method === "GET"
        ? { body: { conversation: null } }
        : { status: 201, body: { conversation: conversation() } },
    );
    mount();
    await screen.findByRole("button", { name: "Nouvelle conversation" });
    await waitFor(() =>
      expect(calls.filter((c) => c.method === "POST" && c.path === PATH)).toHaveLength(1),
    );
  });

  it("shows a restored conversation without asking Célestin to open again", async () => {
    const calls = api(() => ({
      body: {
        conversation: conversation([
          { kind: "learner", text: "explique-moi les suites" },
          { kind: "tutor", text: "Une suite est une liste ordonnée." },
        ]),
      },
    }));
    mount();

    expect(await screen.findByText("Une suite est une liste ordonnée.")).toBeTruthy();
    // The caption holds Célestin's last words; the whole conversation is one tap away.
    fireEvent.click(
      screen.getByRole("button", { name: "Voir toute la conversation avec Célestin" }),
    );
    expect(await screen.findByText("explique-moi les suites")).toBeTruthy();
    // No turn was started: the only calls are the read.
    expect(calls.filter((c) => c.path.endsWith("/api/discussion/turn"))).toHaveLength(0);
  });

  it("asks before replacing the conversation, and says progress is untouched", async () => {
    api(() => ({ body: { conversation: conversation([{ kind: "tutor", text: "Salut" }]) } }));
    mount();
    await screen.findByText("Salut");

    fireEvent.click(screen.getByRole("button", { name: "Nouvelle conversation" }));
    expect(await screen.findByText("Nouvelle conversation ?")).toBeTruthy();
    expect(screen.getByText(/progression dans le parcours n'est pas touchée/)).toBeTruthy();
  });

  it("shows no chapter strip: nothing here can move the path", async () => {
    api(() => ({ body: { conversation: conversation() } }));
    mount();
    await screen.findByRole("button", { name: "Nouvelle conversation" });
    expect(screen.queryByRole("button", { name: /Voir le parcours du chapitre/ })).toBeNull();
  });
});
