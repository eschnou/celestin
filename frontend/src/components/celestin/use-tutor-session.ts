/**
 * Session state for the current page load, plus the chapter progress (002 R5).
 *
 * The conversation is not persisted: a reload starts a fresh one, opening turn
 * included. Progress is owned by the server since 004: it arrives with the
 * chapter, changes here only through the two section events (which the backend
 * has already stored), and a reset goes through the API.
 *
 * Two parallel views of the conversation are kept on purpose:
 *  - `entries` is what the learner sees, markers and errors included;
 *  - `history` is what goes back to the model, and holds tool calls instead.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { genericError, streamTurn } from "@/lib/tutor/client";
import { VOICE_OFF_MARKER, VOICE_ON_MARKER } from "@/lib/tutor/labels";
import { m } from "@/paraglide/messages";
import { resetChapter } from "@/lib/tutor/courses";
import type { VoiceEndReason } from "@/lib/tutor/voice/types";
import {
  EMPTY_PROGRESS,
  type BoardCard,
  type HistoryEntry,
  type LessonScope,
  type NextStep,
  type Progress,
  type StoredEntry,
  type TranscriptEntry,
  type TutorEvent,
} from "@/lib/tutor/types";

export type SessionStatus = "idle" | "streaming" | "error";

/** Client-internal events (003 design 3.13). Not part of the SSE contract. */
export type LocalEvent = { event: "voice.on" } | { event: "voice.off"; reason: VoiceEndReason };
export type SessionEvent = TutorEvent | LocalEvent;

/** What the voice hook needs from the session (003 design 3.12). */
export type TutorSessionHandle = {
  dispatch: (event: SessionEvent) => void;
  appendLearner: (text: string, spoken?: boolean) => void;
  markInterrupted: () => void;
  snapshot: () => { history: HistoryEntry[]; progress: Progress };
};

let counter = 0;
const nextId = () => `e${++counter}`;

const hasRaf = typeof requestAnimationFrame === "function";
const schedule = (fn: () => void): number =>
  hasRaf ? requestAnimationFrame(fn) : (setTimeout(fn, 16) as unknown as number);
const cancelScheduled = (handle: number): void =>
  hasRaf ? cancelAnimationFrame(handle) : clearTimeout(handle);

export type SessionState = {
  entries: TranscriptEntry[];
  history: HistoryEntry[];
  boards: BoardCard[];
  board: BoardCard | null;
  progress: Progress;
  /** What the board's page-turn button offers (null: greyed). A proposed step
   *  dies with the next card; a closed section survives its recap card and dies
   *  when the next section starts or a new turn begins. */
  nextStep: NextStep;
  /** Where each streaming text block lives, so deltas append in place. */
  blocks: Record<number, { entry: string; history: number }>;
  /** A voice session is open: new tutor text is spoken, not written. */
  voice: boolean;
};

export const EMPTY_SESSION: SessionState = {
  entries: [],
  history: [],
  boards: [],
  board: null,
  progress: EMPTY_PROGRESS,
  nextStep: null,
  blocks: {},
  voice: false,
};

function marker(text: string, boardIndex: number | null = null): TranscriptEntry {
  return { id: nextId(), role: "marker", text, boardIndex };
}

