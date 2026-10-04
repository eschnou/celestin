/** Builders for the AI settings view the server sends (spec 014 §3.8), so tests say only what they change. */

import type {
  AiSettingsView,
  ConnectionView,
  Effort,
  Field,
  KeyView,
  ModelRole,
  RoleView,
  Source,
} from "@/lib/admin";

export const OPENAI = "https://api.openai.com/v1";
export const GROQ = "https://api.groq.com/openai/v1";

export const field = <T>(value: T, source: Source = "default"): Field<T> => ({ value, source });
export const NO_KEY: KeyView = { source: "none", last4: null, unreadable: false };
export const stored = (last4: string): KeyView => ({ source: "stored", last4, unreadable: false });
export const envKey = (last4: string): KeyView => ({
  source: "environment",
  last4,
  unreadable: false,
});

export function connection(over: Partial<ConnectionView> = {}): ConnectionView {
  return {
    base_url: field(OPENAI),
    api_style: field("responses"),
    structured: field("schema"),
    key: NO_KEY,
    ...over,
  };
}

export function role(model: string, over: Partial<RoleView> = {}): RoleView {
  return {
    model: field<string | null>(model),
    reasoning_effort: field<Effort | null>(null),
    voice_transcription_model: null,
    own_connection: null,
    uses_default: true,
    resolved: false,
    ...over,
  };
}

/** A fresh instance: OpenAI, no key, today's default models. */
export function freshView(over: Partial<AiSettingsView> = {}): AiSettingsView {
  const roles: Record<ModelRole, RoleView> = {
    tutor: role("gpt-6.1-sol"),
    authoring: role("gpt-6.1-sol", { reasoning_effort: field<Effort | null>("medium") }),
    transcription: role("gpt-6.1-sol", { reasoning_effort: field<Effort | null>("low") }),
    voice: role("gpt-realtime-2.1", {
      reasoning_effort: field<Effort | null>("low"),
      voice_transcription_model: field<string | null>("gpt-4o-mini-transcribe"),
    }),
  };
  return {
    can_store: true,
    configured: false,
    voice_available: false,
    default: connection(),
    roles,
    ...over,
  };
}

/** A configured instance on Groq: stored address, key and models. */
export function groqView(over: Partial<AiSettingsView> = {}): AiSettingsView {
  const fresh = freshView();
  const s = (v: string) => field<string | null>(v, "stored");
  return {
    ...fresh,
    configured: true,
    default: connection({ base_url: field(GROQ, "stored"), key: stored("abcd") }),
    roles: {
      tutor: role("qwen/qwen3.8-27b", { model: s("qwen/qwen3.8-27b"), resolved: true }),
      authoring: role("openai/gpt-oss-120b", {
        model: s("openai/gpt-oss-120b"),
        reasoning_effort: field<Effort | null>("low", "stored"),
        resolved: true,
      }),
      transcription: role("qwen/qwen3.8-27b", { model: s("qwen/qwen3.8-27b"), resolved: true }),
      voice: fresh.roles.voice,
    },
    ...over,
  };
}
