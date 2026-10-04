/**
 * The subset of Realtime API events the bridge reads and the session sends.
 * Anything else is ignored on the way in and never produced on the way out.
 */

export type RealtimeUsage = {
  input_tokens?: number;
  output_tokens?: number;
  input_token_details?: {
    text_tokens?: number;
    audio_tokens?: number;
    cached_tokens?: number;
    cached_tokens_details?: { text_tokens?: number; audio_tokens?: number };
  };
  output_token_details?: { text_tokens?: number; audio_tokens?: number };
};

export type RealtimeOutputItem = {
  id: string;
  type: "message" | "function_call" | string;
  name?: string;
  call_id?: string;
  arguments?: string;
  status?: string;
};

export type RealtimeServerEvent =
  | { type: "session.created"; session?: Record<string, unknown> }
  | { type: "session.updated"; session?: Record<string, unknown> }
  | { type: "input_audio_buffer.speech_started"; item_id?: string }
  | { type: "input_audio_buffer.speech_stopped"; item_id?: string }
  | {
      type: "conversation.item.input_audio_transcription.completed";
      item_id: string;
      transcript: string;
      usage?: RealtimeUsage;
    }
  | { type: "response.created"; response: { id: string; status?: string } }
  | { type: "response.output_item.added"; response_id?: string; item: RealtimeOutputItem }
  | {
      type: "response.output_audio_transcript.delta";
      response_id?: string;
      item_id: string;
      delta: string;
    }
  | { type: "response.output_item.done"; response_id?: string; item: RealtimeOutputItem }
  | {
      type: "response.done";
      response: {
        id: string;
        status: "completed" | "cancelled" | "failed" | "incomplete" | string;
        status_details?: { type?: string; reason?: string; error?: { message?: string } };
        usage?: RealtimeUsage;
      };
    }
  | { type: "output_audio_buffer.started"; response_id?: string }
  | { type: "output_audio_buffer.stopped"; response_id?: string }
  | { type: "output_audio_buffer.cleared"; response_id?: string }
  | { type: "error"; error: { type?: string; code?: string; message?: string } };

const KNOWN_TYPES = [
  "session.created",
  "session.updated",
  "input_audio_buffer.speech_started",
  "input_audio_buffer.speech_stopped",
  "conversation.item.input_audio_transcription.completed",
  "response.created",
  "response.output_item.added",
  "response.output_audio_transcript.delta",
  "response.output_item.done",
  "response.done",
  "output_audio_buffer.started",
  "output_audio_buffer.stopped",
  "output_audio_buffer.cleared",
  "error",
] as const satisfies readonly RealtimeServerEvent["type"][];

const KNOWN = new Set<string>(KNOWN_TYPES);

/** `null` for malformed JSON and for event types the bridge does not read. */
export function parseServerEvent(json: string): RealtimeServerEvent | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object") return null;
  const type = (parsed as { type?: unknown }).type;
  if (typeof type !== "string" || !KNOWN.has(type)) return null;
  return parsed as RealtimeServerEvent;
}

export type ItemCreateEvent = { type: "conversation.item.create"; item: Record<string, unknown> };

export type RealtimeClientEvent =
  | ItemCreateEvent
  | { type: "response.create"; response?: Record<string, unknown> }
  | { type: "response.cancel" };

export const userTextItem = (text: string): ItemCreateEvent => ({
  type: "conversation.item.create",
  item: { type: "message", role: "user", content: [{ type: "input_text", text }] },
});

export const systemTextItem = (text: string): ItemCreateEvent => ({
  type: "conversation.item.create",
  item: { type: "message", role: "system", content: [{ type: "input_text", text }] },
});

export const functionOutputItem = (callId: string, output: string): ItemCreateEvent => ({
  type: "conversation.item.create",
  item: { type: "function_call_output", call_id: callId, output },
});

export const seedItem = (item: Record<string, unknown>): ItemCreateEvent => ({
  type: "conversation.item.create",
  item,
});

export const RESPONSE_CREATE: RealtimeClientEvent = { type: "response.create" };
