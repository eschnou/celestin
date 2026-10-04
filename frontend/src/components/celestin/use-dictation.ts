/**
 * Dictation: the composer's microphone turns a spoken take into written text (not the voice call).
 *
 * One tap starts a take; the take ends by itself when the student has said something and then stops (see
 * `lib/tutor/dictation/vad.ts`), when nothing is said for a while, at the cap, or on a second tap. The
 * recording is sent whole to the backend, transcribed and handed to `onText`; the student reads it, fixes it
 * and sends it like any message. The microphone is released the moment the take ends.
 *
 * All browser objects come through `DictationDeps`, so the tests run under jsdom with fakes.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { CourseLanguage } from "@/lib/course-language";
import { transcribe as apiTranscribe } from "@/lib/tutor/dictation/client";
import { DEFAULT_VAD, Vad } from "@/lib/tutor/dictation/vad";

export type DictationPhase = "idle" | "starting" | "listening" | "transcribing";

/** Why a take gave nothing: the microphone was refused, nothing was said, or the transcription failed. */
export type DictationError =
  { kind: "denied" } | { kind: "empty" } | { kind: "failed"; cause: unknown };

export type Recording = { blob: Blob; durationMs: number };

export type TakeHandle = {
  /** Loudness now, 0 to 1. */
  level: () => number;
  /** Ends the take and gives what was recorded. */
  finish: () => Promise<Recording>;
  /** Ends the take and drops it. */
  cancel: () => void;
};

export type DictationDeps = {
  supported: boolean;
  /** Asks for the microphone and starts recording: rejects when it is refused. */
  begin: () => Promise<TakeHandle>;
  transcribe: (
    recording: Recording,
    language: CourseLanguage | null,
    signal: AbortSignal,
  ) => Promise<string>;
  now: () => number;
  /** The tick of the loudness reading, in ms. */
  tickMs: number;
};

const MIME_TYPES = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus", "audio/webm"];

export function dictationSupported(): boolean {
  return (
    typeof navigator !== "undefined" &&
    typeof navigator.mediaDevices?.getUserMedia === "function" &&
    typeof MediaRecorder !== "undefined" &&
    typeof AudioContext !== "undefined"
  );
}

/** The browser's real microphone, recorder and meter. */
export function defaultDictationDeps(): DictationDeps {
  return {
    supported: dictationSupported(),
    begin: async () => {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      const release = () => stream.getTracks().forEach((track) => track.stop());
      try {
        const mimeType = MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type));
        const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
        const chunks: Blob[] = [];
        recorder.ondataavailable = (event) => {
          if (event.data.size > 0) chunks.push(event.data);
        };
        const stopped = new Promise<void>((resolve) => {
          recorder.onstop = () => resolve();
        });
        const context = new AudioContext();
        void context.resume();
        const analyser = context.createAnalyser();
        analyser.fftSize = 1024;
        context.createMediaStreamSource(stream).connect(analyser);
        const samples = new Float32Array(analyser.fftSize);
        const startedAt = Date.now();
        recorder.start();
        const end = () => {
          if (recorder.state !== "inactive") recorder.stop();
          release();
          void context.close();
        };
        return {
          level: () => {
            analyser.getFloatTimeDomainData(samples);
            let sum = 0;
            for (const sample of samples) sum += sample * sample;
            return Math.sqrt(sum / samples.length);
          },
          finish: async () => {
            end();
            await stopped;
            return {
              blob: new Blob(chunks, { type: recorder.mimeType || mimeType || "audio/webm" }),
              durationMs: Date.now() - startedAt,
            };
          },
          cancel: end,
        };
      } catch (error) {
        release();
        throw error;
      }
    },
    transcribe: (recording, language, signal) =>
      apiTranscribe(recording.blob, { language, durationMs: recording.durationMs }, signal),
    now: () => Date.now(),
    tickMs: 50,
  };
}

export type DictationControls = {
  /** Whether this browser can record at all. */
  supported: boolean;
  phase: DictationPhase;
  /** 0 to 1, for a meter; 0 when not recording. */
  level: number;
  /** Whether speech has been heard in the take in progress. */
  heard: boolean;
  error: DictationError | null;
  /** Starts a take; stops it (and sends it) while one is on; cancels while it is being transcribed. */
  toggle: () => void;
  cancel: () => void;
  clearError: () => void;
};

/**
 * `suspended`: something else owns the microphone (a voice call): a take in progress is dropped and none starts.
 */
