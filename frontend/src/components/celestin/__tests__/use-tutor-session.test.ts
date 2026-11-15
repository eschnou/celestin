import { describe, expect, it } from "vitest";
import {
  EMPTY_SESSION,
  appendLearner,
  markInterrupted,
  reduce,
  type SessionEvent,
  type SessionState,
} from "../use-tutor-session";
import type { BoardCard, TutorEvent } from "@/lib/tutor/types";

const CARD: BoardCard = {
  kind: "exercise",
  title: "Le manuel",
  statement: "Combien ?",
  hint: null,
};

function play(events: SessionEvent[], from: SessionState = EMPTY_SESSION): SessionState {
  return events.reduce(reduce, from);
}

describe("session reducer", () => {
  it("assembles a golden transcript in order", () => {
    const state = play([
      { event: "turn.start", turn_id: "t" },
      { event: "text.delta", block_id: 0, text: "Salut " },
      { event: "text.delta", block_id: 0, text: "!" },
      { event: "board.set", card: CARD, marker: "exercice posé" },
      { event: "text.delta", block_id: 1, text: "À toi." },
      { event: "turn.end", reason: "end", usage: {} },
    ]);

    expect(state.entries.map((e) => [e.role, e.text])).toEqual([
      ["tutor", "Salut !"],
      ["marker", "exercice posé"],
      ["tutor", "À toi."],
    ]);
    expect(state.board).toEqual(CARD);
    expect(state.boards).toHaveLength(1);
  });

  it("keeps markers positioned between the text blocks they interrupt", () => {
    const state = play([
      { event: "text.delta", block_id: 0, text: "avant" },
      { event: "board.clear", marker: "tableau effacé" },
      { event: "text.delta", block_id: 1, text: "après" },
    ]);
    expect(state.entries.map((e) => e.role)).toEqual(["tutor", "marker", "tutor"]);
  });

  it("builds the history the model gets back, tool calls included", () => {
    let state = appendLearner(EMPTY_SESSION, "salut");
    state = play(
      [
        { event: "text.delta", block_id: 0, text: "Bonjour" },
        { event: "board.set", card: CARD, marker: "exercice posé" },
        { event: "text.delta", block_id: 1, text: "Vas-y" },
      ],
      state,
    );
    expect(state.history).toEqual([
      { kind: "learner", text: "salut" },
      { kind: "tutor", text: "Bonjour" },
      { kind: "tool", name: "display_board", arguments: { card: CARD }, ok: true },
      { kind: "tutor", text: "Vas-y" },
    ]);
  });

  it("clears the board but keeps the strip", () => {
    let state = play([{ event: "board.set", card: CARD, marker: "exercice posé" }]);
    state = play([{ event: "board.clear", marker: "tableau effacé" }], state);
    expect(state.board).toBeNull();
    expect(state.boards).toHaveLength(1);
  });

  it("points each marker at its board", () => {
    const other: BoardCard = { kind: "recap", acquired: ["a"], watch: [], next: "b" };
    const state = play([
      { event: "board.set", card: CARD, marker: "exercice posé" },
      { event: "board.clear", marker: "tableau effacé" },
      { event: "board.set", card: other, marker: "bilan affiché" },
    ]);
    const markers = state.entries.filter((e) => e.role === "marker");
    expect(markers.map((m) => (m as { boardIndex: number | null }).boardIndex)).toEqual([
      0,
      null,
      1,
    ]);
  });

  it("surfaces an error entry without discarding what was already streamed", () => {
    const state = play([
      { event: "text.delta", block_id: 0, text: "début" },
      { event: "error", code: "provider_unavailable", message: "Célestin est injoignable." },
    ]);
    expect(state.entries.map((e) => e.role)).toEqual(["tutor", "error"]);
    expect(state.entries[0]).toMatchObject({ text: "début" });
  });

  it("adds a French notice when the round limit is hit", () => {
    const state = play([{ event: "turn.end", reason: "max_rounds", usage: {} }]);
    expect(state.entries).toHaveLength(1);
    expect(state.entries[0]!.text).toContain("emballé");
  });

  it("adds nothing on a normal turn end", () => {
    expect(play([{ event: "turn.end", reason: "end", usage: {} }]).entries).toEqual([]);
  });

  it("marks the last tutor entry interrupted on cancel", () => {
    const state = markInterrupted(
      play([
        { event: "text.delta", block_id: 0, text: "je commen" },
        { event: "board.clear", marker: "tableau effacé" },
      ]),
    );
    expect(state.entries[0]).toMatchObject({ interrupted: true, text: "je commen" });
  });

  it("resets block tracking between turns so ids can repeat", () => {
    let state = play([
      { event: "turn.start", turn_id: "t1" },
      { event: "text.delta", block_id: 0, text: "premier" },
      { event: "turn.end", reason: "end", usage: {} },
    ]);
    state = play(
      [
        { event: "turn.start", turn_id: "t2" },
        { event: "text.delta", block_id: 0, text: "second" },
      ],
      state,
    );
    expect(state.entries.map((e) => e.text)).toEqual(["premier", "second"]);
  });

  it("moves the path on section events and records the tool calls (002)", () => {
    let state = play([
      {
        event: "section.start",
        section_id: "suites",
        review: false,
        marker: "section commencée · 1. Suites",
      },
    ]);
    expect(state.progress).toEqual({ done: [], active: "suites", skipped: [] });
    expect(state.entries).toMatchObject([
      { role: "marker", text: "section commencée · 1. Suites", boardIndex: null },
    ]);

    state = play(
      [
        {
          event: "section.done",
          section_id: "suites",
          next_section_id: "sa",
          marker: "section terminée · 1. Suites",
        },
      ],
      state,
    );
    expect(state.progress).toEqual({ done: ["suites"], active: null, skipped: [] });
    expect(state.history).toEqual([
      // `review` travels with the stored séance (018); the model never reads it.
      {
        kind: "tool",
        name: "start_section",
        arguments: { section_id: "suites" },
        ok: true,
        review: false,
      },
      {
        kind: "tool",
        name: "complete_section",
        arguments: { section_id: "suites" },
        ok: true,
        next_section_id: "sa",
      },
    ]);
  });

  it("starts every section on a fresh board", () => {
    let state = play([
      { event: "board.set", card: CARD, marker: "exercice posé" },
      { event: "section.done", section_id: "suites", next_section_id: "sa", marker: "fin" },
    ]);
    expect(state.boards).toHaveLength(1);
    state = play(
      [
        {
          event: "section.start",
          section_id: "suites",
          review: true,
          marker: "révision · 1. Suites",
        },
      ],
      state,
    );
    expect(state.board).toBeNull();
    expect(state.boards).toEqual([]);
    const markers = state.entries.filter((e) => e.role === "marker");
    expect(markers.every((m) => (m as { boardIndex: number | null }).boardIndex === null)).toBe(
      true,
    );
  });

  it("leaves the path untouched on a review", () => {
    const from: SessionState = {
      ...EMPTY_SESSION,
      progress: { done: ["suites"], active: "sa", skipped: [] },
    };
    const state = play(
      [
        {
          event: "section.start",
          section_id: "suites",
          review: true,
          marker: "révision · 1. Suites",
        },
      ],
      from,
    );
    expect(state.progress).toEqual({ done: ["suites"], active: "sa", skipped: [] });
    expect(state.entries[0]).toMatchObject({ role: "marker", text: "révision · 1. Suites" });
  });

  it("does not list a section twice in done", () => {
    const from: SessionState = {
      ...EMPTY_SESSION,
      progress: { done: ["suites"], active: "suites", skipped: [] },
    };
    const state = play(
      [{ event: "section.done", section_id: "suites", next_section_id: null, marker: "m" }],
      from,
    );
    expect(state.progress.done).toEqual(["suites"]);
  });

  it("lights the next-step button on step.ready and greys it on the next card or turn", () => {
    let state = play([
      { event: "board.set", card: CARD, marker: "exercice posé" },
      { event: "step.ready", marker: "étape suivante proposée" },
    ]);
    expect(state.nextStep).toEqual({ kind: "step" });
    expect(state.entries.at(-1)).toMatchObject({ role: "marker", text: "étape suivante proposée" });
    expect(state.history.at(-1)).toEqual({
      kind: "tool",
      name: "propose_next_step",
      arguments: {},
      ok: true,
    });
    state = play([{ event: "board.set", card: CARD, marker: "exercice posé" }], state);
    expect(state.nextStep).toBeNull();
    state = play(
      [
        { event: "step.ready", marker: "m" },
        { event: "turn.start", turn_id: "t" },
      ],
      state,
    );
    expect(state.nextStep).toBeNull();
  });

  it("lights the next-step button on a title card, with no step.ready needed", () => {
    const title: BoardCard = {
      kind: "title",
      eyebrow: "Leçon 1",
      title: "Statistique, population et variable",
      objective: "Savoir ce qu'est une population.",
    };
    let state = play([
      { event: "section.start", section_id: "sa", review: false, marker: "section commencée" },
      { event: "board.set", card: title, marker: "séance ouverte" },
      { event: "turn.end", reason: "end", usage: {} },
    ]);
    expect(state.nextStep).toEqual({ kind: "step" });
    // The next card greys it again, as any card does.
    state = play([{ event: "board.set", card: CARD, marker: "exercice posé" }], state);
    expect(state.nextStep).toBeNull();
  });

  it("offers the next section after a close, through its recap, until the next section starts", () => {
    let state = play([
      {
        event: "section.done",
        section_id: "suites",
        next_section_id: "sa",
        marker: "section terminée",
      },
      { event: "board.set", card: CARD, marker: "bilan affiché" },
    ]);
    expect(state.nextStep).toEqual({ kind: "section", sectionId: "sa" });
    state = play(
      [{ event: "section.start", section_id: "sa", review: false, marker: "section commencée" }],
      state,
    );
    expect(state.nextStep).toBeNull();
  });

  it("offers nothing after the last section closes", () => {
    const state = play([
      { event: "section.done", section_id: "test-blanc", next_section_id: null, marker: "m" },
    ]);
    expect(state.nextStep).toBeNull();
  });

  it("skips the active section: cleared, the page turns to the next one (spec 019)", () => {
    const state = play([
      { event: "section.start", section_id: "sa", review: false, marker: "ouverte" },
      {
        event: "section.skipped",
        section_id: "sa",
        next_section_id: "sb",
        active_section_id: null,
        marker: "passée · 1",
      },
    ]);
    expect(state.progress).toEqual({ done: [], active: null, skipped: ["sa"] });
    expect(state.nextStep).toEqual({ kind: "section", sectionId: "sb" });
    expect(state.entries.at(-1)).toMatchObject({ role: "marker", text: "passée · 1" });
    // What the call answered travels with the stored séance (spec 019); the model never reads it.
    expect(state.history.at(-1)).toEqual({
      kind: "tool",
      name: "skip_section",
      arguments: { section_id: "sa" },
      ok: true,
      next_section_id: "sb",
      active_section_id: null,
    });
  });

  it("clears the page-turn button when a skip finishes the chapter (spec 019)", () => {
    // complete(X) lights the button for Y; skipping Y, the last open section, ends the
    // chapter: nothing is active and nothing is proposed, so nothing is offered.
    const state = play([
      { event: "section.start", section_id: "sa", review: false, marker: "m" },
      { event: "section.done", section_id: "sa", next_section_id: "sb", marker: "m" },
      {
        event: "section.skipped",
        section_id: "sb",
        next_section_id: null,
        active_section_id: null,
        marker: "m",
      },
    ]);
    expect(state.nextStep).toBeNull();
    expect(state.history.at(-1)).toMatchObject({ next_section_id: null, active_section_id: null });
  });

  it("records the non-review sections started, once each, in order", () => {
    const state = play([
      { event: "section.start", section_id: "sb", review: false, marker: "m" },
      { event: "section.start", section_id: "sa", review: true, marker: "m" },
      { event: "section.start", section_id: "sc", review: false, marker: "m" },
      { event: "section.start", section_id: "sb", review: false, marker: "m" },
    ]);
    expect(state.started).toEqual(["sb", "sc"]);
  });

  it("skips another section without touching the active one or the page", () => {
    const state = play([
      { event: "section.start", section_id: "sa", review: false, marker: "ouverte" },
      { event: "step.ready", marker: "étape" },
      {
        event: "section.skipped",
        section_id: "sc",
        next_section_id: null,
        active_section_id: "sa",
        marker: "passée",
      },
    ]);
    expect(state.progress).toEqual({ done: [], active: "sa", skipped: ["sc"] });
    expect(state.nextStep).toEqual({ kind: "step" });
    expect(state.section).toBe("sa");
  });

  it("does not list a section twice in skipped", () => {
    const skip = {
      event: "section.skipped",
      section_id: "sb",
      next_section_id: null,
      active_section_id: null,
      marker: "m",
    } as const;
    expect(play([skip, skip]).progress.skipped).toEqual(["sb"]);
  });

  it("un-skips a section when it starts, and not on a review", () => {
    const from = play([
      {
        event: "section.skipped",
        section_id: "sb",
        next_section_id: "sc",
        active_section_id: null,
        marker: "m",
      },
    ]);
    const started = play(
      [{ event: "section.start", section_id: "sb", review: false, marker: "m" }],
      from,
    );
    expect(started.progress).toEqual({ done: [], active: "sb", skipped: [] });
    const reviewed = play(
      [{ event: "section.start", section_id: "sb", review: true, marker: "m" }],
      from,
    );
    expect(reviewed.progress).toEqual({ done: [], active: null, skipped: ["sb"] });
  });

  it("keeps skipped sections through a completion", () => {
    const state = play([
      {
        event: "section.skipped",
        section_id: "sa",
        next_section_id: "sb",
        active_section_id: null,
        marker: "m",
      },
      { event: "section.start", section_id: "sb", review: false, marker: "m" },
      { event: "section.done", section_id: "sb", next_section_id: "sc", marker: "m" },
    ]);
    expect(state.progress).toEqual({ done: ["sb"], active: null, skipped: ["sa"] });
  });

  it("appends a learner message to both views", () => {
    const state = appendLearner(EMPTY_SESSION, "ok");
    expect(state.entries).toMatchObject([{ role: "learner", text: "ok" }]);
    expect(state.history).toEqual([{ kind: "learner", text: "ok" }]);
  });
});

