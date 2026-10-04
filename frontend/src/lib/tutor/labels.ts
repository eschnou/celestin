/** Labels for curriculum vocabulary and the voice session that the interface shows, in the
 *  interface language. What the learner "says" to the model lives in `prompts.ts`. */

import { m } from "@/paraglide/messages";
import type { SectionKind, SectionState } from "./types";
import type { VoiceEndReason, VoicePhase } from "./voice/types";

type TextStatus = "idle" | "streaming" | "error";

/** The three kinds of section, in the order the editors offer them. */
export const SECTION_KINDS = [
  "teach",
  "practise",
  "synthesis",
] as const satisfies readonly SectionKind[];

/** Message functions, not strings: the language is read when a label is shown (`KIND_LABEL[kind]()`). */
export const KIND_LABEL: Record<SectionKind, () => string> = {
  teach: m.lesson_kind_teach,
  practise: m.lesson_kind_practise,
  synthesis: m.lesson_kind_synthesis,
};

export const STATE_LABEL: Record<SectionState, () => string> = {
  done: m.lesson_state_done,
  active: m.lesson_state_active,
  available: m.lesson_state_available,
  locked: m.lesson_state_locked,
};

/** Transcript markers for a voice session. Interface text: they label the transcript and
 *  never enter the history the model reads. Message functions, called when the event is
 *  applied. */
export const VOICE_ON_MARKER: () => string = m.voice_marker_on;
export const VOICE_OFF_MARKER: Record<VoiceEndReason, () => string> = {
  learner: m.voice_marker_off_learner,
  cap: m.voice_marker_off_cap,
  idle: m.voice_marker_off_idle,
  error: m.voice_marker_off_error,
  unload: m.voice_marker_off_learner,
};

export const VOICE_PHASE_LABEL: Record<Exclude<VoicePhase, "off">, () => string> = {
  connecting: m.voice_phase_connecting,
  listening: m.voice_phase_listening,
  speaking: m.voice_phase_speaking,
  working: m.voice_phase_working,
};
export const VOICE_MUTED_LABEL: () => string = m.voice_muted;

export const VOICE_MIC_DENIED: () => string = m.voice_mic_denied;
export const VOICE_CONNECT_FAILED: () => string = m.voice_connect_failed;
export const VOICE_BUSY_ELSEWHERE: () => string = m.voice_busy_elsewhere;
export const VOICE_TOOL_FAILED_ENTRY: () => string = m.voice_tool_failed_entry;
export const VOICE_REALTIME_ERROR: () => string = m.voice_realtime_error;

/** The tutor header line: the voice phase while a session is open, else the text status. */
export function statusLabel(
  status: TextStatus,
  voice: { phase: VoicePhase; muted: boolean },
): string {
  if (voice.phase !== "off") {
    return voice.muted && voice.phase === "listening"
      ? VOICE_MUTED_LABEL()
      : VOICE_PHASE_LABEL[voice.phase]();
  }
  return status === "streaming"
    ? m.lesson_status_streaming()
    : status === "error"
      ? m.lesson_status_error()
      : m.lesson_status_idle();
}
