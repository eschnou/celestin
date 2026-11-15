// @vitest-environment jsdom
/**
 * Révision (spec 020) in the interface: the chooser (preselection, `?chapter`, chapters not
 * ready, the POST, a refusal that keeps the choice), the live révision (restored or opened,
 * the quick replies in the course's language, no telephone), the « Bilan » (latest result
 * and its date, « pas encore testée », the links, a result noted live), « Nouvelle révision »
 * and a révision the server closed.
 */
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { stubLayoutApis } from "@/test/jsdom-stubs";

vi.mock("@/components/celestin/math", () => ({
  Math: ({ tex }: { tex: string }) => <span>{tex}</span>,
}));

vi.mock("@/lib/tutor/client", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/tutor/client")>();
  return { ...mod, streamEvents: vi.fn() };
});

import { formatDate } from "@/lib/i18n-format";
import { streamEvents } from "@/lib/tutor/client";
import type { StoredEntry, TutorEvent } from "@/lib/tutor/types";
import { mockApi, mountRoutes, type Reply } from "@/test/route-harness";
import { Route as RevisionFile } from "../_auth/courses/$courseId/revision";

const stream = vi.mocked(streamEvents);

const row = (over: Record<string, unknown>) => ({
  id: "h1",
  position: 1,
  title: "Les suites",
  ready: true,
  section_count: 3,
  done_count: 1,
  skipped_count: 1,
  state: "in_progress",
  last: true,
  authoring_state: "idle",
  authoring_message: null,
  authoring_stage: null,
  pages_done: 0,
  page_count: 0,
  authoring_received_chars: 0,
  authoring_quiet_s: null,
  ...over,
});

const course = (language = "fr") => ({
  id: "maths",
  name: "Mathématiques 5e",
  subject: "mathematics",
  subject_label: "Mathématiques",
  language,
  chapters_total: 3,
  chapters_done: 0,
  last_chapter: null,
  generating: 0,
  chapters: [
    row({}),
    row({ id: "h2", position: 2, title: "Les vecteurs", done_count: 0, skipped_count: 0 }),
    row({ id: "h3", position: 3, title: null, ready: false, section_count: 0 }),
  ],
});

const CHAPTERS = [
  {
    id: "h1",
    position: 1,
    title: "Les suites",
    ready: true,
    section_count: 3,
    done_count: 1,
    skipped_count: 1,
    sections: [
      { id: "s1", index: 1, kind: "teach", title: "Définir une suite", state: "done" },
      { id: "s2", index: 2, kind: "practise", title: "Calculer un terme", state: "skipped" },
      { id: "s3", index: 3, kind: "synthesis", title: "Synthèse", state: "todo" },
    ],
  },
  {
    id: "h2",
    position: 2,
    title: "Les vecteurs",
    ready: true,
    section_count: 1,
    done_count: 0,
    skipped_count: 0,
    sections: [{ id: "v1", index: 1, kind: "teach", title: "Un vecteur", state: "todo" }],
  },
  {
    id: "h3",
    position: 3,
    title: null,
    ready: false,
    section_count: 0,
    done_count: 0,
    skipped_count: 0,
    sections: [],
  },
];

const NOTED_AT = "2026-11-10T10:00:00Z";
const RESULTS = [{ chapter_id: "h1", section_id: "s1", outcome: "shaky", at: NOTED_AT }];

const CARD = {
  kind: "explanation",
  title: "La définition du cours",
  blocks: [{ type: "text", text: "Une suite est une fonction de ℕ dans ℝ." }],
};

const STORED: StoredEntry[] = [
  { kind: "tutor", text: "Bonjour ! On révise les suites ?" },
  { kind: "learner", text: "Oui." },
  {
    kind: "tool",
    name: "display_board",
    arguments: { card: CARD },
    marker: "explication affichée",
  },
  { kind: "tutor", text: "Compare avec ta réponse : acquis, fragile ou à revoir ?" },
];

const revision = (entries: StoredEntry[] = STORED, id = "r1") => ({
  id,
  chapter_ids: ["h1"],
  entries,
  entry_count: entries.length,
  created_at: "",
});