/** Pure reducer, so the whole event pipeline is testable without React. */
export function reduce(state: SessionState, event: SessionEvent): SessionState {
  switch (event.event) {
    case "voice.on":
      return { ...state, voice: true, entries: [...state.entries, marker(VOICE_ON_MARKER())] };

    case "voice.off":
      return {
        ...state,
        voice: false,
        entries: [...state.entries, marker(VOICE_OFF_MARKER[event.reason]())],
      };

    case "turn.start":
      return { ...state, blocks: {}, nextStep: null };

    case "text.delta": {
      const known = state.blocks[event.block_id];
      if (known) {
        return {
          ...state,
          entries: state.entries.map((e) =>
            e.id === known.entry && e.role === "tutor" ? { ...e, text: e.text + event.text } : e,
          ),
          history: state.history.map((h, i) =>
            i === known.history && h.kind === "tutor" ? { ...h, text: h.text + event.text } : h,
          ),
        };
      }
      const id = nextId();
      return {
        ...state,
        entries: [
          ...state.entries,
          {
            id,
            role: "tutor",
            text: event.text,
            blockId: event.block_id,
            ...(state.voice ? { spoken: true as const } : {}),
          },
        ],
        history: [...state.history, { kind: "tutor", text: event.text }],
        blocks: {
          ...state.blocks,
          [event.block_id]: { entry: id, history: state.history.length },
        },
      };
    }

    case "board.set":
      return {
        ...state,
        // A title card only opens the section: there is nothing on it to talk
        // through, so the page can turn straight away without `propose_next_step`.
        nextStep:
          state.nextStep?.kind === "section"
            ? state.nextStep
            : event.card.kind === "title"
              ? { kind: "step" }
              : null,
        board: event.card,
        boards: [...state.boards, event.card],
        entries: [...state.entries, marker(event.marker, state.boards.length)],
        history: [
          ...state.history,
          { kind: "tool", name: "display_board", arguments: { card: event.card }, ok: true },
        ],
      };

    case "board.clear":
      return {
        ...state,
        nextStep: state.nextStep?.kind === "section" ? state.nextStep : null,
        board: null,
        entries: [...state.entries, marker(event.marker)],
        history: [...state.history, { kind: "tool", name: "clear_board", arguments: {}, ok: true }],
      };

    case "section.start":
      return {
        ...state,
        nextStep: null,
        // A section starts on a fresh board, review included: the strip empties and
        // the markers that pointed at the old boards stop being clickable.
        board: null,
        boards: [],
        // A review leaves the path where it is (R3.6).
        progress: event.review ? state.progress : { ...state.progress, active: event.section_id },
        entries: [
          ...state.entries.map((e) => (e.role === "marker" ? { ...e, boardIndex: null } : e)),
          marker(event.marker),
        ],
        history: [
          ...state.history,
          {
            kind: "tool",
            name: "start_section",
            arguments: { section_id: event.section_id },
            ok: true,
          },
        ],
      };

    case "section.done":
      return {
        ...state,
        nextStep: event.next_section_id
          ? { kind: "section", sectionId: event.next_section_id }
          : null,
        progress: {
          done: state.progress.done.includes(event.section_id)
            ? state.progress.done
            : [...state.progress.done, event.section_id],
          active: null,
        },
        entries: [...state.entries, marker(event.marker)],
        history: [
          ...state.history,
          // The summary stays server-side (logged); a replay needs only the id.
          {
            kind: "tool",
            name: "complete_section",
            arguments: { section_id: event.section_id },
            ok: true,
          },
        ],
      };

    case "step.ready":
      return {
        ...state,
        nextStep: { kind: "step" },
        entries: [...state.entries, marker(event.marker)],
        history: [
          ...state.history,
          { kind: "tool", name: "propose_next_step", arguments: {}, ok: true },
        ],
      };

    case "error":
      return {
        ...state,
        entries: [
          ...state.entries,
          { id: nextId(), role: "error", text: event.message, code: event.code },
        ],
      };

    case "turn.end":
      if (event.reason !== "max_rounds") return state;
      return {
        ...state,
        entries: [...state.entries, { id: nextId(), role: "error", text: m.lesson_max_rounds() }],
      };

    default:
      return state;
  }
}

export function appendLearner(state: SessionState, text: string, spoken = false): SessionState {
  return {
    ...state,
    entries: [
      ...state.entries,
      { id: nextId(), role: "learner", text, ...(spoken ? { spoken: true as const } : {}) },
    ],
    history: [...state.history, { kind: "learner", text }],
  };
}

export function markInterrupted(state: SessionState): SessionState {
  const entries = [...state.entries];
  for (let i = entries.length - 1; i >= 0; i--) {
    const entry = entries[i]!;
    if (entry.role === "tutor") {
      entries[i] = { ...entry, interrupted: true };
      break;
    }
  }
  return { ...state, entries };
}

/** What a turn needs. The parcours transport posts `history` and ignores
 *  `message`; the discussion transport posts `message` and ignores `history`, so
 *  neither shape can reach the wrong route (007 §3.11). */
