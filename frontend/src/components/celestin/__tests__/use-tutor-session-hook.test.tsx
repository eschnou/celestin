// @vitest-environment jsdom
/**
 * The hook itself (004 R6): progress arrives with the chapter, the reset goes
 * through the API, and nothing touches browser storage any more.
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TutorEvent } from "@/lib/tutor/types";
import { useTutorSession } from "../use-tutor-session";

vi.mock("@/lib/tutor/client", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/tutor/client")>();
  return { ...mod, streamTurn: vi.fn() };
});
vi.mock("@/lib/tutor/courses", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/tutor/courses")>();
  return { ...mod, resetChapter: vi.fn() };
});

import { streamTurn } from "@/lib/tutor/client";
import { resetChapter } from "@/lib/tutor/courses";

const SCOPE = { courseId: "maths-5e", chapterId: "suites" };
const PROGRESS = { done: ["suites"], active: "sa-definition" };

function scripted(events: TutorEvent[]) {
  return vi.mocked(streamTurn).mockImplementation(async function* () {
    for (const event of events) yield event;
  } as never);
}

const OPENING: TutorEvent[] = [
  { event: "turn.start", turn_id: "t1" },
  { event: "text.delta", block_id: 0, text: "Bonjour" },
  { event: "turn.end", reason: "end", usage: {} },
];

function mount(progress = PROGRESS) {
  return renderHook(() => useTutorSession({ ...SCOPE, initialProgress: progress }));
}

beforeEach(() => scripted(OPENING));
afterEach(() => vi.clearAllMocks());

describe("useTutorSession", () => {
  it("starts from the progress that came with the chapter", async () => {
    const { result } = mount();
    expect(result.current.progress).toEqual(PROGRESS);
    await waitFor(() => expect(result.current.status).toBe("idle"));
    expect(vi.mocked(streamTurn).mock.calls[0]![0]).toEqual(SCOPE);
  });

  it("never reads or writes browser storage", async () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem");
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const { result } = mount();
    await waitFor(() => expect(result.current.status).toBe("idle"));
    act(() => result.current.send("salut"));
    await waitFor(() => expect(result.current.status).toBe("idle"));
    expect(getItem).not.toHaveBeenCalled();
    expect(setItem).not.toHaveBeenCalled();
  });

  it("resets through the API, then reopens the chapter from scratch", async () => {
    vi.mocked(resetChapter).mockResolvedValue(undefined);
    const { result } = mount();
    await waitFor(() => expect(result.current.status).toBe("idle"));
    act(() => result.current.resetProgress());
    await waitFor(() => expect(result.current.status).toBe("idle"));
    expect(resetChapter).toHaveBeenCalledWith("maths-5e", "suites");
    expect(result.current.progress).toEqual({ done: [], active: null });
    expect(vi.mocked(streamTurn)).toHaveBeenCalledTimes(2);
  });

  it("refuses a turn started while the reset is in flight", async () => {
    let release!: () => void;
    vi.mocked(resetChapter).mockImplementation(
      () => new Promise<void>((resolve) => (release = () => resolve())),
    );
    const { result } = mount();
    await waitFor(() => expect(result.current.status).toBe("idle"));
    act(() => result.current.resetProgress());
    // The board's « Étape suivante » is gated on nextStep, not on status.
    act(() => result.current.send("Étape suivante."));
    expect(vi.mocked(streamTurn)).toHaveBeenCalledTimes(1);
    await act(async () => {
      release();
    });
    await waitFor(() => expect(vi.mocked(streamTurn)).toHaveBeenCalledTimes(2));
    expect(result.current.entries.some((e) => e.text === "Étape suivante.")).toBe(false);
  });

  it("keeps the transcript and reports the failure when the reset cannot be saved", async () => {
    vi.mocked(resetChapter).mockRejectedValue(new Error("500"));
    const { result } = mount();
    await waitFor(() => expect(result.current.status).toBe("idle"));
    act(() => result.current.resetProgress());
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.progress).toEqual(PROGRESS);
    expect(result.current.entries.at(-1)).toMatchObject({ role: "error" });
  });
});

describe("the transport seam (007 §3.11)", () => {
  const RESTORED = {
    entries: [],
    history: [{ kind: "learner" as const, text: "déjà dit" }],
    boards: [],
    board: null,
    progress: { done: [], active: null },
    nextStep: null,
    blocks: {},
    voice: false,
  };

  function mountWith(transport: ReturnType<typeof vi.fn>, initialState?: typeof RESTORED) {
    return renderHook(() =>
      useTutorSession({
        ...SCOPE,
        initialProgress: PROGRESS,
        transport: transport as never,
        ...(initialState ? { initialState } : {}),
      }),
    );
  }

  type Input = { history: unknown[]; message: string | null };

  function transportOf(events: TutorEvent[]) {
    return vi.fn(async function* (_input: Input, _signal: AbortSignal) {
      for (const event of events) yield event;
    });
  }

  it("uses the given transport instead of the parcours one", async () => {
    const transport = transportOf(OPENING);
    const { result } = mountWith(transport);
    await waitFor(() => expect(result.current.status).toBe("idle"));
    expect(transport).toHaveBeenCalledTimes(1);
    expect(vi.mocked(streamTurn)).not.toHaveBeenCalled();
    expect(transport.mock.calls[0]![0]).toEqual({ history: [], message: null });
  });

  it("sends the message, and the history the parcours needs, on a learner turn", async () => {
    const transport = transportOf(OPENING);
    const { result } = mountWith(transport);
    await waitFor(() => expect(result.current.status).toBe("idle"));

    act(() => result.current.send("et les suites ?"));
    await waitFor(() => expect(result.current.status).toBe("idle"));
    expect(transport.mock.calls[1]![0].message).toBe("et les suites ?");
  });

  it("does not open a restored conversation again", async () => {
    const transport = transportOf(OPENING);
    mountWith(transport, RESTORED);
    await new Promise((r) => setTimeout(r, 10));
    expect(transport).not.toHaveBeenCalled();
  });

  it("re-sends the same message on retry rather than the transcript", async () => {
    const failing = vi.fn(async function* (
      _input: Input,
      _signal: AbortSignal,
    ): AsyncGenerator<TutorEvent> {
      yield { event: "turn.start", turn_id: "t" };
      yield { event: "error", code: "network", message: "raté" };
      yield { event: "turn.end", reason: "end", usage: {} };
    });
    const { result } = mountWith(failing, RESTORED);

    act(() => result.current.send("ma question"));
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(failing.mock.calls[0]![0].message).toBe("ma question");

    act(() => result.current.retry());
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(failing.mock.calls[1]![0].message).toBe("ma question");
  });
});
