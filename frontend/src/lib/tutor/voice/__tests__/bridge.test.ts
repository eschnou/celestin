import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { TutorEvent } from "../../types";
import { bridge, initialBridgeState, sumUsage, usageOf, type BridgeAction } from "../bridge";
import { parseServerEvent, type RealtimeServerEvent } from "../realtime";
import { EMPTY_USAGE } from "../types";

function fixture(name: string): RealtimeServerEvent[] {
  const text = readFileSync(new URL(`./fixtures/${name}.jsonl`, import.meta.url), "utf-8");
  return text
    .split("\n")
    .filter(Boolean)
    .map((line) => parseServerEvent(line))
    .filter((e): e is RealtimeServerEvent => e !== null);
}

function run(name: string): { events: TutorEvent[]; actions: BridgeAction[] } {
  let state = initialBridgeState();
  const events: TutorEvent[] = [];
  const actions: BridgeAction[] = [];
  for (const ev of fixture(name)) {
    const out = bridge(state, ev);
    state = out.state;
    events.push(...out.events);
    actions.push(...out.actions);
  }
  return { events, actions };
}

describe("bridge", () => {
  it("turns a spoken exchange into a text-mode shaped turn", () => {
    const { events, actions } = run("spoken_turn");
    expect(events).toEqual([
      { event: "turn.start", turn_id: "resp_1" },
      { event: "text.delta", block_id: 0, text: "Salut " },
      { event: "text.delta", block_id: 0, text: "à toi." },
      { event: "turn.end", reason: "end", usage: {} },
    ]);
    expect(actions[0]).toEqual({ kind: "learner.spoken", text: "Bonjour Célestin" });
    expect(actions).toContainEqual({ kind: "speaking", on: true });
    expect(actions.at(-1)).toEqual({ kind: "speaking", on: false });
    const usage = actions.find((a) => a.kind === "usage");
    expect(usage).toEqual({
      kind: "usage",
      usage: {
        input_text: 100,
        input_audio: 20,
        cached_text: 80,
        cached_audio: 0,
        output_text: 10,
        output_audio: 30,
      },
    });
  });

  it("keeps a tool round inside one turn and bumps the block id", () => {
    const { events, actions } = run("tool_round");
    expect(events.filter((e) => e.event === "turn.start")).toHaveLength(1);
    expect(events.filter((e) => e.event === "turn.end")).toHaveLength(1);
    expect(events.filter((e) => e.event === "text.delta")).toEqual([
      { event: "text.delta", block_id: 0, text: "Je l'écris au tableau." },
      { event: "text.delta", block_id: 1, text: "Voilà." },
    ]);
    const calls = actions.filter((a) => a.kind === "tool.call");
    expect(calls).toEqual([
      {
        kind: "tool.call",
        call: { callId: "call_1", name: "display_board", arguments: '{"card":{"kind":"title"}}' },
      },
    ]);
    // The call is emitted at response.done, after the text of that round.
    expect(actions.findIndex((a) => a.kind === "tool.call")).toBeGreaterThan(-1);
  });

  it("emits two calls from one response in order, no turn.end", () => {
    const { events, actions } = run("two_tools_one_response");
    expect(events).toEqual([{ event: "turn.start", turn_id: "resp_1" }]);
    expect(
      actions
        .filter((a) => a.kind === "tool.call")
        .map((a) => a.kind === "tool.call" && a.call.name),
    ).toEqual(["start_section", "display_board"]);
  });

  it("marks a barge-in as interrupted and ends the turn as cancelled", () => {
    const { events, actions } = run("cancelled");
    expect(actions).toContainEqual({ kind: "interrupted" });
    expect(events.at(-1)).toEqual({ event: "turn.end", reason: "cancelled", usage: {} });
  });

  it("interrupts playback that outlives its response", () => {
    const { actions } = run("late_interruption");
    expect(actions).toContainEqual({ kind: "interrupted" });
  });

  it("does not report an interruption when nothing is playing", () => {
    const out = bridge(initialBridgeState(), {
      type: "input_audio_buffer.speech_started",
      item_id: "u",
    });
    expect(out.actions).toEqual([]);
  });

  it("surfaces a failed response as an error entry then ends the turn", () => {
    const { events } = run("failed");
    expect(events.map((e) => e.event)).toEqual(["turn.start", "error", "turn.end"]);
  });

  it("ignores empty transcripts", () => {
    const out = bridge(initialBridgeState(), {
      type: "conversation.item.input_audio_transcription.completed",
      item_id: "u",
      transcript: "   ",
    });
    expect(out.actions).toEqual([]);
  });

  it("maps a realtime error to an action, not an event, and swallows racing codes", () => {
    const out = bridge(initialBridgeState(), {
      type: "error",
      error: { code: "server_error", message: "boom" },
    });
    expect(out.events).toEqual([]);
    expect(out.actions).toEqual([{ kind: "error", code: "server_error", message: "boom" }]);
    const benign = bridge(initialBridgeState(), {
      type: "error",
      error: { code: "conversation_already_has_active_response", message: "…" },
    });
    expect(benign.actions).toEqual([]);
  });
});

describe("usage", () => {
  it("counts missing fields as zero", () => {
    expect(usageOf({})).toEqual(EMPTY_USAGE);
  });

  it("sums per modality", () => {
    const a = { ...EMPTY_USAGE, input_audio: 5, output_audio: 7 };
    const b = { ...EMPTY_USAGE, input_audio: 1, cached_text: 2 };
    expect(sumUsage(a, b)).toEqual({
      ...EMPTY_USAGE,
      input_audio: 6,
      output_audio: 7,
      cached_text: 2,
    });
  });
});

describe("bridge on a recorded session", () => {
  it("replays a real tool round: one turn, one call, two spoken blocks", () => {
    const { events, actions } = run("recorded_tool_round");
    expect(events.filter((e) => e.event === "turn.start")).toHaveLength(1);
    expect(events.filter((e) => e.event === "turn.end")).toEqual([
      { event: "turn.end", reason: "end", usage: {} },
    ]);
    const calls = actions.filter((a) => a.kind === "tool.call");
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({ call: { name: "display_board" } });
    const blocks = new Set(
      events
        .filter((e) => e.event === "text.delta")
        .map((e) => e.event === "text.delta" && e.block_id),
    );
    expect([...blocks]).toEqual([0, 1]);
    const text = events
      .filter((e) => e.event === "text.delta")
      .map((e) => (e.event === "text.delta" ? e.text : ""))
      .join("");
    expect(text).toContain("tableau");
    expect(actions.filter((a) => a.kind === "usage")).toHaveLength(2);
  });
});
