// @vitest-environment jsdom
/**
 * The lesson resumes where it stopped (spec 018 D6): it reads the live séance and the
 * progress together before mounting the session, folds the séance back, and opens only
 * when nothing is stored. The map offers « Relire » on sections with stored boards, the
 * bar links to the cahier, and « Recommencer le chapitre » says the cahier goes too.
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

vi.mock("@/components/celestin/math", () => ({
  Math: ({ tex }: { tex: string }) => <span>{tex}</span>,
}));

vi.mock("@/lib/tutor/client", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/tutor/client")>();
  return {
    ...mod,
    streamTurn: vi.fn(async function* () {
      yield { event: "turn.start", turn_id: "t1" };
      yield { event: "text.delta", block_id: 0, text: "Bonjour, on commence." };
      yield { event: "section.start", section_id: "s2", review: false, marker: "section ouverte" };
      yield {
        event: "board.set",
        card: { kind: "explanation", title: "Le terme général", blocks: [] },
        marker: "explication affichée",
      };
      yield { event: "turn.end", reason: "end", usage: {} };
    }),
  };
});

import { streamTurn } from "@/lib/tutor/client";
import type { Progress, StoredEntry } from "@/lib/tutor/types";
import { mockApi, mountRoutes, type Reply } from "@/test/route-harness";
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
    { id: "s1", index: 1, kind: "teach", title: "Suites numériques", goal: "g1" },
    { id: "s2", index: 2, kind: "practise", title: "Calculer un terme", goal: "g2" },
    { id: "s3", index: 3, kind: "synthesis", title: "Synthèse", goal: "g3" },
  ],
  progress: { done: ["s1"], active: "s2", skipped: [] },
};

const CHAPTER_PATH = "/api/courses/maths/chapters/suites";
const CARD = { kind: "explanation", title: "Le terme général", blocks: [] };

/** A séance stopped mid-section: the board on a card, the page-turn button live. */
const ENTRIES: StoredEntry[] = [
  { kind: "tutor", text: "Bonjour Léa." },
  { kind: "learner", text: "On commence ?" },
  {
    kind: "tool",
    name: "start_section",
    arguments: { section_id: "s2" },
    review: false,
    marker: "section ouverte",
  },
  {
    kind: "tool",
    name: "display_board",
    arguments: { card: CARD },
    marker: "explication affichée",
  },
  { kind: "tutor", text: "Tu suis jusque-là ?" },
  { kind: "tool", name: "propose_next_step", arguments: {}, marker: "étape suivante proposée" },
];

const seance = (entries: StoredEntry[]) => ({ id: "row1", section_id: "s2", entries });

/** `GET …/seance`: the live séance, with the progress and the stored card counts read beside
 *  it (s1's boards are in the cahier). */