export function useDictation(opts: {
  /** The course's language, or null for no hint. */
  language: CourseLanguage | null;
  onText: (text: string) => void;
  suspended?: boolean;
  deps?: DictationDeps;
}): DictationControls {
  const [deps] = useState(() => opts.deps ?? defaultDictationDeps());
  const { language, suspended = false } = opts;
  const [phase, setPhaseState] = useState<DictationPhase>("idle");
  const [level, setLevel] = useState(0);
  const [heard, setHeard] = useState(false);
  const [error, setError] = useState<DictationError | null>(null);

  const phaseRef = useRef<DictationPhase>("idle");
  const takeRef = useRef<TakeHandle | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const onTextRef = useRef(opts.onText);
  const languageRef = useRef(language);
  useEffect(() => {
    onTextRef.current = opts.onText;
    languageRef.current = language;
  });
  const generation = useRef(0);
  const vadRef = useRef<Vad | null>(null);

  const setPhase = useCallback((next: DictationPhase) => {
    phaseRef.current = next;
    setPhaseState(next);
  }, []);

  const stopTimer = useCallback(() => {
    if (timerRef.current !== null) clearInterval(timerRef.current);
    timerRef.current = null;
  }, []);

  const reset = useCallback(() => {
    stopTimer();
    takeRef.current = null;
    setLevel(0);
    setHeard(false);
    setPhase("idle");
  }, [setPhase, stopTimer]);

  /** Ends the take in progress and sends what was heard. */
  const finish = useCallback(
    async (wasHeard: boolean) => {
      const take = takeRef.current;
      if (!take || phaseRef.current !== "listening") return;
      const mine = generation.current;
      stopTimer();
      takeRef.current = null;
      setLevel(0);
      if (!wasHeard) {
        // Nothing worth sending: drop it without a round trip.
        take.cancel();
        reset();
        setError({ kind: "empty" });
        return;
      }
      setPhase("transcribing");
      try {
        const recording = await take.finish();
        const controller = new AbortController();
        abortRef.current = controller;
        const text = (
          await deps.transcribe(recording, languageRef.current, controller.signal)
        ).trim();
        if (mine !== generation.current) return; // cancelled meanwhile
        if (text) onTextRef.current(text);
        else setError({ kind: "empty" });
      } catch (cause) {
        if (mine !== generation.current) return;
        setError({ kind: "failed", cause });
      } finally {
        if (mine === generation.current) {
          abortRef.current = null;
          reset();
        }
      }
    },
    [deps, reset, setPhase, stopTimer],
  );

  const start = useCallback(async () => {
    if (!deps.supported || suspended || phaseRef.current !== "idle") return;
    const mine = ++generation.current;
    setError(null);
    setPhase("starting");
    let take: TakeHandle;
    try {
      take = await deps.begin();
    } catch {
      if (mine === generation.current) {
        reset();
        setError({ kind: "denied" });
      }
      return;
    }
    if (mine !== generation.current) {
      take.cancel(); // cancelled while the browser asked for the microphone
      return;
    }
    takeRef.current = take;
    setPhase("listening");
    const vad = new Vad(deps.now(), DEFAULT_VAD);
    let ticks = 0;
    timerRef.current = setInterval(() => {
      const verdict = vad.push(take.level(), deps.now());
      if (verdict.heard) setHeard(true);
      if (++ticks % 2 === 0) setLevel(Math.min(1, take.level() * 6));
      if (verdict.stop) void finish(verdict.heard);
    }, deps.tickMs);
    vadRef.current = vad;
  }, [deps, finish, reset, setPhase, suspended]);

  const cancel = useCallback(() => {
    generation.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    takeRef.current?.cancel();
    vadRef.current = null;
    reset();
  }, [reset]);

  const toggle = useCallback(() => {
    switch (phaseRef.current) {
      case "idle":
        void start();
        break;
      case "listening":
        void finish(vadRef.current?.heard ?? false);
        break;
      default:
        cancel(); // starting or transcribing: a tap is « never mind »
    }
  }, [cancel, finish, start]);

  // A voice call, or the page going to the background, ends a take: nobody is dictating any more.
  useEffect(() => {
    if (suspended && phaseRef.current !== "idle") cancel();
  }, [suspended, cancel]);
  useEffect(() => {
    const onHidden = () => {
      if (document.visibilityState === "hidden" && phaseRef.current !== "idle") cancel();
    };
    document.addEventListener("visibilitychange", onHidden);
    window.addEventListener("pagehide", cancel);
    return () => {
      document.removeEventListener("visibilitychange", onHidden);
      window.removeEventListener("pagehide", cancel);
    };
  }, [cancel]);
  useEffect(() => cancel, [cancel]);

  const clearError = useCallback(() => setError(null), []);

  return {
    supported: deps.supported && !suspended,
    phase,
    level,
    heard,
    error,
    toggle,
    cancel,
    clearError,
  };
}