type View = { revision: ReturnType<typeof revision> | null; chapters: unknown; results: unknown };

const view = (live: ReturnType<typeof revision> | null = revision()): View => ({
  revision: live,
  chapters: CHAPTERS,
  results: RESULTS,
});

/** The server: `read` is what `GET …/revision` answers now (a function, for a test that
 *  changes it as turns are stored); a start answers with the same body as the read, the new
 *  révision in it, and the read becomes that. */
function mount(
  {
    read = view(),
    post,
    language = "fr",
  }: { read?: View | (() => View); post?: (body: unknown) => Reply; language?: string } = {},
  url = "/courses/maths/revision",
) {
  let started: View | null = null;
  const current = () => (typeof read === "function" ? read() : (started ?? read));
  const calls = mockApi((method, path, body) => {
    if (path.endsWith("/api/health")) return { body: { voice: true, dictation: false } };
    if (method === "GET" && path.endsWith("/api/courses/maths")) return { body: course(language) };
    if (path.endsWith("/api/courses/maths/revision")) {
      if (method === "GET") return { body: current() };
      if (method === "POST") {
        const reply = post?.(body) ?? {
          status: 201,
          body: { ...current(), revision: revision([], "r2") },
        };
        if (reply.status === 201) started = reply.body as View;
        return reply;
      }
    }
    return undefined;
  });
  mountRoutes([{ path: "/courses/$courseId/revision", file: RevisionFile }], url);
  return calls;
}

const reads = (calls: { method: string; path: string }[]) =>
  calls.filter((c) => c.method === "GET" && c.path.endsWith("/api/courses/maths/revision"));

const posts = (calls: { method: string; path: string; body: unknown }[]) =>
  calls.filter((c) => c.method === "POST" && c.path.endsWith("/api/courses/maths/revision"));

/** The turns posted, as the transport sent them. */
const turns = () => stream.mock.calls.map(([url, body]) => ({ url, body }));

function replies(...events: TutorEvent[]) {
  stream.mockImplementation(async function* () {
    yield { event: "turn.start", turn_id: "t" };
    for (const event of events) yield event;
    yield { event: "turn.end", reason: "end", usage: {} };
  });
}