describe("voice mode in the reducer (003)", () => {
  it("marks the start and the end of a voice session", () => {
    let state = play([{ event: "voice.on" }]);
    expect(state.voice).toBe(true);
    expect(state.entries.at(-1)).toMatchObject({ role: "marker", text: "séance vocale" });
    state = play([{ event: "voice.off", reason: "cap" }], state);
    expect(state.voice).toBe(false);
    expect(state.entries.at(-1)).toMatchObject({
      role: "marker",
      text: "fin de la séance vocale : temps écoulé",
    });
    expect(play([{ event: "voice.off", reason: "error" }], state).entries.at(-1)).toMatchObject({
      text: "connexion vocale perdue",
    });
  });

  it("flags spoken tutor text while voice is on, and not after", () => {
    let state = play([{ event: "voice.on" }, { event: "text.delta", block_id: 0, text: "Salut" }]);
    expect(state.entries.at(-1)).toMatchObject({ role: "tutor", text: "Salut", spoken: true });
    state = play(
      [
        { event: "voice.off", reason: "learner" },
        { event: "text.delta", block_id: 1, text: "Écrit" },
      ],
      state,
    );
    expect(state.entries.at(-1)).toMatchObject({ role: "tutor", text: "Écrit" });
    expect("spoken" in state.entries.at(-1)!).toBe(false);
  });

  it("flags a spoken learner entry, keeping the history shape unchanged", () => {
    const state = appendLearner(EMPTY_SESSION, "Bonjour", true);
    expect(state.entries[0]).toMatchObject({ role: "learner", text: "Bonjour", spoken: true });
    expect(state.history).toEqual([{ kind: "learner", text: "Bonjour" }]);
  });
});
