import { describe, expect, it } from "vitest";

import {
  appendLearner,
  EMPTY_SESSION,
  reduce,
  sessionFromEntries,
  type SessionState,
} from "@/components/celestin/use-tutor-session";
import type { BoardCard, StoredEntry, TutorEvent } from "@/lib/tutor/types";

const CARD: BoardCard = {
  kind: "explanation",
  title: "Les suites",
  blocks: [{ type: "text", text: "Bonjour" }],
};

const board = (marker: string): StoredEntry => ({
  kind: "tool",
  name: "display_board",
  arguments: { card: CARD },
  marker,
});

describe("sessionFromEntries", () => {
  it("restores an empty conversation as an empty session", () => {
    const state = sessionFromEntries([]);
    expect(state.entries).toEqual([]);
    expect(state.board).toBeNull();
    expect(state.boards).toEqual([]);
  });

  it("restores the transcript, the board and the markers", () => {
    const state = sessionFromEntries([
      { kind: "learner", text: "explique-moi" },
      { kind: "tutor", text: "Regarde." },
      board("explication affichée"),
      { kind: "tutor", text: "Tu suis ?" },
    ]);

    expect(state.entries.map((e) => e.role)).toEqual(["learner", "tutor", "marker", "tutor"]);
    expect(state.entries[0]).toMatchObject({ role: "learner", text: "explique-moi" });
    expect(state.entries[2]).toMatchObject({ role: "marker", text: "explication affichée" });
    expect(state.board).toEqual(CARD);
    expect(state.boards).toEqual([CARD]);
  });

  it("gives the model back the same history the live turn would have", () => {
    const state = sessionFromEntries([
      { kind: "learner", text: "salut" },
      { kind: "tutor", text: "bonjour" },
      board("explication affichée"),
    ]);
    expect(state.history).toEqual([
      { kind: "learner", text: "salut" },
      { kind: "tutor", text: "bonjour" },
      { kind: "tool", name: "display_board", arguments: { card: CARD }, ok: true },
    ]);
  });

  it("leaves the board empty after a trailing clear", () => {
    const state = sessionFromEntries([
      board("explication affichée"),
      { kind: "tool", name: "clear_board", arguments: {}, marker: "tableau effacé" },
    ]);
    expect(state.board).toBeNull();
    // The card stays in the history strip, as it does live.
    expect(state.boards).toEqual([CARD]);
  });

  it("never restores a pending next step", () => {
    expect(sessionFromEntries([board("explication affichée")]).nextStep).toBeNull();
  });

  it("keeps each tutor entry its own block, so text around a card stays ordered", () => {
    const state = sessionFromEntries([
      { kind: "tutor", text: "avant" },
      board("explication affichée"),
      { kind: "tutor", text: "après" },
    ]);
    const texts = state.entries.filter((e) => e.role === "tutor").map((e) => e.text);
    expect(texts).toEqual(["avant", "après"]);
  });
});

// --- a parcours séance (018 D6) ---------------------------------------------------------

const TITLE: BoardCard = { kind: "title", eyebrow: "Section 2", title: "La somme", objective: "o" };
const RECAP: BoardCard = { kind: "recap", acquired: ["a"], watch: [], next: "n" };

const start = (sectionId: string, review = false): StoredEntry => ({
  kind: "tool",
  name: "start_section",
  arguments: { section_id: sectionId },
  review,
  marker: "section ouverte",
});
const done = (sectionId: string, next: string | null): StoredEntry => ({
  kind: "tool",
  name: "complete_section",
  arguments: { section_id: sectionId },
  next_section_id: next,
  marker: "section terminée",
});
const proposed: StoredEntry = {
  kind: "tool",
  name: "propose_next_step",
  arguments: {},
  marker: "étape suivante proposée",
};
const show = (card: BoardCard): StoredEntry => ({
  kind: "tool",
  name: "display_board",
  arguments: { card },
  marker: "carte affichée",
});

