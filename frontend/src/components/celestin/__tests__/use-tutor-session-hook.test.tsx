// @vitest-environment jsdom
/**
 * The hook itself (004 R6): progress arrives with the chapter, the reset goes
 * through the API, and nothing touches browser storage any more.
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TutorEvent } from "@/lib/tutor/types";
import { sessionFromEntries, useTutorSession } from "../use-tutor-session";

vi.mock("@/lib/tutor/client", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/tutor/client")>();
  return { ...mod, streamTurn: vi.fn() };
});
vi.mock("@/lib/tutor/courses", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/tutor/courses")>();
  return { ...mod, resetChapter: vi.fn() };
});
vi.mock("@/lib/tutor/voice/client", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/tutor/voice/client")>();
  return { ...mod, reportTurn: vi.fn(async () => {}) };
});

import { streamTurn } from "@/lib/tutor/client";
import { resetChapter } from "@/lib/tutor/courses";
import { reportTurn } from "@/lib/tutor/voice/client";

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
    act(() => {
      void result.current.resetProgress();
    });
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
    act(() => {
      void result.current.resetProgress();
    });
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
    act(() => {
      void result.current.resetProgress();
    });
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
    section: null,
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

  type Input = { message: string | null };

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
    expect(transport.mock.calls[0]![0]).toEqual({ message: null });
  });

  it("sends the message, and nothing else, on a learner turn", async () => {
    const transport = transportOf(OPENING);
    const { result } = mountWith(transport);
    await waitFor(() => expect(result.current.status).toBe("idle"));

    act(() => result.current.send("et les suites ?"));
    await waitFor(() => expect(result.current.status).toBe("idle"));
    expect(transport.mock.calls[1]![0]).toEqual({ message: "et les suites ?" });
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

describe("the parcours transport (018 D1, D6)", () => {
  const SEANCE = sessionFromEntries([
    { kind: "tutor", text: "Bonjour." },
    {
      kind: "tool",
      name: "start_section",
      arguments: { section_id: "sa-definition" },
      review: false,
      marker: "section ouverte",
    },
  ]);

  it("opens an empty séance with a null message", async () => {
    const { result } = mount();
    await waitFor(() => expect(result.current.status).toBe("idle"));
    expect(vi.mocked(streamTurn)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(streamTurn).mock.calls[0]!.slice(0, 2)).toEqual([SCOPE, null]);
  });

  it("does not open a restored séance, and starts from the server's progress", async () => {
    const { result } = renderHook(() =>
      useTutorSession({ ...SCOPE, initialProgress: PROGRESS, initialState: SEANCE }),
    );
    await new Promise((r) => setTimeout(r, 10));
    expect(vi.mocked(streamTurn)).not.toHaveBeenCalled();
    expect(result.current.entries.map((e) => e.role)).toEqual(["tutor", "marker"]);
    expect(result.current.progress).toEqual(PROGRESS);
    expect(result.current.section).toBe("sa-definition");
  });

  it("posts the learner's message, never the transcript", async () => {
    const { result } = renderHook(() =>
      useTutorSession({ ...SCOPE, initialProgress: PROGRESS, initialState: SEANCE }),
    );
    act(() => result.current.send("et la raison ?"));
    await waitFor(() => expect(result.current.status).toBe("idle"));
    const args = vi.mocked(streamTurn).mock.calls[0]!;
    expect(args[0]).toEqual(SCOPE);
    expect(args[1]).toBe("et la raison ?");
  });

  it("re-sends the same message on retry, after rolling the failed turn back", async () => {
    vi.mocked(streamTurn).mockImplementation(async function* () {
      yield { event: "turn.start", turn_id: "t" };
      yield { event: "text.delta", block_id: 0, text: "à moit" };
      yield { event: "error", code: "overloaded", message: "raté" };
      yield { event: "turn.end", reason: "end", usage: {} };
    } as never);
    const { result } = renderHook(() =>
      useTutorSession({ ...SCOPE, initialProgress: PROGRESS, initialState: SEANCE }),
    );
    act(() => result.current.send("ma question"));
    await waitFor(() => expect(result.current.status).toBe("error"));
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(vi.mocked(streamTurn).mock.calls.map((c) => c[1])).toEqual([
      "ma question",
      "ma question",
    ]);
    // One learner entry and one half reply, not two of each.
    expect(result.current.entries.filter((e) => e.role === "learner")).toHaveLength(1);
    expect(result.current.entries.filter((e) => e.text === "à moit")).toHaveLength(1);
  });
});

describe("a stopped turn is reported, a failed one is not (018 D7)", () => {
  const CARD = { kind: "explanation", title: "Définition", blocks: [{ type: "text", text: "x" }] };

  /** A turn that shows a text and a card, then waits until the learner stops it. */
  function stoppable() {
    vi.mocked(streamTurn).mockImplementationOnce(async function* (
      _scope: unknown,
      _message: string | null,
      signal: AbortSignal,
    ) {
      yield { event: "turn.start", turn_id: "t" };
      yield { event: "text.delta", block_id: 0, text: "Regarde bien" };
      yield { event: "board.set", card: CARD, marker: "explication affichée" };
      await new Promise((_, reject) =>
        signal.addEventListener("abort", () => reject(new DOMException("stop", "AbortError"))),
      );
    } as never);
  }

  function deferred() {
    let resolve!: () => void;
    let reject!: (e: unknown) => void;
    const promise = new Promise<void>((res, rej) => {
      resolve = res;
      reject = rej;
    });
    return { promise, resolve, reject };
  }

  const restored = () =>
    renderHook(() =>
      useTutorSession({
        ...SCOPE,
        initialProgress: PROGRESS,
        initialState: sessionFromEntries([{ kind: "tutor", text: "Bonjour." }]),
      }),
    );

  it("reports exactly what the stopped turn kept, and sends the next turn once it is stored", async () => {
    const report = deferred();
    vi.mocked(reportTurn).mockReturnValueOnce(report.promise);
    stoppable();
    const { result } = restored();
    act(() => result.current.send("montre-moi"));
    await waitFor(() => expect(result.current.entries.some((e) => e.role === "marker")).toBe(true));

    act(() => result.current.cancel());
    expect(reportTurn).toHaveBeenCalledTimes(1);
    expect(vi.mocked(reportTurn).mock.calls[0]).toEqual([
      { ...SCOPE, mode: "parcours" },
      [
        { kind: "learner", text: "montre-moi" },
        { kind: "tutor", text: "Regarde bien" },
        { kind: "tool", name: "display_board", arguments: { card: CARD }, ok: true },
      ],
    ]);

    scripted(OPENING);
    act(() => result.current.send("et ensuite ?"));
    await new Promise((r) => setTimeout(r, 10));
    expect(vi.mocked(streamTurn)).toHaveBeenCalledTimes(1); // held behind the report
    await act(async () => report.resolve());
    await waitFor(() => expect(vi.mocked(streamTurn)).toHaveBeenCalledTimes(2));
    expect(vi.mocked(streamTurn).mock.calls[1]![1]).toBe("et ensuite ?");
    await waitFor(() => expect(result.current.status).toBe("idle"));
    expect(reportTurn).toHaveBeenCalledTimes(1);
  });

  it("sends the next turn even when the report fails: that partial turn is just not stored", async () => {
    vi.mocked(reportTurn).mockRejectedValueOnce(new Error("429"));
    stoppable();
    const { result } = restored();
    act(() => result.current.send("montre-moi"));
    await waitFor(() => expect(result.current.entries.some((e) => e.role === "marker")).toBe(true));
    act(() => result.current.cancel());
    scripted(OPENING);
    act(() => result.current.send("et ensuite ?"));
    await waitFor(() => expect(vi.mocked(streamTurn)).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.status).toBe("idle"));
    expect(result.current.entries.some((e) => e.role === "error")).toBe(false);
  });

  it("holds a reset behind the report, so the old séance cannot come back after it", async () => {
    const report = deferred();
    vi.mocked(reportTurn).mockReturnValueOnce(report.promise);
    vi.mocked(resetChapter).mockResolvedValue(undefined);
    stoppable();
    const { result } = restored();
    act(() => result.current.send("montre-moi"));
    await waitFor(() => expect(result.current.entries.some((e) => e.role === "marker")).toBe(true));
    act(() => result.current.cancel());
    act(() => {
      void result.current.resetProgress();
    });
    await new Promise((r) => setTimeout(r, 10));
    expect(resetChapter).not.toHaveBeenCalled();
    await act(async () => report.resolve());
    await waitFor(() => expect(resetChapter).toHaveBeenCalledTimes(1));
  });

  it("retries a turn lost to the network with the same message once, and reports nothing", async () => {
    vi.mocked(streamTurn).mockImplementationOnce(async function* () {
      yield { event: "turn.start", turn_id: "t" };
      yield { event: "text.delta", block_id: 0, text: "à moit" };
      throw new TypeError("network down");
    } as never);
    const { result } = restored();
    act(() => result.current.send("ma question"));
    await waitFor(() => expect(result.current.status).toBe("error"));
    scripted(OPENING);
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.status).toBe("idle"));
    expect(vi.mocked(streamTurn).mock.calls.map((c) => c[1])).toEqual([
      "ma question",
      "ma question",
    ]);
    expect(result.current.entries.filter((e) => e.role === "learner")).toHaveLength(1);
    expect(reportTurn).not.toHaveBeenCalled();
  });

  it("retries an opening turn that failed as an opening turn again, with no report", async () => {
    vi.mocked(streamTurn).mockImplementationOnce(async function* () {
      yield { event: "turn.start", turn_id: "t" };
      yield { event: "text.delta", block_id: 0, text: "Bonj" };
      yield { event: "error", code: "provider_unavailable", message: "raté" };
      yield { event: "turn.end", reason: "end", usage: {} };
    } as never);
    const { result } = mount();
    await waitFor(() => expect(result.current.status).toBe("error"));
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.status).toBe("idle"));
    expect(vi.mocked(streamTurn).mock.calls.map((c) => c[1])).toEqual([null, null]);
    expect(result.current.entries.filter((e) => e.role === "tutor").map((e) => e.text)).toEqual([
      "Bonjour",
    ]);
    expect(reportTurn).not.toHaveBeenCalled();
  });

  it("reports nothing when a session with its own transport (a discussion) is stopped", async () => {
    const transport = vi.fn(async function* (_input: unknown, signal: AbortSignal) {
      yield { event: "turn.start", turn_id: "t" } as TutorEvent;
      yield { event: "text.delta", block_id: 0, text: "Hmm" } as TutorEvent;
      await new Promise((_, reject) =>
        signal.addEventListener("abort", () => reject(new DOMException("stop", "AbortError"))),
      );
    });
    const { result } = renderHook(() =>
      useTutorSession({
        ...SCOPE,
        initialProgress: PROGRESS,
        transport: transport as never,
        initialState: sessionFromEntries([{ kind: "tutor", text: "Bonjour." }]),
      }),
    );
    act(() => result.current.send("salut"));
    await waitFor(() => expect(result.current.entries.some((e) => e.text === "Hmm")).toBe(true));
    act(() => result.current.cancel());
    expect(reportTurn).not.toHaveBeenCalled();
  });

  it("reports nothing when the stop button is pressed with no turn running", async () => {
    const { result } = restored();
    act(() => result.current.cancel());
    expect(reportTurn).not.toHaveBeenCalled();
  });
});