const start = (live: ReturnType<typeof seance> | null, progress: Progress = CHAPTER.progress) => ({
  body: { seance: live, progress, seances: { s1: { cards: 4 } } },
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function mountLesson(
  over: {
    seance?: () => Reply;
    chapter?: () => Reply;
  } = {},
) {
  const calls = mockApi((method, path) => {
    if (path.endsWith("/api/health")) return { body: { voice: false } };
    if (method === "GET" && path.endsWith(CHAPTER_PATH))
      return over.chapter?.() ?? { body: CHAPTER };
    if (method === "GET" && path.endsWith(`${CHAPTER_PATH}/seance`))
      return over.seance?.() ?? start(null);
    if (method === "DELETE" && path.endsWith(`${CHAPTER_PATH}/progress`)) return { body: {} };
    return undefined;
  });
  mountRoutes(
    [{ path: "/courses/$courseId/chapters/$chapterId/", file: ChapterFile }],
    "/courses/maths/chapters/suites",
  );
  return calls;
}

const openMap = async () => {
  fireEvent.click(screen.getByRole("button", { name: "Voir le parcours du chapitre" }));
  return screen.findByRole("dialog");
};

describe("a lesson with a stored séance", () => {
  it("restores the transcript and the board, says it resumed, and does not open again", async () => {
    mountLesson({ seance: () => start(seance(ENTRIES)) });
    await screen.findByText("Tu suis jusque-là ?");
    expect(screen.getByText("Bonjour Léa.")).toBeTruthy();
    expect(screen.getByText("On commence ?")).toBeTruthy();
    // The board is where it was, and so is the page-turn button.
    expect(screen.getAllByText("Le terme général").length).toBeGreaterThan(0);
    const next = screen.getByRole("button", { name: "Étape suivante" }) as HTMLButtonElement;
    expect(next.disabled).toBe(false);
    // « séance reprise » closes the transcript.
    const log = screen.getByText(/séance reprise/).closest("p")!;
    const markers = Array.from(document.querySelectorAll("p")).filter((p) =>
      p.textContent?.startsWith("→"),
    );
    expect(markers.at(-1)).toBe(log);
    await new Promise((r) => setTimeout(r, 20));
    expect(vi.mocked(streamTurn)).not.toHaveBeenCalled();
  });

  it("shows the progress read with the séance, not the chapter view's or the replay's", async () => {
    // The replay would make s2 active, and so does the chapter view (cached, it can be
    // stale); the progress read with the séance says s2 is done since.
    let reads = 0;
    const calls = mountLesson({
      seance: () => start(seance(ENTRIES), { done: ["s1", "s2"], active: null, skipped: [] }),
      chapter: () => {
        reads += 1;
        return { body: CHAPTER };
      },
    });
    await screen.findByText("Tu suis jusque-là ?");
    const sheet = await openMap();
    const rows = within(sheet).getAllByRole("listitem");
    expect(rows.map((r) => r.getAttribute("data-state"))).toEqual(["done", "done", "available"]);
    // One read of each: the lesson does not read the chapter view a second time.
    expect(reads).toBe(1);
    expect(calls.filter((c) => c.path.endsWith(`${CHAPTER_PATH}/seance`))).toHaveLength(1);
  });

  it("then posts the learner's message, never the transcript", async () => {
    mountLesson({ seance: () => start(seance(ENTRIES)) });
    await screen.findByText("Tu suis jusque-là ?");
    fireEvent.click(screen.getByRole("button", { name: "Étape suivante" }));
    await waitFor(() => expect(vi.mocked(streamTurn)).toHaveBeenCalledTimes(1));
    const [scope, message] = vi.mocked(streamTurn).mock.calls[0]!;
    expect(scope).toEqual({ courseId: "maths", chapterId: "suites" });
    expect(message).toBe("Étape suivante.");
  });
});

describe("a lesson with nothing stored", () => {
  it("opens with the opening turn when there is no séance", async () => {
    mountLesson();
    await screen.findByText("Bonjour, on commence.");
    expect(vi.mocked(streamTurn)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(streamTurn).mock.calls[0]![1]).toBeNull();
    expect(screen.queryByText(/séance reprise/)).toBeNull();
  });

  it("opens with the opening turn when the séance is empty", async () => {
    mountLesson({ seance: () => start(seance([])) });
    await screen.findByText("Bonjour, on commence.");
    expect(vi.mocked(streamTurn)).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/séance reprise/)).toBeNull();
  });

  it("says when the séance cannot be read, and tries again", async () => {
    let fail = true;
    mountLesson({
      seance: () =>
        fail
          ? { status: 500, body: { code: "server_error", message: "Panne du serveur." } }
          : start(null),
    });
    await screen.findByText(/Panne du serveur\./);
    expect(vi.mocked(streamTurn)).not.toHaveBeenCalled();
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    await screen.findByText("Bonjour, on commence.");
  });
});

