/** The révision's one new event (spec 020): `revision.result` in the reducer, live and
 *  replayed from a stored `record_result` entry. */
import { describe, expect, it } from "vitest";

import {
  appendLearner,
  EMPTY_SESSION,
  reduce,
  sessionFromEntries,
  type SessionEvent,
  type SessionState,
} from "@/components/celestin/use-tutor-session";
import type { BoardCard, StoredEntry } from "@/lib/tutor/types";

const RESULT: SessionEvent = {
  event: "revision.result",
  chapter_id: "h2",
  section_id: "s3",
  outcome: "shaky",
  marker: "noté : fragile · 3. Le terme général",
};

describe("revision.result", () => {
  it("marks the transcript, keeps the result and records the call", () => {
    const state = reduce(EMPTY_SESSION, RESULT);
    expect(state.entries).toHaveLength(1);
    expect(state.entries[0]).toMatchObject({
      role: "marker",
      text: "noté : fragile · 3. Le terme général",
      boardIndex: null,
    });
    expect(state.results).toEqual([{ chapter_id: "h2", section_id: "s3", outcome: "shaky" }]);
    expect(state.history).toEqual([
      {
        kind: "tool",
        name: "record_result",
        arguments: { chapter_id: "h2", section_id: "s3", outcome: "shaky" },
        ok: true,
      },
    ]);
  });

  it("keeps every result in order, so the last one counts", () => {
    const state = [RESULT, { ...RESULT, outcome: "solid" } as SessionEvent].reduce(
      reduce,
      EMPTY_SESSION,
    );
    expect(state.results.map((r) => r.outcome)).toEqual(["shaky", "solid"]);
  });

  it("leaves the board, the path and the page-turn button alone", () => {
    const state = reduce(EMPTY_SESSION, RESULT);
    expect(state.board).toBeNull();
    expect(state.progress).toEqual(EMPTY_SESSION.progress);
    expect(state.nextStep).toBeNull();
  });
});

describe("a stored révision", () => {
  const CARD: BoardCard = {
    kind: "explanation",
    title: "La définition du cours",
    blocks: [{ type: "text", text: "Une suite est une fonction de ℕ dans ℝ." }],
  };

  it("replays a stored record_result as the live event did", () => {
    const stored: StoredEntry[] = [
      { kind: "tutor", text: "Bonjour ! On révise ?" },
      { kind: "learner", text: "Oui, tout mélangé." },
      { kind: "tutor", text: "Définis une suite." },
      { kind: "learner", text: "Une liste de nombres." },
      {
        kind: "tool",
        name: "display_board",
        arguments: { card: CARD },
        marker: "explication affichée",
      },
      { kind: "learner", text: "Pour moi, c'est fragile." },
      {
        kind: "tool",
        name: "record_result",
        // What the model sent: the chapter by its number.
        arguments: { chapter: 2, section_id: "s3", outcome: "shaky" },
        chapter_id: "h2",
        section_id: "s3",
        outcome: "shaky",
        marker: "noté : fragile · 3. Le terme général",
      },
      { kind: "tutor", text: "Noté. On y reviendra." },
    ];
    type Step = SessionEvent | { learner: string };
    const live: Step[] = [
      { event: "turn.start", turn_id: "t0" },
      { event: "text.delta", block_id: 0, text: "Bonjour ! On révise ?" },
      { event: "turn.end", reason: "end", usage: {} },
      { learner: "Oui, tout mélangé." },
      { event: "turn.start", turn_id: "t1" },
      { event: "text.delta", block_id: 0, text: "Définis une suite." },
      { event: "turn.end", reason: "end", usage: {} },
      { learner: "Une liste de nombres." },
      { event: "turn.start", turn_id: "t2" },
      { event: "board.set", card: CARD, marker: "explication affichée" },
      { event: "turn.end", reason: "end", usage: {} },
      { learner: "Pour moi, c'est fragile." },
      { event: "turn.start", turn_id: "t3" },
      RESULT,
      { event: "text.delta", block_id: 0, text: "Noté. On y reviendra." },
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
    });
    expect(comparable(restored)).toEqual(comparable(lived));
    expect(lived.results).toEqual([{ chapter_id: "h2", section_id: "s3", outcome: "shaky" }]);
    // The stored results are in the server's read: a restored session notes none of its own.
    expect(restored.results).toEqual([]);
  });

  it("skips a record_result entry that does not say what was noted", () => {
    const state = sessionFromEntries([
      { kind: "tool", name: "record_result", arguments: { chapter: 1 }, marker: "noté" },
    ]);
    expect(state.results).toEqual([]);
    expect(state.entries).toEqual([]);
  });
});