export type TurnInput = { history: HistoryEntry[]; message: string | null };
export type TurnTransport = (input: TurnInput, signal: AbortSignal) => AsyncGenerator<TutorEvent>;

/**
 * A stored conversation as a session (007 §3.11). The entries are folded back
 * through the same `reduce` that built them live, so the transcript, the board
 * history and the markers cannot drift from what the learner saw.
 */
export function sessionFromEntries(entries: StoredEntry[]): SessionState {
  let state = EMPTY_SESSION;
  let block = 0;
  for (const entry of entries) {
    if (entry.kind === "learner") {
      state = appendLearner(state, entry.text ?? "");
    } else if (entry.kind === "tutor") {
      state = reduce(state, { event: "text.delta", block_id: block, text: entry.text ?? "" });
      block += 1;
    } else if (entry.name === "display_board") {
      const card = entry.arguments?.["card"] as BoardCard | undefined;
      if (card) {
        state = reduce(state, { event: "board.set", card, marker: entry.marker ?? "" });
      }
    } else if (entry.name === "clear_board") {
      state = reduce(state, { event: "board.clear", marker: entry.marker ?? "" });
    }
  }
  return state;
}

export type TutorSessionOptions = LessonScope & {
  initialProgress: Progress;
  /** Defaults to the parcours transport: `POST /api/chat` with the transcript. */
  transport?: TurnTransport;
  /** A restored conversation (007 R4.2); defaults to an empty session. */
  initialState?: SessionState;
};

/**
 * Mount the hook once the chapter and its progress are loaded (004 R6.4): the
 * initial state is built synchronously from `initialProgress`, so there is never a
 * pre-restore state to guard. A new class or chapter is a new mount (the route keys
 * the screen on both), so the scope is fixed for the hook's life.
 */
