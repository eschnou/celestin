/** Voice-mode types (003 design 3.9). The wire DTOs mirror `app/api/schemas/voice.py`. */

import type { Progress, TutorEvent } from "../types";

export type VoicePhase = "off" | "connecting" | "listening" | "speaking" | "working";
export type VoiceEndReason = "learner" | "cap" | "idle" | "error" | "unload";

/** A Realtime conversation item as the backend seeds it; opaque to the browser. */
export type RealtimeItem = Record<string, unknown>;

export type VoiceSessionInfo = {
  sessionId: string;
  secret: string;
  /** Where to post the SDP offer: the voice server's `…/realtime/calls`. */
  callsUrl: string;
  expiresAt: number;
  model: string;
  voice: string;
  limits: { maxSessionS: number; idleS: number };
  seed: RealtimeItem[];
  opening: boolean;
};

export type ToolCall = { callId: string; name: string; arguments: string };

export type ToolResult = {
  output: string;
  event: TutorEvent | null;
  progress: Progress;
  stateText?: string;
};

export type VoiceUsage = {
  input_text: number;
  input_audio: number;
  cached_text: number;
  cached_audio: number;
  output_text: number;
  output_audio: number;
};

export const EMPTY_USAGE: VoiceUsage = {
  input_text: 0,
  input_audio: 0,
  cached_text: 0,
  cached_audio: 0,
  output_text: 0,
  output_audio: 0,
};

export type VoiceUsageReport = {
  session_id: string;
  reason: VoiceEndReason;
  duration_s: number;
  responses: number;
  usage: VoiceUsage;
};
