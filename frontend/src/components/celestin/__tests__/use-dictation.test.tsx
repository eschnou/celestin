// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useDictation, type DictationDeps, type TakeHandle } from "../use-dictation";

const ROOM = 0.004;
const VOICE = 0.08;

/** A microphone whose loudness the test sets. */
function fakeDeps(over: Partial<DictationDeps> = {}) {
  const state = { rms: ROOM, begun: 0, finished: 0, cancelled: 0 };
  const take: TakeHandle = {
    level: () => state.rms,
    finish: async () => {
      state.finished += 1;
      return { blob: new Blob(["x"], { type: "audio/webm" }), durationMs: 3000 };
    },
    cancel: () => {
      state.cancelled += 1;
    },
  };
  const deps: DictationDeps = {
    supported: true,
    begin: async () => {
      state.begun += 1;
      return take;
    },
    transcribe: vi.fn(async () => "la somme de deux entiers"),
    now: () => Date.now(),
    tickMs: 50,
    ...over,
  };
  return { deps, state };
}

const advance = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

function mount(deps: DictationDeps, onText = vi.fn(), suspended = false) {
  const hook = renderHook(
    (props: { suspended: boolean }) =>
      useDictation({ language: "fr", onText, suspended: props.suspended, deps }),
    { initialProps: { suspended } },
  );
  return { ...hook, onText };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(1_000_000);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("useDictation", () => {
  it("listens, hears a phrase, stops by itself when she stops talking, and hands over the text", async () => {
    const { deps, state } = fakeDeps();
    const { result, onText } = mount(deps);
    await act(async () => result.current.toggle());
    expect(result.current.phase).toBe("listening");
    await advance(500); // the room
    state.rms = VOICE;
    await advance(2000); // a phrase
    expect(result.current.heard).toBe(true);
    state.rms = ROOM;
    await advance(3000); // a pause longer than the patience
    expect(deps.transcribe).toHaveBeenCalledOnce();
    expect(onText).toHaveBeenCalledWith("la somme de deux entiers");
    expect(result.current.phase).toBe("idle");
    expect(state.finished).toBe(1);
  });

  it("sends the language of the course along with the recording", async () => {
    const { deps, state } = fakeDeps();
    const { result } = mount(deps);
    await act(async () => result.current.toggle());
    await advance(500);
    state.rms = VOICE;
    await advance(1500);
    await act(async () => result.current.toggle()); // a second tap ends the take
    expect(deps.transcribe).toHaveBeenCalledWith(
      expect.objectContaining({ durationMs: 3000 }),
      "fr",
      expect.any(AbortSignal),
    );
  });

  it("gives no language hint to a language course, where the wrong hint is worse than none", async () => {
    const { deps, state } = fakeDeps();
    const hook = renderHook(() => useDictation({ language: null, onText: vi.fn(), deps }));
    await act(async () => hook.result.current.toggle());
    await advance(500);
    state.rms = VOICE;
    await advance(1500);
    await act(async () => hook.result.current.toggle());
    expect(deps.transcribe).toHaveBeenCalledWith(expect.anything(), null, expect.any(AbortSignal));
  });

  it("drops a take in which nothing was said, without calling the server", async () => {
    const { deps, state } = fakeDeps();
    const { result, onText } = mount(deps);
    await act(async () => result.current.toggle());
    await advance(9000); // past the time to give up
    expect(deps.transcribe).not.toHaveBeenCalled();
    expect(onText).not.toHaveBeenCalled();
    expect(result.current.error).toEqual({ kind: "empty" });
    expect(result.current.phase).toBe("idle");
    expect(state.cancelled).toBe(1); // the microphone was released
  });

  it("says so when the server heard nothing intelligible", async () => {
    const { deps, state } = fakeDeps({ transcribe: vi.fn(async () => "  ") });
    const { result, onText } = mount(deps);
    await act(async () => result.current.toggle());
    await advance(500);
    state.rms = VOICE;
    await advance(1500);
    await act(async () => result.current.toggle());
    expect(onText).not.toHaveBeenCalled();
    expect(result.current.error).toEqual({ kind: "empty" });
  });

  it("reports a refused microphone", async () => {
    const { deps } = fakeDeps({
      begin: async () => {
        throw new DOMException("no", "NotAllowedError");
      },
    });
    const { result } = mount(deps);
    await act(async () => result.current.toggle());
    expect(result.current.error).toEqual({ kind: "denied" });
    expect(result.current.phase).toBe("idle");
  });

  it("reports a failed transcription with its cause", async () => {
    const cause = new Error("502");
    const { deps, state } = fakeDeps({
      transcribe: vi.fn(async () => {
        throw cause;
      }),
    });
    const { result } = mount(deps);
    await act(async () => result.current.toggle());
    await advance(500);
    state.rms = VOICE;
    await advance(1500);
    await act(async () => result.current.toggle());
    expect(result.current.error).toEqual({ kind: "failed", cause });
    expect(result.current.phase).toBe("idle");
  });

  it("a tap while transcribing gives up, and the text never arrives", async () => {
    let release: (text: string) => void = () => {};
    const { deps, state } = fakeDeps({
      transcribe: vi.fn((_r, _l, signal: AbortSignal) => {
        return new Promise<string>((resolve) => {
          release = resolve;
          signal.addEventListener("abort", () => resolve("never"));
        });
      }),
    });
    const { result, onText } = mount(deps);
    await act(async () => result.current.toggle());
    await advance(500);
    state.rms = VOICE;
    await advance(1500);
    await act(async () => result.current.toggle());
    expect(result.current.phase).toBe("transcribing");
    await act(async () => result.current.toggle());
    release("late");
    await advance(10);
    expect(onText).not.toHaveBeenCalled();
    expect(result.current.phase).toBe("idle");
  });

  it("is dropped when a voice call takes the microphone", async () => {
    const { deps, state } = fakeDeps();
    const { result, rerender } = mount(deps);
    await act(async () => result.current.toggle());
    expect(result.current.phase).toBe("listening");
    rerender({ suspended: true });
    expect(result.current.phase).toBe("idle");
    expect(state.cancelled).toBe(1);
    expect(result.current.supported).toBe(false);
  });

  it("is dropped when the page goes to the background", async () => {
    const { deps, state } = fakeDeps();
    const { result } = mount(deps);
    await act(async () => result.current.toggle());
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    expect(result.current.phase).toBe("idle");
    expect(state.cancelled).toBe(1);
  });

  it("does nothing in a browser that cannot record", async () => {
    const { deps, state } = fakeDeps({ supported: false });
    const { result } = mount(deps);
    await act(async () => result.current.toggle());
    expect(state.begun).toBe(0);
    expect(result.current.supported).toBe(false);
  });
});