beforeEach(() => {
  stubLayoutApis({ desktop: true });
  replies({ event: "text.delta", block_id: 0, text: "Bonjour, on révise ?" });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

const box = (name: RegExp) => screen.getByRole("checkbox", { name });

describe("the chooser", () => {
  it("lists every chapter, ticks those with progress, and starts on the ticked ones", async () => {
    const calls = mount({ read: view(null) });
    await screen.findByRole("heading", { name: "Que veux-tu réviser ?" });
    expect(box(/Les suites/).getAttribute("aria-checked")).toBe("true");
    expect(box(/Les vecteurs/).getAttribute("aria-checked")).toBe("false");
    // Its counts, as the course page writes them.
    expect(box(/Les suites/).closest("label")?.textContent).toMatch(/1 faite sur 3 · 1 passée/);
    // A chapter not ready is listed, disabled, and says why.
    const notReady = box(/Nouveau chapitre 3/);
    expect(notReady.hasAttribute("disabled")).toBe(true);
    expect(notReady.closest("label")?.textContent).toMatch(/pas encore prêt/);

    fireEvent.click(box(/Les vecteurs/));
    fireEvent.click(screen.getByRole("button", { name: "Commencer la révision" }));
    await waitFor(() => expect(posts(calls)).toHaveLength(1));
    expect(posts(calls)[0]!.body).toEqual({ chapter_ids: ["h1", "h2"] });
    // The new révision opens: Célestin speaks first, on the révision's route.
    expect(await screen.findByText("Bonjour, on révise ?")).toBeTruthy();
    expect(turns()).toEqual([
      {
        url: "/api/revision/turn",
        body: { course_id: "maths", revision_id: "r2", message: null },
      },
    ]);
  });

  it("reads the révision once on page load", async () => {
    const calls = mount();
    await screen.findByText(/Compare avec ta réponse/);
    // The read also closes a changed révision: once, not once by the loader and again by the page.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(reads(calls)).toHaveLength(1);
  });

  it("reads the révision once even when the course answers after it", async () => {
    const calls = mockApi((method, path) => {
      if (path.endsWith("/api/health")) return { body: { voice: true, dictation: false } };
      if (method === "GET" && path.endsWith("/api/courses/maths")) return { body: course() };
      if (method === "GET" && path.endsWith("/api/courses/maths/revision")) return { body: view() };
      return undefined;
    });
    const answer = globalThis.fetch;
    vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
      if (String(url).endsWith("/api/courses/maths"))
        await new Promise((resolve) => setTimeout(resolve, 30));
      return answer(url, init);
    });
    mountRoutes(
      [{ path: "/courses/$courseId/revision", file: RevisionFile }],
      "/courses/maths/revision",
    );
    await screen.findByText(/Compare avec ta réponse/);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(reads(calls)).toHaveLength(1);
  });

  it("takes the start's answer as the read, and reads nothing again", async () => {
    const noted = [
      ...RESULTS,
      { chapter_id: "h1", section_id: "s2", outcome: "solid", at: NOTED_AT },
    ];
    const calls = mount({
      read: view(null),
      post: () => ({
        status: 201,
        body: { revision: revision([], "r2"), chapters: CHAPTERS, results: noted },
      }),
    });
    await screen.findByRole("heading", { name: "Que veux-tu réviser ?" });
    fireEvent.click(screen.getByRole("button", { name: "Commencer la révision" }));
    await screen.findByText("Bonjour, on révise ?");
    expect(reads(calls)).toHaveLength(1);
    // The « Bilan » is the start's answer: the results the closed révision noted included.
    fireEvent.click(screen.getByRole("button", { name: "Bilan" }));
    const sheet = await screen.findByRole("dialog", { name: "Bilan de la révision" });
    const s2 = sheet.querySelector<HTMLElement>('[data-section="s2"]')!;
    expect(within(s2).getByText("Acquis")).toBeTruthy();
  });

  it("ticks every ready chapter when none has progress", async () => {
    const fresh = CHAPTERS.map((c) => ({ ...c, done_count: 0, skipped_count: 0 }));
    mount({ read: { revision: null, chapters: fresh, results: [] } });
    await screen.findByRole("heading", { name: "Que veux-tu réviser ?" });
    expect(box(/Les suites/).getAttribute("aria-checked")).toBe("true");
    expect(box(/Les vecteurs/).getAttribute("aria-checked")).toBe("true");
    expect(box(/Nouveau chapitre 3/).getAttribute("aria-checked")).toBe("false");
  });

  it("ticks only the chapter she came from", async () => {
    mount({ read: view(null) }, "/courses/maths/revision?chapter=h2");
    await screen.findByRole("heading", { name: "Que veux-tu réviser ?" });
    expect(box(/Les vecteurs/).getAttribute("aria-checked")).toBe("true");
    expect(box(/Les suites/).getAttribute("aria-checked")).toBe("false");
  });

  it("cannot start with nothing ticked", async () => {
    mount({ read: view(null) });
    await screen.findByRole("heading", { name: "Que veux-tu réviser ?" });
    fireEvent.click(box(/Les suites/));
    expect(
      screen.getByRole("button", { name: "Commencer la révision" }).hasAttribute("disabled"),
    ).toBe(true);
  });

  it("says the server's refusal above the list and keeps the choice", async () => {
    const calls = mount({
      read: view(null),
      post: () => ({
        status: 422,
        body: {
          code: "revision_too_large",
          message: "Ces chapitres font trop de matière pour une révision : choisis-en moins.",
        },
      }),
    });
    await screen.findByRole("heading", { name: "Que veux-tu réviser ?" });
    fireEvent.click(box(/Les vecteurs/));
    fireEvent.click(screen.getByRole("button", { name: "Commencer la révision" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/trop de matière/);
    expect(posts(calls)).toHaveLength(1);
    expect(box(/Les suites/).getAttribute("aria-checked")).toBe("true");
    expect(box(/Les vecteurs/).getAttribute("aria-checked")).toBe("true");
    expect(stream).not.toHaveBeenCalled();
  });
});

describe("a live révision", () => {
  it("restores the transcript and the board without a new opening turn, and has no telephone", async () => {
    mount();
    expect(await screen.findByText(/Compare avec ta réponse/)).toBeTruthy();
    expect(screen.getByText("Oui.")).toBeTruthy();
    expect(screen.getAllByText("La définition du cours").length).toBeGreaterThan(0);
    expect(stream).not.toHaveBeenCalled();
    // No voice in révision (D5), even when the server offers it.
    expect(screen.queryByRole("button", { name: /Appeler/ })).toBeNull();
    // No strip, no map: nothing here moves the path.
    expect(screen.queryByRole("button", { name: /Voir le parcours du chapitre/ })).toBeNull();
  });

  it("opens an empty révision with Célestin's first turn", async () => {
    mount({ read: view(revision([])) });
    expect(await screen.findByText("Bonjour, on révise ?")).toBeTruthy();
    expect(turns()).toEqual([
      { url: "/api/revision/turn", body: { course_id: "maths", revision_id: "r1", message: null } },
    ]);
  });

  it("sends the quick replies as her sentence, and waits while Célestin answers", async () => {
    let release = () => {};
    stream.mockImplementation(async function* () {
      yield { event: "turn.start", turn_id: "t" };
      await new Promise<void>((resolve) => (release = resolve));
      yield { event: "text.delta", block_id: 0, text: "Noté." };
      yield { event: "turn.end", reason: "end", usage: {} };
    });
    mount();
    await screen.findByText(/Compare avec ta réponse/);
    const group = screen.getByRole("group", { name: "Comment ça s'est passé ?" });
    fireEvent.click(within(group).getByRole("button", { name: "Fragile" }));
    await waitFor(() => expect(stream).toHaveBeenCalledTimes(1));
    expect(turns()[0]!.body).toEqual({
      course_id: "maths",
      revision_id: "r1",
      message: "Pour moi, c'est fragile.",
    });
    for (const name of ["Acquis", "Fragile", "À revoir"])
      expect(within(group).getByRole("button", { name }).hasAttribute("disabled")).toBe(true);
    release();
    await screen.findByText("Noté.");
    expect(within(group).getByRole("button", { name: "Acquis" }).hasAttribute("disabled")).toBe(
      false,
    );
  });

  it("says her sentence in the course's language, whatever the interface's", async () => {
    mount({ language: "en" });
    await screen.findByText(/Compare avec ta réponse/);
    fireEvent.click(screen.getByRole("button", { name: "À revoir" }));
    await waitFor(() => expect(stream).toHaveBeenCalledTimes(1));
    expect((turns()[0]!.body as { message: string }).message).toBe("I'd say I need to review it.");
  });

  it("has no telephone on a phone either", async () => {
    stubLayoutApis({ desktop: false });
    mount();
    await screen.findByText(/Compare avec ta réponse/);
    expect(screen.queryByRole("button", { name: /Appeler/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Bilan" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Fragile" })).toBeTruthy();
  });
});

describe("the « Bilan »", () => {
  const openBilan = async () => {
    fireEvent.click(await screen.findByRole("button", { name: "Bilan" }));
    return screen.findByRole("dialog", { name: "Bilan de la révision" });
  };
  const sectionRow = (sheet: HTMLElement, id: string) =>
    sheet.querySelector<HTMLElement>(`[data-section="${id}"]`)!;

  it("shows each section's latest result and date, or that it was not tested, and the ways to work on it", async () => {
    mount();
    const sheet = await openBilan();
    expect(within(sheet).getByText(/ce sont tes propres bilans/i)).toBeTruthy();
    // Only the révision's chapters.
    expect(within(sheet).getByText("Les suites")).toBeTruthy();
    expect(within(sheet).queryByText("Les vecteurs")).toBeNull();

    const s1 = sectionRow(sheet, "s1");
    expect(within(s1).getByText("Fragile")).toBeTruthy();
    expect(within(s1).getByText(`noté le ${formatDate(NOTED_AT)}`)).toBeTruthy();
    expect(within(s1).getByRole("link", { name: "Parcours" }).getAttribute("href")).toBe(
      "/courses/maths/chapters/h1",
    );
    expect(within(s1).getByRole("link", { name: "Cahier" }).getAttribute("href")).toBe(
      "/courses/maths/chapters/h1/notebook#s1",
    );

    const s2 = sectionRow(sheet, "s2");
    expect(within(s2).getByText("pas encore testée")).toBeTruthy();
    expect(within(s2).getByText("passée")).toBeTruthy();
    // Not done: nothing in the cahier to reread.
    expect(within(s2).queryByRole("link", { name: "Cahier" })).toBeNull();
    expect(within(s2).getByRole("link", { name: "Parcours" })).toBeTruthy();

    expect(within(sectionRow(sheet, "s3")).getByText("pas encore faite")).toBeTruthy();
  });

  it("shows a result the moment Célestin notes it", async () => {
    replies(
      {
        event: "revision.result",
        chapter_id: "h1",
        section_id: "s2",
        outcome: "solid",
        marker: "noté : acquis · 2. Calculer un terme",
      },
      { event: "text.delta", block_id: 0, text: "C'est noté." },
    );
    mount();
    await screen.findByText(/Compare avec ta réponse/);
    fireEvent.click(screen.getByRole("button", { name: "Acquis" }));
    await screen.findByText("C'est noté.");
    // The marker says what was recorded about her.
    expect(screen.getByText(/noté : acquis/)).toBeTruthy();
    const sheet = await openBilan();
    const s2 = sectionRow(sheet, "s2");
    expect(within(s2).getByText("Acquis")).toBeTruthy();
    expect(within(s2).getByText(`noté le ${formatDate(new Date().toISOString())}`)).toBeTruthy();
    expect(within(s2).queryByText("pas encore testée")).toBeNull();
  });
});

describe("« Nouvelle révision »", () => {
  it("asks first, goes back to the chooser, and starts a new one from there", async () => {
    const calls = mount();
    await screen.findByText(/Compare avec ta réponse/);
    fireEvent.click(screen.getByRole("button", { name: "Nouvelle révision" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText(/Tes bilans sont gardés/)).toBeTruthy();
    expect(posts(calls)).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole("button", { name: "Nouvelle révision" }));

    await screen.findByRole("heading", { name: "Que veux-tu réviser ?" });
    expect(screen.getByRole("button", { name: "Revenir à la révision en cours" })).toBeTruthy();
    expect(posts(calls)).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Commencer la révision" }));
    await waitFor(() => expect(posts(calls)).toHaveLength(1));
    expect(await screen.findByText("Bonjour, on révise ?")).toBeTruthy();
    expect((turns()[0]!.body as { revision_id: string }).revision_id).toBe("r2");
  });

  it("goes back to the révision in progress without starting anything", async () => {
    const calls = mount();
    await screen.findByText(/Compare avec ta réponse/);
    fireEvent.click(screen.getByRole("button", { name: "Nouvelle révision" }));
    fireEvent.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", {
        name: "Nouvelle révision",
      }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "Revenir à la révision en cours" }));
    expect(await screen.findByText(/Compare avec ta réponse/)).toBeTruthy();
    expect(posts(calls)).toHaveLength(0);
  });

  /** « Nouvelle révision », confirmed: the chooser. */
  const toChooser = async () => {
    fireEvent.click(screen.getByRole("button", { name: "Nouvelle révision" }));
    fireEvent.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", {
        name: "Nouvelle révision",
      }),
    );
    await screen.findByRole("heading", { name: "Que veux-tu réviser ?" });
  };

  it("goes back to the révision as the server has it, the turns made since included", async () => {
    replies({ event: "text.delta", block_id: 0, text: "C'est noté, on continue." });
    // The server stores each turn: its read after the turn holds it.
    let stored = STORED;
    const calls = mount({ read: () => view(revision(stored)) });
    await screen.findByText(/Compare avec ta réponse/);
    fireEvent.click(screen.getByRole("button", { name: "Acquis" }));
    await screen.findByText("C'est noté, on continue.");
    stored = [
      ...STORED,
      { kind: "learner", text: "Pour moi, c'est acquis." },
      { kind: "tutor", text: "C'est noté, on continue." },
    ];

    await toChooser();
    fireEvent.click(screen.getByRole("button", { name: "Revenir à la révision en cours" }));
    expect(await screen.findByText("C'est noté, on continue.")).toBeTruthy();
    expect(screen.getByText(/Compare avec ta réponse/)).toBeTruthy();
    expect(reads(calls)).toHaveLength(2);
    // The one turn she made; no opening turn on the way back.
    expect(turns()).toHaveLength(1);
    expect(posts(calls)).toHaveLength(0);
  });

  it("goes back to a révision started on this page without opening it again", async () => {
    let read = view(null);
    const calls = mount({ read: () => read });
    await screen.findByRole("heading", { name: "Que veux-tu réviser ?" });
    fireEvent.click(screen.getByRole("button", { name: "Commencer la révision" }));
    await screen.findByText("Bonjour, on révise ?");
    read = view(revision([{ kind: "tutor", text: "Bonjour, on révise ?" }], "r2"));

    await toChooser();
    fireEvent.click(screen.getByRole("button", { name: "Revenir à la révision en cours" }));
    expect(await screen.findByText("Bonjour, on révise ?")).toBeTruthy();
    await new Promise((resolve) => setTimeout(resolve, 20));
    // Only the opening of the start: the server's read has it, so none is posted again.
    expect(turns()).toHaveLength(1);
    expect(posts(calls)).toHaveLength(1);
  });

  it("offers a new one when the server closed this one", async () => {
    stream.mockImplementation(async function* () {
      yield {
        event: "error",
        code: "conversation_closed",
        message: "Le contenu d'un chapitre a changé : cette révision est close.",
      };
      yield { event: "turn.end", reason: "end", usage: {} };
    });
    mount();
    await screen.findByText(/Compare avec ta réponse/);
    fireEvent.click(screen.getByRole("button", { name: "Acquis" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/cette révision est close/);
    fireEvent.click(within(alert).getByRole("button", { name: "Nouvelle révision" }));
    expect(await screen.findByRole("heading", { name: "Que veux-tu réviser ?" })).toBeTruthy();
  });

  it("stays in the chooser, without the way back, when the server has no live révision", async () => {
    stream.mockImplementation(async function* () {
      yield { event: "error", code: "conversation_closed", message: "Révision close." };
      yield { event: "turn.end", reason: "end", usage: {} };
    });
    let read = view();
    const calls = mount({ read: () => read });
    await screen.findByText(/Compare avec ta réponse/);
    fireEvent.click(screen.getByRole("button", { name: "Acquis" }));
    const alert = await screen.findByRole("alert");
    read = view(null);
    fireEvent.click(within(alert).getByRole("button", { name: "Nouvelle révision" }));
    fireEvent.click(await screen.findByRole("button", { name: "Revenir à la révision en cours" }));
    await waitFor(() => expect(reads(calls)).toHaveLength(2));
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Revenir à la révision en cours" })).toBeNull(),
    );
    expect(screen.getByRole("heading", { name: "Que veux-tu réviser ?" })).toBeTruthy();
    expect(screen.queryByText(/Compare avec ta réponse/)).toBeNull();
    expect(turns()).toHaveLength(1);
  });

  it("says the révision is closed when the server gives no words for it", async () => {
    stream.mockImplementation(async function* () {
      yield { event: "error", code: "conversation_closed", message: "" };
      yield { event: "turn.end", reason: "end", usage: {} };
    });
    mount();
    await screen.findByText(/Compare avec ta réponse/);
    fireEvent.click(screen.getByRole("button", { name: "Acquis" }));
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Cette révision est close.")).toBeTruthy();
  });
});
