/**
 * A voice session on top of the tutor session (003 design 3.12).
 *
 * Owns the call, the timers and the tool queue; talks to the tutor session only
 * through its handle. Everything browser-specific is injectable so the whole
 * orchestration runs under jsdom against fakes.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { genericError } from "@/lib/tutor/client";
import {
  VOICE_BUSY_ELSEWHERE,
  VOICE_CONNECT_FAILED,
  VOICE_MIC_DENIED,
  VOICE_REALTIME_ERROR,
  VOICE_TOOL_FAILED_ENTRY,
} from "@/lib/tutor/labels";
import { useLearnerSentences } from "@/lib/tutor/prompts";
import { bridge, initialBridgeState, sumUsage, type BridgeAction } from "@/lib/tutor/voice/bridge";
import {
  createVoiceSession as apiCreateSession,
  executeTool as apiExecuteTool,
  reportUsage as apiReportUsage,
  VoiceRequestError,
} from "@/lib/tutor/voice/client";
import {
  functionOutputItem,
  RESPONSE_CREATE,
  seedItem,
  systemTextItem,
  userTextItem,
  type RealtimeClientEvent,
  type RealtimeServerEvent,
} from "@/lib/tutor/voice/realtime";
import {
  browserDeps,
  requestMic,
  VoiceSession,
  VoiceSessionError,
  voiceSupported,
  type CloseReason,
} from "@/lib/tutor/voice/session";
import {
  EMPTY_USAGE,
  type ToolCall,
  type VoiceEndReason,
  type VoicePhase,
  type VoiceSessionInfo,
  type VoiceUsage,
} from "@/lib/tutor/voice/types";
import { recordVoiceTurn } from "@/lib/tutor/discussion";
import type { HistoryEntry, LessonScope } from "@/lib/tutor/types";
import type { TutorSessionHandle } from "./use-tutor-session";

/** How long a turn in progress may finish after the cap fires. */
export const CAP_GRACE_MS = 10_000;
/** How long a tab waits for a "busy" answer from another tab. */
export const PROBE_MS = 150;

/** The call as the hook drives it; `VoiceSession` in production, a fake in tests. */
export type CallHandle = {
  connect: (secret: string, mic: MediaStream, callsUrl: string) => Promise<void>;
  send: (event: RealtimeClientEvent) => void;
  setMuted: (muted: boolean) => void;
  close: () => void;
  readonly open: boolean;
};

export type BusMessage = { type: "probe" | "busy" | "stop" };
export type BusChannel = {
  postMessage: (msg: BusMessage) => void;
  onmessage: ((e: { data: BusMessage }) => void) | null;
  close: () => void;
};

export type VoiceDeps = {
  supported: boolean;
  getMic: () => Promise<MediaStream>;
  createCall: (
    onEvent: (e: RealtimeServerEvent) => void,
    onClose: (reason: CloseReason) => void,
  ) => CallHandle;
  api: {
    createVoiceSession: (scope: LessonScope, history: HistoryEntry[]) => Promise<VoiceSessionInfo>;
    executeTool: typeof apiExecuteTool;
    reportUsage: typeof apiReportUsage;
  };
  bus: () => BusChannel | null;
  now: () => number;
};

export function defaultVoiceDeps(): VoiceDeps {
  return {
    supported: voiceSupported(),
    getMic: requestMic,
    createCall: (onEvent, onClose) => {
      const audioEl = document.createElement("audio");
      audioEl.autoplay = true;
      audioEl.hidden = true;
      document.body.appendChild(audioEl);
      return new VoiceSession(browserDeps(audioEl), onEvent, (reason) => {
        audioEl.remove();
        onClose(reason);
      });
    },
    api: {
      createVoiceSession: apiCreateSession,
      executeTool: apiExecuteTool,
      reportUsage: apiReportUsage,
    },
    bus: () =>
      typeof BroadcastChannel === "function"
        ? (new BroadcastChannel("celestin.voice") as unknown as BusChannel)
        : null,
    now: () => Date.now(),
  };
}

