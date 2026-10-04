/** HTTP side of voice mode: the three `/api/voice` routes (003 design 3.1). */

import { ApiError, sendJson } from "../client";
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

export async function createVoiceSession(
  scope: LessonScope,
  history: HistoryEntry[],
  signal?: AbortSignal,
): Promise<VoiceSessionInfo> {
  const wire = (await (
    await sendJson(
      SESSION_URL,
      {
        course_id: scope.courseId,
        chapter_id: scope.chapterId,
        history,
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
