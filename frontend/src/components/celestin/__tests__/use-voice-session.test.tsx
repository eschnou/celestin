// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RealtimeClientEvent, RealtimeServerEvent } from "@/lib/tutor/voice/realtime";

vi.mock("@/lib/tutor/discussion", () => ({ recordVoiceTurn: vi.fn(async () => {}) }));
import { recordVoiceTurn } from "@/lib/tutor/discussion";
import type { CloseReason } from "@/lib/tutor/voice/session";
import type { ToolResult, VoiceSessionInfo } from "@/lib/tutor/voice/types";
import {
  EMPTY_PROGRESS,
  type HistoryEntry,
  type LessonScope,
  type Progress,
} from "@/lib/tutor/types";

const SCOPE = { courseId: "maths-5e", chapterId: "suites" };
import { VoiceRequestError } from "@/lib/tutor/voice/client";
import { VoiceSessionError } from "@/lib/tutor/voice/session";
import type { SessionEvent, TutorSessionHandle } from "../use-tutor-session";
import {
  CAP_GRACE_MS,
  PROBE_MS,
  useVoiceSession,
  type BusChannel,
  type BusMessage,
  type CallHandle,
  type VoiceDeps,
} from "../use-voice-session";

class FakeCall implements CallHandle {
  sent: RealtimeClientEvent[] = [];
  open = false;
  muted: boolean | null = null;
  closed = 0;
  connectError: Error | null = null;
  constructor(
    readonly onEvent: (e: RealtimeServerEvent) => void,
    readonly onClose: (reason: CloseReason) => void,
  ) {}
  mic: MediaStream | null = null;
  connected: { secret: string; callsUrl: string }[] = [];

  async connect(secret: string, mic: MediaStream, callsUrl: string) {
    this.connected.push({ secret, callsUrl });
    if (this.connectError) throw this.connectError;
    this.mic = mic;
    this.open = true;
  }
  send(event: RealtimeClientEvent) {
    if (!this.open) throw new Error("closed");
    this.sent.push(event);
  }
  setMuted(muted: boolean) {
    this.muted = muted;
  }
  close() {
    this.closed += 1;
    this.open = false;
    this.onClose("local");
  }
  drop() {
    this.open = false;
    this.onClose("remote");
  }
}

class FakeBus implements BusChannel {
  static peers: FakeBus[] = [];
  onmessage: ((e: { data: BusMessage }) => void) | null = null;
  closed = false;
  constructor() {
    FakeBus.peers.push(this);
  }
  postMessage(msg: BusMessage) {
    for (const peer of FakeBus.peers)
      if (peer !== this && !peer.closed) peer.onmessage?.({ data: msg });
  }
  close() {
    this.closed = true;
  }
}

const INFO: VoiceSessionInfo = {
  sessionId: "s1",
  secret: "ek_1",
  callsUrl: "https://rt.example/v1/realtime/calls",
  expiresAt: 1,
  model: "m",
  voice: "marin",
  limits: { maxSessionS: 60, idleS: 20 },
  seed: [{ type: "message", role: "system" }],
  opening: true,
};

function harness(
  overrides: Partial<{
    info: VoiceSessionInfo;
    micFails: boolean;
    supported: boolean;
    connectError: Error;
    scope: LessonScope;
  }> = {},
) {
  const dispatched: SessionEvent[] = [];
  const learner: { text: string; spoken: boolean | undefined }[] = [];
  let progress: Progress = EMPTY_PROGRESS;
  const history: HistoryEntry[] = [{ kind: "learner", text: "salut" }];
  let interrupted = 0;
  const tutor: TutorSessionHandle = {
    dispatch: (e) => {
      dispatched.push(e);
      if (e.event === "section.start") progress = { ...progress, active: e.section_id };
    },
    appendLearner: (text, spoken) => learner.push({ text, spoken }),
    markInterrupted: () => (interrupted += 1),
    snapshot: () => ({ history, progress }),
  };
  let call: FakeCall | null = null;
  let now = 1_000_000;
  const toolResults: ToolResult[] = [];
  const api = {
    createVoiceSession: vi.fn(async () => overrides.info ?? INFO),
    executeTool: vi.fn(async () => {
      const next = toolResults.shift();
      if (!next) throw new Error("no scripted tool result");
      if (next instanceof Error) throw next;
      return next;
    }),
    reportUsage: vi.fn(),
  };
  const deps: VoiceDeps = {
    supported: overrides.supported ?? true,
    getMic: overrides.micFails
      ? () => Promise.reject(new Error("NotAllowedError"))
      : () => Promise.resolve({ getTracks: () => [] } as unknown as MediaStream),
    createCall: (onEvent, onClose) => {
      call = new FakeCall(onEvent, onClose);
      call.connectError = overrides.connectError ?? null;
      return call;
    },
    api,
    bus: () => new FakeBus(),
    now: () => now,
  };
  const hook = renderHook(() =>
    useVoiceSession(tutor, { enabled: true, scope: overrides.scope ?? SCOPE, deps }),
  );
  const start = async () => {
    await act(async () => {
      const p = hook.result.current.start();
      await vi.advanceTimersByTimeAsync(PROBE_MS + 1);
      await p;
    });
  };
  const emit = (events: RealtimeServerEvent[]) => {
    act(() => {
      for (const e of events) call!.onEvent(e);
    });
  };
  const flush = async () => {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
  };
  return {
    hook,
    start,
    emit,
    flush,
    api,
    history,
    toolResults,
    dispatched,
    learner,
    get call() {
      return call!;
    },
    get interrupted() {
      return interrupted;
    },
    advance: (ms: number) => {
      now += ms;
      return act(async () => {
        await vi.advanceTimersByTimeAsync(ms);
      });
    },
  };
}