describe("sessionFromEntries on a parcours séance", () => {
  it("starts a section on a fresh board, as it did live", () => {
    const state = sessionFromEntries([show(CARD), start("s2"), show(TITLE), show(CARD)]);
    expect(state.boards).toEqual([TITLE, CARD]);
    expect(state.board).toEqual(CARD);
    expect(state.section).toBe("s2");
    expect(state.progress.active).toBe("s2");
    // The marker of the card before the section start no longer points at a board.
    const markers = state.entries.filter((e) => e.role === "marker");
    expect(markers[0]).toMatchObject({ text: "carte affichée", boardIndex: null });
    expect(markers.at(-1)).toMatchObject({ boardIndex: 1 });
  });

  it("keeps a review's path where it was, and records that it was one", () => {
    const state = sessionFromEntries([start("s1", true)]);
    expect(state.progress.active).toBeNull();
    expect(state.section).toBe("s1");
    expect(state.history).toEqual([
      {
        kind: "tool",
        name: "start_section",
        arguments: { section_id: "s1" },
        ok: true,
        review: true,
      },
    ]);
  });

  it("restores a proposed step", () => {
    expect(sessionFromEntries([start("s2"), show(CARD), proposed]).nextStep).toEqual({
      kind: "step",
    });
  });

  it("restores the next section after a closed one, through its recap card", () => {
    const state = sessionFromEntries([start("s2"), done("s2", "s3"), show(RECAP)]);
    expect(state.nextStep).toEqual({ kind: "section", sectionId: "s3" });
    expect(state.board).toEqual(RECAP);
  });

  it("offers nothing after the last section", () => {
    expect(sessionFromEntries([start("s4"), done("s4", null)]).nextStep).toBeNull();
  });

  it("puts out a pending step when the learner spoke after it", () => {
    const state = sessionFromEntries([
      start("s2"),
      show(CARD),
      proposed,
      { kind: "learner", text: "Je n'ai pas compris." },
      { kind: "tutor", text: "Reprenons." },
    ]);
    expect(state.nextStep).toBeNull();
  });

  it("puts out a closed section's offer when the learner spoke after it", () => {
    const state = sessionFromEntries([
      start("s2"),
      done("s2", "s3"),
      { kind: "learner", text: "Merci !" },
    ]);
    expect(state.nextStep).toBeNull();
  });

  it("yields the state the live events built", () => {
    const stored: StoredEntry[] = [
      { kind: "tutor", text: "Bonjour." },
      { kind: "learner", text: "On commence ?" },
      start("s2"),
      show(TITLE),
      { kind: "tutor", text: "Voici la définition." },
      show(CARD),
      proposed,
      { kind: "learner", text: "Étape suivante." },
      { kind: "tool", name: "clear_board", arguments: {}, marker: "tableau effacé" },
      show(RECAP),
      done("s2", "s3"),
    ];
    // The same séance as the browser lived it: the opening turn, then two learner turns.
    type Step = TutorEvent | { learner: string };
    const live: Step[] = [
      { event: "turn.start", turn_id: "t1" },
      { event: "text.delta", block_id: 0, text: "Bonjour." },
      { event: "turn.end", reason: "end", usage: {} },
      { learner: "On commence ?" },
      { event: "turn.start", turn_id: "t2" },
      { event: "section.start", section_id: "s2", review: false, marker: "section ouverte" },
      { event: "board.set", card: TITLE, marker: "carte affichée" },
      { event: "text.delta", block_id: 0, text: "Voici la définition." },
      { event: "board.set", card: CARD, marker: "carte affichée" },
      { event: "step.ready", marker: "étape suivante proposée" },
      { event: "turn.end", reason: "end", usage: {} },
      { learner: "Étape suivante." },
      { event: "turn.start", turn_id: "t3" },
      { event: "board.clear", marker: "tableau effacé" },
      { event: "board.set", card: RECAP, marker: "carte affichée" },
      {
        event: "section.done",
        section_id: "s2",
        next_section_id: "s3",
        marker: "section terminée",
      },
      { event: "turn.end", reason: "end", usage: {} },
    ];
    const lived = live.reduce<SessionState>(
      (state, step) =>
        "learner" in step ? appendLearner(state, step.learner) : reduce(state, step),
      EMPTY_SESSION,
    );
    const restored = sessionFromEntries(stored);
    const comparable = (state: SessionState) => ({
      entries: state.entries.map(({ id: _id, ...rest }) =>
        rest.role === "tutor" ? { ...rest, blockId: 0 } : rest,
      ),
      history: state.history,
      boards: state.boards,
      board: state.board,
      progress: state.progress,
      nextStep: state.nextStep,
      section: state.section,
    });
    expect(comparable(restored)).toEqual(comparable(lived));
    expect(restored.nextStep).toEqual({ kind: "section", sectionId: "s3" });
  });
});
