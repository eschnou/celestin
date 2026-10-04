import { describe, expect, it } from "vitest";

import { sessionFromEntries } from "@/components/celestin/use-tutor-session";
import type { BoardCard, StoredEntry } from "@/lib/tutor/types";

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