const FC = (name: string, args: string, callId = "c1"): RealtimeServerEvent => ({
  type: "response.output_item.done",
  item: { id: "i", type: "function_call", name, call_id: callId, arguments: args },
});

beforeEach(() => {
  vi.useFakeTimers();
  FakeBus.peers = [];
});
afterEach(() => {
  vi.useRealTimers();
});

describe("useVoiceSession", () => {
  it("starts: mic, session, connect, voice.on, seed, opening response", async () => {
    const h = harness();
    await h.start();
    expect(h.hook.result.current.phase).toBe("listening");
    expect(h.api.createVoiceSession).toHaveBeenCalledWith(SCOPE, [
      { kind: "learner", text: "salut" },
    ]);
    expect(h.dispatched).toEqual([{ event: "voice.on" }]);
    expect(h.call.sent).toEqual([
      { type: "conversation.item.create", item: { type: "message", role: "system" } },
      { type: "response.create" },
    ]);
    expect(h.hook.result.current.capAt).toBe(1_000_000 + 60_000);
    expect(h.call.mic).not.toBeNull();
    // The call goes to the voice server the backend named, not to a place the browser knows.
    expect(h.call.connected).toEqual([
      { secret: "ek_1", callsUrl: "https://rt.example/v1/realtime/calls" },
    ]);
  });

  it("does not request the opening response when continuing a transcript", async () => {
    const h = harness({ info: { ...INFO, opening: false } });
    await h.start();
    expect(h.call.sent).toEqual([
      { type: "conversation.item.create", item: { type: "message", role: "system" } },
    ]);
  });

  it("relays bridged events and spoken learner text", async () => {
    const h = harness();
    await h.start();
    h.emit([
      {
        type: "conversation.item.input_audio_transcription.completed",
        item_id: "u",
        transcript: "Bonjour",
      },
      { type: "response.created", response: { id: "r1" } },
      { type: "output_audio_buffer.started" },
      { type: "response.output_audio_transcript.delta", item_id: "m", delta: "Salut" },
    ]);
    expect(h.learner).toEqual([{ text: "Bonjour", spoken: true }]);
    expect(h.dispatched.slice(1)).toEqual([
      { event: "turn.start", turn_id: "r1" },
      { event: "text.delta", block_id: 0, text: "Salut" },
    ]);
    expect(h.hook.result.current.phase).toBe("speaking");
    h.emit([{ type: "output_audio_buffer.stopped" }]);
    expect(h.hook.result.current.phase).toBe("listening");
  });

  it("runs a tool round: /tool, dispatch, state item, output, response.create", async () => {
    const h = harness();
    await h.start();
    h.call.sent.length = 0;
    h.toolResults.push({
      output: '{"ok":true}',
      event: { event: "section.start", section_id: "suites", review: false, marker: "m" },
      progress: { done: [], active: "suites" },
      stateText: "État",
    });
    h.emit([
      { type: "response.created", response: { id: "r1" } },
      FC("start_section", '{"section_id":"suites"}'),
      { type: "response.done", response: { id: "r1", status: "completed" } },
    ]);
    expect(h.hook.result.current.phase).toBe("working");
    await h.flush();
    expect(h.api.executeTool).toHaveBeenCalledWith(
      "s1",
      { callId: "c1", name: "start_section", arguments: '{"section_id":"suites"}' },
      SCOPE,
    );
    expect(h.dispatched.slice(1)).toEqual([
      { event: "turn.start", turn_id: "r1" },
      { event: "section.start", section_id: "suites", review: false, marker: "m" },
    ]);
    expect(h.call.sent).toEqual([
      {
        type: "conversation.item.create",
        item: { type: "message", role: "system", content: [{ type: "input_text", text: "État" }] },
      },
      {
        type: "conversation.item.create",
        item: { type: "function_call_output", call_id: "c1", output: '{"ok":true}' },
      },
      { type: "response.create" },
    ]);
    expect(h.hook.result.current.phase).toBe("listening");
  });

  it("executes two calls of one response serially, in scope", async () => {
    const h = harness();
    await h.start();
    h.toolResults.push(
      {
        output: "{}",
        event: { event: "section.start", section_id: "suites", review: false, marker: "m" },
        progress: { done: [], active: "suites" },
      },
      { output: "{}", event: null, progress: { done: [], active: "suites" } },
    );
    h.emit([
      { type: "response.created", response: { id: "r1" } },
      FC("start_section", "{}", "c1"),
      FC("display_board", "{}", "c2"),
      { type: "response.done", response: { id: "r1", status: "completed" } },
    ]);
    await h.flush();
    const calls = h.api.executeTool.mock.calls as unknown as [
      string,
      { callId: string },
      Progress,
    ][];
    expect(calls.map((c) => c[1].callId)).toEqual(["c1", "c2"]);
    expect(calls[1]![2]).toEqual(SCOPE);
    expect(h.call.sent.filter((e) => e.type === "response.create")).toHaveLength(2); // opening + after batch
  });

  it("sendText appends an unspoken entry and asks for a response", async () => {
    const h = harness();
    await h.start();
    h.call.sent.length = 0;
    act(() => h.hook.result.current.sendText("  Étape suivante. "));
    expect(h.learner).toEqual([{ text: "Étape suivante.", spoken: undefined }]);
    expect(h.call.sent).toEqual([
      {
        type: "conversation.item.create",
        item: {
          type: "message",
          role: "user",
          content: [{ type: "input_text", text: "Étape suivante." }],
        },
      },
      { type: "response.create" },
    ]);
  });

  it("cancels the current response before typed text mid-turn", async () => {
    const h = harness();
    await h.start();
    h.emit([{ type: "response.created", response: { id: "r1" } }]);
    h.call.sent.length = 0;
    act(() => h.hook.result.current.sendText("stop"));
    expect(h.call.sent[0]).toEqual({ type: "response.cancel" });
  });

  it("stops on request: closes, reports usage, voice.off", async () => {
    const h = harness();
    await h.start();
    h.emit([
      { type: "response.created", response: { id: "r1" } },
      {
        type: "response.done",
        response: {
          id: "r1",
          status: "completed",
          usage: {
            input_token_details: { audio_tokens: 5 },
            output_token_details: { audio_tokens: 7 },
          },
        },
      },
    ]);
    await h.advance(3000);
    act(() => h.hook.result.current.stop());
    expect(h.hook.result.current.phase).toBe("off");
    expect(h.call.closed).toBe(1);
    expect(h.api.reportUsage).toHaveBeenCalledWith(
      {
        session_id: "s1",
        reason: "learner",
        duration_s: 3,
        responses: 1,
        usage: expect.objectContaining({ input_audio: 5, output_audio: 7 }),
      },
      {},
    );
    expect(h.dispatched.at(-1)).toEqual({ event: "voice.off", reason: "learner" });
  });

  const LONG_IDLE = { ...INFO, limits: { maxSessionS: 60, idleS: 1000 } };

  it("the cap waits for the turn to end, then stops", async () => {
    const h = harness({ info: LONG_IDLE });
    await h.start();
    h.emit([{ type: "response.created", response: { id: "r1" } }]);
    await h.advance(60_000);
    expect(h.hook.result.current.phase).not.toBe("off");
    h.emit([{ type: "response.done", response: { id: "r1", status: "completed" } }]);
    expect(h.hook.result.current.phase).toBe("off");
    expect(h.api.reportUsage.mock.calls[0]![0]).toMatchObject({ reason: "cap" });
  });

  it("the cap grace period expires without a turn end", async () => {
    const h = harness({ info: LONG_IDLE });
    await h.start();
    h.emit([{ type: "response.created", response: { id: "r1" } }]);
    await h.advance(60_000 + CAP_GRACE_MS);
    expect(h.hook.result.current.phase).toBe("off");
    expect(h.dispatched.at(-1)).toEqual({ event: "voice.off", reason: "cap" });
  });

  it("idles out, unless she speaks", async () => {
    const h = harness();
    await h.start();
    await h.advance(15_000);
    h.emit([{ type: "input_audio_buffer.speech_started", item_id: "u" }]);
    await h.advance(15_000);
    expect(h.hook.result.current.phase).not.toBe("off");
    await h.advance(6_000);
    expect(h.dispatched.at(-1)).toEqual({ event: "voice.off", reason: "idle" });
  });

  it("a refused mic ends in text mode with the French sentence, no session minted", async () => {
    const h = harness({ micFails: true });
    await h.start();
    expect(h.hook.result.current.phase).toBe("off");
    expect(h.api.createVoiceSession).not.toHaveBeenCalled();
    expect(h.dispatched).toEqual([
      { event: "error", code: "voice_mic", message: expect.stringContaining("micro") },
    ]);
  });

  it("a 429 from /session surfaces the server message", async () => {
    const h = harness();
    h.api.createVoiceSession.mockRejectedValueOnce(
      new VoiceRequestError("voice_rate_limited", "Trop."),
    );
    await h.start();
    expect(h.hook.result.current.phase).toBe("off");
    expect(h.dispatched).toEqual([{ event: "error", code: "voice_connect", message: "Trop." }]);
    expect(h.api.reportUsage).not.toHaveBeenCalled();
  });

  it("a connect failure tears down and reports nothing", async () => {
    const h = harness({ connectError: new VoiceSessionError("timeout", "no channel") });
    await h.start();
    expect(h.hook.result.current.phase).toBe("off");
    expect(h.dispatched).toEqual([
      {
        event: "error",
        code: "voice_connect",
        message: expect.stringContaining("connexion vocale"),
      },
    ]);
    expect(h.call.closed).toBe(1);
    expect(h.api.reportUsage).not.toHaveBeenCalled();
  });

  it("a dropped channel ends the session as an error", async () => {
    const h = harness();
    await h.start();
    act(() => h.call.drop());
    expect(h.hook.result.current.phase).toBe("off");
    expect(h.dispatched.at(-1)).toEqual({ event: "voice.off", reason: "error" });
    expect(h.api.reportUsage.mock.calls[0]![0]).toMatchObject({ reason: "error" });
  });

  it("a failed /tool answers the model with ok:false and shows one entry", async () => {
    const h = harness();
    await h.start();
    h.call.sent.length = 0;
    h.toolResults.push(new Error("500") as unknown as ToolResult);
    h.emit([
      { type: "response.created", response: { id: "r1" } },
      FC("display_board", "{}"),
      { type: "response.done", response: { id: "r1", status: "completed" } },
    ]);
    await h.flush();
    const output = h.call.sent[0] as unknown as { item: { output: string } };
    expect(JSON.parse(output.item.output)).toMatchObject({ ok: false });
    expect(h.call.sent[1]).toEqual({ type: "response.create" });
    expect(h.dispatched.at(-1)).toMatchObject({
      event: "error",
      message: expect.stringContaining("tableau"),
    });
  });

  it("a tool whose result arrives after the drop applies locally but sends nothing", async () => {
    const h = harness();
    await h.start();
    let resolve!: (r: ToolResult) => void;
    h.api.executeTool.mockImplementationOnce(() => new Promise<ToolResult>((r) => (resolve = r)));
    h.emit([
      { type: "response.created", response: { id: "r1" } },
      FC("display_board", "{}"),
      { type: "response.done", response: { id: "r1", status: "completed" } },
    ]);
    await h.flush();
    const sentBefore = h.call.sent.length;
    act(() => h.call.drop());
    await act(async () => {
      resolve({
        output: "{}",
        event: { event: "board.clear", marker: "x" },
        progress: EMPTY_PROGRESS,
      });
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(h.call.sent).toHaveLength(sentBefore);
    expect(h.dispatched.filter((e) => e.event === "board.clear")).toHaveLength(1);
  });

  it("benign realtime errors are silent, others show one entry", async () => {
    const h = harness();
    await h.start();
    h.emit([
      {
        type: "error",
        error: {
          code: "conversation_already_has_active_response",
          message: "Conversation already has an active response",
        },
      },
    ]);
    expect(h.dispatched.filter((e) => e.event === "error")).toHaveLength(0);
    vi.spyOn(console, "warn").mockImplementation(() => {});
    h.emit([{ type: "error", error: { code: "server_error", message: "server exploded" } }]);
    expect(h.dispatched.filter((e) => e.event === "error")).toHaveLength(1);
  });

  it("refuses to start while another tab holds a session", async () => {
    const other = new FakeBus();
    other.onmessage = (e) => {
      if (e.data.type === "probe") other.postMessage({ type: "busy" });
    };
    const h = harness();
    await h.start();
    expect(h.hook.result.current.phase).toBe("off");
    expect(h.dispatched).toEqual([
      { event: "error", code: "voice_busy", message: expect.stringContaining("onglet") },
    ]);
    expect(h.api.createVoiceSession).not.toHaveBeenCalled();
  });

  it("mute toggles the call's track", async () => {
    const h = harness();
    await h.start();
    act(() => h.hook.result.current.toggleMute());
    expect(h.hook.result.current.muted).toBe(true);
    expect(h.call.muted).toBe(true);
    act(() => h.hook.result.current.toggleMute());
    expect(h.call.muted).toBe(false);
  });

  it("unmount stops with a beacon", async () => {
    const h = harness();
    await h.start();
    h.hook.unmount();
    expect(h.api.reportUsage.mock.calls[0]![1]).toEqual({ beacon: true });
    expect(h.dispatched.at(-1)).toEqual({ event: "voice.off", reason: "unload" });
  });

  it("is inert when unsupported", async () => {
    const h = harness({ supported: false });
    expect(h.hook.result.current.supported).toBe(false);
    await h.start();
    expect(h.hook.result.current.phase).toBe("off");
    expect(h.api.createVoiceSession).not.toHaveBeenCalled();
  });
});

describe("useVoiceSession on page unload", () => {
  it("pagehide stops with a beacon", async () => {
    const h = harness();
    await h.start();
    act(() => {
      window.dispatchEvent(new Event("pagehide"));
    });
    expect(h.hook.result.current.phase).toBe("off");
    expect(h.api.reportUsage.mock.calls[0]![1]).toEqual({ beacon: true });
    expect(h.dispatched.at(-1)).toEqual({ event: "voice.off", reason: "unload" });
  });
});

// --- discussion mode (007 deviation D1) --------------------------------------

describe("a spoken turn in a discussion", () => {
  const DISCUSSION = { ...SCOPE, mode: "discussion" as const, conversationId: "conv1" };

  it("reports what the call said, never the transcript it started from", async () => {
    // The harness seeds one entry, standing in for a restored conversation the
    // server has already stored. Re-reporting it would append the whole thread a
    // second time and count twice against the cap.
    const s = harness({ scope: DISCUSSION });
    await s.start();
    s.history.push({ kind: "learner", text: "et les suites géométriques ?" });
    s.history.push({ kind: "tutor", text: "Une suite est une liste ordonnée." });
    s.emit([{ type: "response.done", response: { status: "completed" } } as never]);
    await s.flush();

    expect(recordVoiceTurn).toHaveBeenCalledTimes(1);
    const [scope, entries] = vi.mocked(recordVoiceTurn).mock.calls[0]!;
    expect(scope.conversationId).toBe("conv1");
    expect(entries).toEqual([
      { kind: "learner", text: "et les suites géométriques ?" },
      { kind: "tutor", text: "Une suite est une liste ordonnée." },
    ]);
    expect(entries).not.toContainEqual({ kind: "learner", text: "salut" });
  });

  it("reports nothing when the call added nothing", async () => {
    const s = harness({ scope: DISCUSSION });
    await s.start();
    s.emit([{ type: "response.done", response: { status: "completed" } } as never]);
    await s.flush();
    expect(vi.mocked(recordVoiceTurn).mock.calls[0]![1]).toEqual([]);
  });

  it("reports only what is new on the next turn", async () => {
    const s = harness({ scope: DISCUSSION });
    await s.start();
    s.emit([{ type: "response.done", response: { status: "completed" } } as never]);
    await s.flush();
    s.history.push({ kind: "tutor", text: "Et ensuite ?" });
    s.emit([{ type: "response.done", response: { status: "completed" } } as never]);
    await s.flush();

    expect(vi.mocked(recordVoiceTurn).mock.calls[1]![1]).toEqual([
      { kind: "tutor", text: "Et ensuite ?" },
    ]);
  });

  it("reports nothing in the parcours, where the browser owns the transcript", async () => {
    const s = harness();
    await s.start();
    s.emit([{ type: "response.done", response: { status: "completed" } } as never]);
    await s.flush();
    expect(recordVoiceTurn).not.toHaveBeenCalled();
  });
});