describe("the cahier's entry points", () => {
  it("links the bar to the cahier", async () => {
    mountLesson();
    await screen.findByText("Bonjour, on commence.");
    const link = screen.getByRole("link", { name: "Cahier" });
    expect(link.getAttribute("href")).toBe("/courses/maths/chapters/suites/notebook");
  });

  it("offers « Relire » on stored sections and on the one shown this page load", async () => {
    mountLesson();
    // The opening turn starts s2 and shows a card in it.
    await screen.findByText("Bonjour, on commence.");
    await waitFor(() => expect(screen.getAllByText("Le terme général").length).toBeGreaterThan(0));
    const sheet = await openMap();
    const rows = within(sheet).getAllByRole("listitem");
    const reread = (row: HTMLElement) => within(row).queryByRole("link", { name: "Relire" });
    expect(reread(rows[0]!)?.getAttribute("href")).toBe(
      "/courses/maths/chapters/suites/notebook#s1",
    );
    // A done row keeps « Revoir » beside it.
    expect(within(rows[0]!).getByRole("button", { name: "Revoir" })).toBeTruthy();
    expect(reread(rows[1]!)?.getAttribute("href")).toBe(
      "/courses/maths/chapters/suites/notebook#s2",
    );
    expect(reread(rows[2]!)).toBeNull();
  });

  it("offers « Reprendre » where a séance exists, and the page turns with it (spec 019)", async () => {
    vi.mocked(streamTurn).mockImplementationOnce(async function* () {
      yield { event: "turn.start", turn_id: "t1" };
      yield { event: "text.delta", block_id: 0, text: "Bonjour, on commence." };
      yield { event: "section.start", section_id: "s1", review: false, marker: "section ouverte" };
      yield { event: "board.set", card: CARD as never, marker: "explication affichée" };
      yield {
        event: "section.skipped",
        section_id: "s1",
        next_section_id: "s2",
        active_section_id: null,
        marker: "passée",
      };
      yield { event: "turn.end", reason: "end", usage: {} };
    });
    const progress = { done: [], active: null, skipped: [] };
    mountLesson({
      seance: () => ({ body: { seance: null, progress, seances: { s2: { cards: 0 } } } }),
    });
    await screen.findByText("Bonjour, on commence.");
    const sheet = await openMap();
    const rows = within(sheet).getAllByRole("listitem");
    // s1 was started this page load, then skipped; s2 has a séance stored from before.
    expect(rows.map((r) => r.getAttribute("data-state"))).toEqual(["skipped", "available", "open"]);
    expect(within(rows[0]!).getByRole("button", { name: "Reprendre" })).toBeTruthy();
    expect(within(rows[1]!).getByRole("button", { name: "Reprendre" })).toBeTruthy();
    expect(within(rows[2]!).getByRole("button", { name: "Commencer" })).toBeTruthy();
    fireEvent.keyDown(sheet, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    fireEvent.click(screen.getAllByRole("button", { name: "Section suivante" })[0]!);
    await waitFor(() => expect(vi.mocked(streamTurn)).toHaveBeenCalledTimes(2));
    expect(vi.mocked(streamTurn).mock.calls[1]![1]).toBe(
      "On reprend la section « Calculer un terme » ?",
    );
  });

  it("takes a progress without `skipped` (a backend older than spec 019)", async () => {
    vi.mocked(streamTurn).mockImplementationOnce(async function* () {
      yield { event: "turn.start", turn_id: "t1" };
      yield { event: "text.delta", block_id: 0, text: "Bonjour, on commence." };
      yield { event: "section.start", section_id: "s1", review: false, marker: "section ouverte" };
      yield { event: "turn.end", reason: "end", usage: {} };
    });
    mountLesson({
      seance: () => ({ body: { seance: null, progress: { done: [], active: null }, seances: {} } }),
    });
    await screen.findByText("Bonjour, on commence.");
    const sheet = await openMap();
    const rows = within(sheet).getAllByRole("listitem");
    expect(rows.map((r) => r.getAttribute("data-state"))).toEqual(["active", "open", "open"]);
  });

  it("says the cahier is erased with the progress, and leaves nothing to reread", async () => {
    const calls = mountLesson({ seance: () => start(seance(ENTRIES)) });
    await screen.findByText("Tu suis jusque-là ?");
    let sheet = await openMap();
    expect(within(sheet).getAllByRole("link", { name: "Relire" })).toHaveLength(2);
    fireEvent.click(within(sheet).getByRole("button", { name: "Recommencer le chapitre" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain(
      "Ta progression dans ce chapitre et ton cahier seront effacés de ton compte, et une nouvelle séance démarrera à la première section.",
    );
    vi.mocked(streamTurn).mockImplementationOnce(async function* () {
      yield { event: "turn.start", turn_id: "t2" };
      yield { event: "text.delta", block_id: 0, text: "On recommence." };
      yield { event: "turn.end", reason: "end", usage: {} };
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Recommencer" }));
    // An empty session, then the opening turn.
    await screen.findByText("On recommence.");
    expect(calls.some((c) => c.method === "DELETE" && c.path.endsWith("/progress"))).toBe(true);
    expect(screen.queryByText("Tu suis jusque-là ?")).toBeNull();
    expect(screen.queryByText(/séance reprise/)).toBeNull();
    expect(vi.mocked(streamTurn).mock.calls[0]![1]).toBeNull();
    sheet = await openMap();
    expect(within(sheet).queryAllByRole("link", { name: "Relire" })).toHaveLength(0);
  });
});
