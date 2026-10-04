/**
 * Realtime server events → the tutor event vocabulary (003 design 3.11).
 *
 * Pure, so a whole spoken session can be replayed from a fixture. The one rule
 * that matters: a Realtime response we caused by answering a function call is
 * the *same* tutor turn as the response that made the call, exactly like a
 * tool round in the text loop. So `turn.start` is suppressed for it and the
 * text block id increments instead.
 */

import { genericError } from "../client";
import type { TutorEvent } from "../types";
import type { RealtimeServerEvent, RealtimeUsage } from "./realtime";
import { EMPTY_USAGE, type ToolCall, type VoiceUsage } from "./types";

export type BridgeState = {
  inTurn: boolean;
  continuing: boolean;
  speaking: boolean;
  blockId: number;
  pendingCalls: ToolCall[];
};

export type BridgeAction =
  | { kind: "tool.call"; call: ToolCall }
  | { kind: "learner.spoken"; text: string }
  | { kind: "usage"; usage: VoiceUsage }
  | { kind: "interrupted" }
  | { kind: "speaking"; on: boolean }
  | { kind: "error"; code: string; message: string };

export type BridgeResult = { state: BridgeState; events: TutorEvent[]; actions: BridgeAction[] };

/** Realtime errors that are consequences of ordinary racing (a response was
 *  already active, a cancel arrived late), not failures worth an entry. */
const BENIGN_ERROR_CODES = new Set([
  "conversation_already_has_active_response",
  "response_cancel_not_active",
  "input_audio_buffer_commit_empty",
]);

export function initialBridgeState(): BridgeState {
  return { inTurn: false, continuing: false, speaking: false, blockId: 0, pendingCalls: [] };
}

export function bridge(state: BridgeState, ev: RealtimeServerEvent): BridgeResult {
  const events: TutorEvent[] = [];
  const actions: BridgeAction[] = [];
  let next = state;

  switch (ev.type) {
    case "response.created":
      if (state.continuing) {
        next = { ...state, continuing: false, pendingCalls: [] };
      } else {
        next = { ...state, inTurn: true, blockId: 0, pendingCalls: [] };
        events.push({ event: "turn.start", turn_id: ev.response.id });
      }
      break;

    case "response.output_audio_transcript.delta":
      events.push({ event: "text.delta", block_id: state.blockId, text: ev.delta });
      break;

    case "response.output_item.done":
      if (ev.item.type === "function_call" && ev.item.name) {
        next = {
          ...state,
          pendingCalls: [
            ...state.pendingCalls,
            {
              callId: ev.item.call_id ?? ev.item.id,
              name: ev.item.name,
              arguments: ev.item.arguments ?? "",
            },
          ],
        };
      }
      break;

    case "response.done": {
      if (ev.response.usage) actions.push({ kind: "usage", usage: usageOf(ev.response.usage) });
      if (state.pendingCalls.length > 0) {
        for (const call of state.pendingCalls) actions.push({ kind: "tool.call", call });
        next = { ...state, continuing: true, blockId: state.blockId + 1, pendingCalls: [] };
        break;
      }
      if (ev.response.status === "failed") {
        events.push({ event: "error", code: "voice_response_failed", message: genericError() });
      }
      events.push({
        event: "turn.end",
        reason: ev.response.status === "cancelled" ? "cancelled" : "end",
        usage: {},
      });
      next = { ...state, inTurn: false, continuing: false, pendingCalls: [] };
      break;
    }

    case "conversation.item.input_audio_transcription.completed": {
      const text = ev.transcript.trim();
      if (text) actions.push({ kind: "learner.spoken", text });
      if (ev.usage) actions.push({ kind: "usage", usage: usageOf(ev.usage) });
      break;
    }

    case "input_audio_buffer.speech_started":
      if (state.inTurn || state.speaking) actions.push({ kind: "interrupted" });
      break;

    case "output_audio_buffer.started":
      next = { ...state, speaking: true };
      actions.push({ kind: "speaking", on: true });
      break;

    case "output_audio_buffer.stopped":
    case "output_audio_buffer.cleared":
      next = { ...state, speaking: false };
      actions.push({ kind: "speaking", on: false });
      break;

    case "error": {
      const code = ev.error.code ?? "";
      if (!BENIGN_ERROR_CODES.has(code)) {
        actions.push({ kind: "error", code, message: ev.error.message ?? "realtime error" });
      }
      break;
    }

    default:
      break;
  }
  return { state: next, events, actions };
}

/** Token counts by modality from one `response.done` (design 4.5). */
export function usageOf(usage: RealtimeUsage): VoiceUsage {
  const input = usage.input_token_details ?? {};
  const cached = input.cached_tokens_details ?? {};
  const output = usage.output_token_details ?? {};
  return {
    input_text: input.text_tokens ?? 0,
    input_audio: input.audio_tokens ?? 0,
    cached_text: cached.text_tokens ?? 0,
    cached_audio: cached.audio_tokens ?? 0,
    output_text: output.text_tokens ?? 0,
    output_audio: output.audio_tokens ?? 0,
  };
}

export function sumUsage(total: VoiceUsage, part: VoiceUsage): VoiceUsage {
  const out = { ...EMPTY_USAGE };
  for (const key of Object.keys(out) as (keyof VoiceUsage)[]) out[key] = total[key] + part[key];
  return out;
}