export function useTutorSession({
  courseId,
  chapterId,
  initialProgress,
  transport,
  initialState,
}: TutorSessionOptions) {
  const [state, setState] = useState<SessionState>(() => ({
    ...(initialState ?? EMPTY_SESSION),
    progress: initialProgress,
  }));
  const [status, setStatus] = useState<SessionStatus>("idle");
  const stateRef = useRef(state);

  /** Every change goes through here: the ref is the truth, React follows. A
   *  synchronous reader (the voice tool queue) then never sees a stale state. */
  const apply = useCallback((fn: (prev: SessionState) => SessionState) => {
    const next = fn(stateRef.current);
    stateRef.current = next;
    setState(next);
  }, []);

  const abortRef = useRef<AbortController | null>(null);
  const startedRef = useRef(false);
  /** State as the current turn began, so a failed turn can be rolled back. */
  const turnStartRef = useRef<SessionState>(EMPTY_SESSION);
  /** The last turn's input, so `retry()` re-sends it rather than guessing. */
  const lastInputRef = useRef<TurnInput>({ history: [], message: null });
  /** True while the reset round trip is in flight: `abortRef` is null then, and
   *  a turn started in that window would be orphaned by the wipe that follows. */
  const resettingRef = useRef(false);

  /** Deltas queue here and flush on an animation frame, so a fast stream does not
   *  re-render the transcript once per token (NFR 4.2.2). */
  const queueRef = useRef<SessionEvent[]>([]);
  const frameRef = useRef<number | null>(null);

  const flush = useCallback(() => {
    if (frameRef.current !== null) {
      cancelScheduled(frameRef.current);
      frameRef.current = null;
    }
    const queued = queueRef.current;
    if (queued.length === 0) return;
    queueRef.current = [];
    apply((prev) => queued.reduce(reduce, prev));
  }, [apply]);

  const push = useCallback(
    (event: SessionEvent) => {
      queueRef.current.push(event);
      // Anything that is not a token flushes immediately, so ordering between
      // text and board events is preserved exactly as the backend sent it.
      if (event.event !== "text.delta") {
        flush();
        return;
      }
      if (frameRef.current !== null) return;
      frameRef.current = schedule(flush);
    },
    [flush],
  );

  const run = useCallback(
    async (input: TurnInput) => {
      const controller = new AbortController();
      abortRef.current = controller;
      turnStartRef.current = stateRef.current;
      // Kept so `retry()` re-sends the same turn: a discussion turn is its
      // message, not the transcript, so replaying the history would send nothing.
      lastInputRef.current = input;
      setStatus("streaming");
      let failed = false;
      try {
        const stream =
          transport?.(input, controller.signal) ??
          streamTurn({ courseId, chapterId }, input.history, controller.signal);
        for await (const event of stream) {
          if (event.event === "error") failed = true;
          push(event);
        }
      } catch {
        if (!controller.signal.aborted) {
          failed = true;
          push({ event: "error", code: "network", message: genericError() });
        }
      } finally {
        flush();
        // Only the owner tears down: a run that has already been superseded must
        // not clear the newer run's controller or overwrite its status.
        if (abortRef.current === controller) {
          abortRef.current = null;
          setStatus(failed ? "error" : "idle");
        }
      }
    },
    [chapterId, courseId, flush, push, transport],
  );

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || abortRef.current || resettingRef.current) return;
      apply((prev) => appendLearner(prev, trimmed));
      void run({ history: stateRef.current.history, message: trimmed });
    },
    [apply, run],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    flush();
    apply(markInterrupted);
    setStatus("idle");
  }, [apply, flush]);

  const retry = useCallback(() => {
    if (abortRef.current) return;
    // Roll the failed turn back rather than just hiding its error. Keeping the
    // half-finished reply would render it above the new one and, worse, hand the
    // model its own truncated sentence as a finished message.
    // `turnStartRef` and the kept input were taken from the same snapshot, so the
    // input's history is already the rolled-back one.
    apply(() => turnStartRef.current);
    void run(lastInputRef.current);
  }, [apply, run]);

  const showBoard = useCallback(
    (index: number) => {
      apply((prev) => ({ ...prev, board: prev.boards[index] ?? prev.board }));
    },
    [apply],
  );

  /** Back to section 1 and a fresh conversation (R5.5). The caller confirms first;
   *  the server record is cleared before the new opening turn (004 R6.6). */
  const resetProgress = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    resettingRef.current = true;
    setStatus("streaming");
    void resetChapter(courseId, chapterId)
      .then(() => {
        resettingRef.current = false;
        apply(() => EMPTY_SESSION);
        setStatus("idle");
        void run({ history: [], message: null });
      })
      .catch(() => {
        resettingRef.current = false;
        apply((prev) =>
          reduce(prev, { event: "error", code: "reset_failed", message: m.lesson_reset_failed() }),
        );
        setStatus("error");
      });
  }, [apply, chapterId, courseId, run]);

  // The voice hook's window onto the session (003 design 3.13).
  const handle = useMemo<TutorSessionHandle>(
    () => ({
      dispatch: push,
      appendLearner: (text, spoken) => apply((prev) => appendLearner(prev, text, spoken)),
      markInterrupted: () => apply(markInterrupted),
      snapshot: () => ({
        history: stateRef.current.history,
        progress: stateRef.current.progress,
      }),
    }),
    [apply, push],
  );

  // The opening turn: the tutor speaks first, unprompted (R3.8), from the progress
  // restored for this chapter (R5.4).
  //
  // Start and teardown live in one effect on purpose. Split across two, a
  // re-invoked effect (React's development double-invoke, or a remount during
  // hydration) aborts the request the guard then refuses to restart, and the
  // session opens silently empty.
  useEffect(() => {
    if (!startedRef.current) {
      startedRef.current = true;
      // A restored conversation already has its opening turn (007 R4.2); only an
      // empty session needs Célestin to speak first.
      if (stateRef.current.history.length === 0) void run({ history: [], message: null });
    }
    return () => {
      startedRef.current = false;
      abortRef.current?.abort();
      abortRef.current = null;
      if (frameRef.current !== null) {
        cancelScheduled(frameRef.current);
        frameRef.current = null;
      }
    };
  }, [run]);

  return {
    entries: state.entries,
    board: state.board,
    boards: state.boards,
    progress: state.progress,
    nextStep: state.nextStep,
    status,
    send,
    cancel,
    retry,
    showBoard,
    resetProgress,
    handle,
  };
}