export type VoiceControls = {
  phase: VoicePhase;
  muted: boolean;
  /** Epoch ms at which the cap ends the session; null while off. */
  capAt: number | null;
  supported: boolean;
  start: () => Promise<void>;
  stop: () => void;
  toggleMute: () => void;
  sendText: (text: string) => void;
};

/** The sentence for a failed start (design §5). */
function startFailureMessage(error: unknown): string {
  if (error instanceof VoiceRequestError) return error.message;
  if (error instanceof VoiceSessionError) return VOICE_CONNECT_FAILED();
  return genericError();
}

export function useVoiceSession(
  tutor: TutorSessionHandle,
  opts: { enabled: boolean; scope: LessonScope; deps?: VoiceDeps },
): VoiceControls {
  const [deps] = useState(() => opts.deps ?? defaultVoiceDeps());
  const { scope } = opts;
  const said = useLearnerSentences();
  const supported = opts.enabled && deps.supported;

  const [phase, setPhaseState] = useState<VoicePhase>("off");
  const [muted, setMuted] = useState(false);
  const [capAt, setCapAt] = useState<number | null>(null);

  const phaseRef = useRef<VoicePhase>("off");
  const callRef = useRef<CallHandle | null>(null);
  const infoRef = useRef<VoiceSessionInfo | null>(null);
  const bridgeRef = useRef(initialBridgeState());
  const usageRef = useRef<VoiceUsage>(EMPTY_USAGE);
  const responsesRef = useRef(0);
  const startedAtRef = useRef(0);
  const queueRef = useRef<Promise<void>>(Promise.resolve());
  const busRef = useRef<BusChannel | null>(null);
  const capTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const graceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const capPendingRef = useRef(false);

  const setPhase = useCallback((next: VoicePhase) => {
    phaseRef.current = next;
    setPhaseState(next);
  }, []);

  const clearTimers = useCallback(() => {
    for (const ref of [capTimer, graceTimer, idleTimer]) {
      if (ref.current !== null) clearTimeout(ref.current);
      ref.current = null;
    }
  }, []);

  const closeBus = useCallback(() => {
    busRef.current?.close();
    busRef.current = null;
  }, []);

  const send = useCallback((event: RealtimeClientEvent) => {
    const call = callRef.current;
    if (!call?.open) return;
    try {
      call.send(event);
    } catch {
      // The channel died between the check and the send; onClose handles it.
    }
  }, []);

  /** Ends the session for any reason. Idempotent; the only way out. */
  const stop = useCallback(
    (reason: VoiceEndReason, opts: { beacon?: boolean } = {}) => {
      if (phaseRef.current === "off") return;
      clearTimers();
      const info = infoRef.current;
      const call = callRef.current;
      callRef.current = null;
      infoRef.current = null;
      setPhase("off");
      setCapAt(null);
      setMuted(false);
      call?.close();
      busRef.current?.postMessage({ type: "stop" });
      closeBus();
      if (info) {
        const durationS = Math.max(0, Math.round((deps.now() - startedAtRef.current) / 1000));
        deps.api.reportUsage(
          {
            session_id: info.sessionId,
            reason,
            duration_s: Math.min(durationS, 7200),
            responses: responsesRef.current,
            usage: usageRef.current,
          },
          opts,
        );
      }
      tutor.dispatch({ event: "voice.off", reason });
    },
    [clearTimers, closeBus, deps, setPhase, tutor],
  );

  const resetIdle = useCallback(() => {
    const info = infoRef.current;
    if (!info) return;
    if (idleTimer.current !== null) clearTimeout(idleTimer.current);
    idleTimer.current = setTimeout(() => stop("idle"), info.limits.idleS * 1000);
  }, [stop]);

  /** One batch of tool calls from one response, executed serially, then one
   *  `response.create` so the model continues the same turn (design 3.12). */
  const runTools = useCallback(
    async (calls: ToolCall[]) => {
      const info = infoRef.current;
      if (!info) return;
      for (const call of calls) {
        if (!callRef.current?.open) return;
        try {
          const result = await deps.api.executeTool(info.sessionId, call, scope);
          if (result.event) tutor.dispatch(result.event);
          if (result.stateText) send(systemTextItem(result.stateText));
          send(functionOutputItem(call.callId, result.output));
        } catch (error) {
          send(
            functionOutputItem(
              call.callId,
              JSON.stringify({ ok: false, error: said.voiceToolFailed }),
            ),
          );
          tutor.dispatch({
            event: "error",
            code: error instanceof VoiceRequestError ? error.code : "voice_tool",
            message: VOICE_TOOL_FAILED_ENTRY(),
          });
        }
      }
      if (!callRef.current?.open) return;
      send(RESPONSE_CREATE);
      if (phaseRef.current === "working") setPhase("listening");
    },
    [deps, said.voiceToolFailed, scope, send, setPhase, tutor],
  );

  const handleActions = useCallback(
    (actions: BridgeAction[]) => {
      const calls: ToolCall[] = [];
      for (const action of actions) {
        switch (action.kind) {
          case "tool.call":
            calls.push(action.call);
            break;
          case "learner.spoken":
            tutor.appendLearner(action.text, true);
            resetIdle();
            break;
          case "interrupted":
            tutor.markInterrupted();
            resetIdle();
            break;
          case "speaking":
            if (phaseRef.current === "speaking" || phaseRef.current === "listening") {
              setPhase(action.on ? "speaking" : "listening");
            }
            break;
          case "usage":
            usageRef.current = sumUsage(usageRef.current, action.usage);
            break;
          case "error":
            console.warn("realtime error", action.code, action.message);
            tutor.dispatch({
              event: "error",
              code: "voice_realtime",
              message: VOICE_REALTIME_ERROR(),
            });
            break;
        }
      }
      if (calls.length > 0) {
        setPhase("working");
        queueRef.current = queueRef.current.then(() => runTools(calls)).catch(() => {});
      }
    },
    [resetIdle, runTools, setPhase, tutor],
  );

  /**
   * A spoken turn reaches the browser and never the server (007 deviation D1), so
   * in a discussion the browser reports what was said. Only what this call added
   * is sent: everything before it is already stored, and re-reporting it would
   * append the whole thread a second time. A failure is silent, because the
   * learner has already heard the answer and a lost report costs only the thread.
   */
  const reportedRef = useRef(0);
  const reportSpokenTurn = useCallback(() => {
    if (!scope.conversationId) return;
    const { history } = tutor.snapshot();
    const added = history.slice(reportedRef.current);
    reportedRef.current = history.length;
    void recordVoiceTurn(scope, added).catch(() => {});
  }, [scope, tutor]);

  const onEvent = useCallback(
    (ev: RealtimeServerEvent) => {
      if (phaseRef.current === "off") return;
      if (ev.type === "response.done") responsesRef.current += 1;
      if (ev.type === "response.created" || ev.type === "input_audio_buffer.speech_started") {
        resetIdle();
      }
      const out = bridge(bridgeRef.current, ev);
      bridgeRef.current = out.state;
      for (const event of out.events) tutor.dispatch(event);
      handleActions(out.actions);
      if (out.events.some((e) => e.event === "turn.end")) {
        reportSpokenTurn();
        // The cap fired mid-turn: the turn just ended, so stop now.
        if (capPendingRef.current) {
          capPendingRef.current = false;
          stop("cap");
        }
      }
    },
    [handleActions, reportSpokenTurn, resetIdle, stop, tutor],
  );

  const onClose = useCallback(
    (reason: CloseReason) => {
      if (reason !== "local") stop("error");
    },
    [stop],
  );

  const startTimers = useCallback(
    (info: VoiceSessionInfo) => {
      const capMs = info.limits.maxSessionS * 1000;
      setCapAt(startedAtRef.current + capMs);
      capTimer.current = setTimeout(() => {
        if (bridgeRef.current.inTurn) {
          capPendingRef.current = true;
          graceTimer.current = setTimeout(() => stop("cap"), CAP_GRACE_MS);
        } else {
          stop("cap");
        }
      }, capMs);
      resetIdle();
    },
    [resetIdle, stop],
  );

  /** True when another tab already holds a session. Keeps the bus open only
   *  when the answer is no, so `stop` can announce the end. */
  const probeOtherTabs = useCallback(async (): Promise<boolean> => {
    const bus = deps.bus();
    if (!bus) return false;
    const busy = await new Promise<boolean>((resolve) => {
      let seen = false;
      bus.onmessage = (e) => {
        if (e.data.type === "busy") seen = true;
        if (e.data.type === "probe") bus.postMessage({ type: "busy" });
      };
      bus.postMessage({ type: "probe" });
      setTimeout(() => resolve(seen), PROBE_MS);
    });
    if (busy) bus.close();
    else busRef.current = bus;
    return busy;
  }, [deps]);

  const start = useCallback(async () => {
    if (phaseRef.current !== "off" || !supported) return;
    setPhase("connecting");
    const abandon = (code: string, message: string, mic?: MediaStream) => {
      for (const track of mic?.getTracks() ?? []) track.stop();
      closeBus();
      infoRef.current = null;
      setPhase("off");
      tutor.dispatch({ event: "error", code, message });
    };

    let mic: MediaStream;
    let busy: boolean;
    try {
      [mic, busy] = await Promise.all([deps.getMic(), probeOtherTabs()]);
    } catch {
      abandon("voice_mic", VOICE_MIC_DENIED());
      return;
    }
    if (busy) {
      abandon("voice_busy", VOICE_BUSY_ELSEWHERE(), mic);
      return;
    }

    const call = deps.createCall(onEvent, onClose);
    let info: VoiceSessionInfo;
    try {
      info = await deps.api.createVoiceSession(scope, tutor.snapshot().history);
      infoRef.current = info;
      await call.connect(info.secret, mic, info.callsUrl);
    } catch (error) {
      call.close();
      abandon("voice_connect", startFailureMessage(error), mic);
      return;
    }

    callRef.current = call;
    bridgeRef.current = initialBridgeState();
    usageRef.current = EMPTY_USAGE;
    responsesRef.current = 0;
    startedAtRef.current = deps.now();
    capPendingRef.current = false;
    // Everything said before the call is already stored, so a spoken turn reports
    // only what this call adds from here on (007 deviation D1).
    reportedRef.current = tutor.snapshot().history.length;
    tutor.dispatch({ event: "voice.on" });
    setPhase("listening");
    for (const item of info.seed) send(seedItem(item));
    if (info.opening) send(RESPONSE_CREATE);
    startTimers(info);
  }, [
    closeBus,
    deps,
    onClose,
    onEvent,
    probeOtherTabs,
    scope,
    send,
    setPhase,
    startTimers,
    supported,
    tutor,
  ]);

  const toggleMute = useCallback(() => {
    if (!callRef.current) return;
    setMuted((prev) => {
      callRef.current?.setMuted(!prev);
      return !prev;
    });
  }, []);

  const sendText = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || !callRef.current?.open) return;
      tutor.appendLearner(trimmed);
      if (bridgeRef.current.inTurn) send({ type: "response.cancel" });
      send(userTextItem(trimmed));
      send(RESPONSE_CREATE);
      resetIdle();
    },
    [resetIdle, send, tutor],
  );

  const stopByLearner = useCallback(() => stop("learner"), [stop]);

  // Page unload and unmount both end the session; the beacon survives the page.
  useEffect(() => {
    const onHide = () => stop("unload", { beacon: true });
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("pagehide", onHide);
      stop("unload", { beacon: true });
    };
  }, [stop]);

  return useMemo(
    () => ({ phase, muted, capAt, supported, start, stop: stopByLearner, toggleMute, sendText }),
    [phase, muted, capAt, supported, start, stopByLearner, toggleMute, sendText],
  );
}
