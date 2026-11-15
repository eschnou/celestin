/** HTTP side of voice mode: the three `/api/voice` routes (003 design 3.1), and the report
 *  of a turn the server did not see to its end to the mode's own route (007 D1, 018 D7). */

import { ApiError, sendJson } from "../client";
import { VOICE_TURN_URL } from "../discussion";
import { SEANCE_REPORT_URL } from "../seance";
import type { HistoryEntry, LessonScope, Progress, TutorEvent } from "../types";
import type { ToolCall, ToolResult, VoiceSessionInfo, VoiceUsageReport } from "./types";

export const SESSION_URL = "/api/voice/session";
export const TOOL_URL = "/api/voice/tool";
export const USAGE_URL = "/api/voice/usage";

export { ApiError as VoiceRequestError };

type SessionWire = {
  session_id: string;
  secret: string;
  calls_url: string;
  expires_at: number;
  model: string;
  voice: string;
  limits: { max_session_s: number; idle_s: number };
  seed: Record<string, unknown>[];
  opening: boolean;
};

/** No transcript in any mode: the server seeds the call from what it has stored, the live
 *  séance for the parcours (018) and the conversation for a discussion (007). */
export async function createVoiceSession(
  scope: LessonScope,
  signal?: AbortSignal,
): Promise<VoiceSessionInfo> {
  const wire = (await (
    await sendJson(
      SESSION_URL,
      {
        course_id: scope.courseId,
        chapter_id: scope.chapterId,
        mode: scope.mode,
        conversation_id: scope.conversationId,
      },
      signal ? { signal } : {},
    )
  ).json()) as SessionWire;
  return {
    sessionId: wire.session_id,
    secret: wire.secret,
    callsUrl: wire.calls_url,
    expiresAt: wire.expires_at,
    model: wire.model,
    voice: wire.voice,
    limits: { maxSessionS: wire.limits.max_session_s, idleS: wire.limits.idle_s },
    seed: wire.seed,
    opening: wire.opening,
  };
}

type ToolWire = {
  output: string;
  event: TutorEvent | null;
  progress: Progress;
  state_text?: string | null;
};

export async function executeTool(
  sessionId: string,
  call: ToolCall,
  scope: LessonScope,
): Promise<ToolResult> {
  const wire = (await (
    await sendJson(TOOL_URL, {
      session_id: sessionId,
      call_id: call.callId,
      name: call.name,
      arguments: call.arguments,
      course_id: scope.courseId,
      chapter_id: scope.chapterId,
      mode: scope.mode,
    })
  ).json()) as ToolWire;
  const result: ToolResult = { output: wire.output, event: wire.event, progress: wire.progress };
  if (wire.state_text) result.stateText = wire.state_text;
  return result;
}

/** Fire and forget. `beacon` survives page unload; the route never fails the caller. */
export function reportUsage(report: VoiceUsageReport, opts: { beacon?: boolean } = {}): void {
  const body = JSON.stringify(report);
  if (
    opts.beacon &&
    typeof navigator !== "undefined" &&
    typeof navigator.sendBeacon === "function"
  ) {
    navigator.sendBeacon(USAGE_URL, new Blob([body], { type: "text/plain" }));
    return;
  }
  void fetch(USAGE_URL, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
    keepalive: true,
  }).catch(() => {});
}

/**
 * A turn the browser reports, because the server did not see it to its end: a spoken one
 * (007 deviation D1: the model's speech reaches the browser over WebRTC and never the
 * server), or, in the parcours, a text turn the learner stopped (018 D7: what she kept of
 * it). One code path for both; only the route differs, a discussion naming its conversation
 * and the parcours its chapter (the server files the entries into the live séance with its
 * split rule). Rejects on a refusal: each caller decides what a lost report costs.
 */
export async function reportTurn(scope: LessonScope, entries: HistoryEntry[]): Promise<void> {
  if (entries.length === 0) return;
  const discussion = scope.mode === "discussion";
  if (discussion && !scope.conversationId) return;
  await sendJson(discussion ? VOICE_TURN_URL : SEANCE_REPORT_URL, {
    course_id: scope.courseId,
    chapter_id: scope.chapterId,
    ...(discussion ? { conversation_id: scope.conversationId } : {}),
    entries,
  });
}
