/** Providers the settings screen can fill in with one click (spec 014 R1.6). A preset is a convenience: only
 *  the values it fills in are stored. The suggestions are data, easy to update, never required. */

import type { ApiStyle, ModelRole } from "./admin";

export type PresetId = "openai" | "groq" | "openrouter" | "ollama" | "custom";

export type Preset = {
  id: PresetId;
  /** A brand name, the same in both languages; `null` for « custom », which the screen words. */
  name: string | null;
  baseUrl: string;
  apiStyle: ApiStyle;
  /** Where to create a key, for a provider that has accounts. */
  keyUrl: string | null;
  /** Suggested model per role. A role missing here has no suggestion. */
  models: Partial<Record<ModelRole, string>>;
};

export const OPENAI_BASE_URL = "https://api.openai.com/v1";

export const PRESETS: Preset[] = [
  {
    id: "openai",
    name: "OpenAI",
    baseUrl: OPENAI_BASE_URL,
    apiStyle: "responses",
    keyUrl: "https://platform.openai.com/api-keys",
    models: {
      tutor: "gpt-6.1-sol",
      authoring: "gpt-6.1-sol",
      transcription: "gpt-6.1-sol",
      voice: "gpt-realtime-2.1",
    },
  },
  {
    id: "groq",
    name: "Groq",
    baseUrl: "https://api.groq.com/openai/v1",
    apiStyle: "responses",
    keyUrl: "https://console.groq.com/keys",
    // What the Test button's live check found on Groq (documentation/ai-providers.md): Qwen 3.8 teaches and
    // reads images, gpt-oss prepares chapters well but cannot call the board's tool. Suggestions, not rules.
    models: {
      tutor: "qwen/qwen3.8-27b",
      authoring: "openai/gpt-oss-120b",
      transcription: "qwen/qwen3.8-27b",
    },
  },
  {
    id: "openrouter",
    name: "OpenRouter",
    baseUrl: "https://openrouter.ai/api/v1",
    apiStyle: "responses",
    keyUrl: "https://openrouter.ai/keys",
    models: {},
  },
  {
    id: "ollama",
    name: "Ollama",
    baseUrl: "http://localhost:11434/v1",
    apiStyle: "chat",
    keyUrl: null,
    models: {},
  },
  { id: "custom", name: null, baseUrl: "", apiStyle: "responses", keyUrl: null, models: {} },
];

export function presetById(id: PresetId): Preset {
  return PRESETS.find((p) => p.id === id) ?? PRESETS[PRESETS.length - 1]!;
}

/** Two addresses are the same when they differ only by spaces or a trailing slash (the server stores them so). */
export const sameAddress = (a: string, b: string) =>
  a.trim().replace(/\/+$/, "") === b.trim().replace(/\/+$/, "");

/** The preset an address belongs to; `custom` for any other. */
export function presetOf(baseUrl: string | null): PresetId {
  const found = PRESETS.find((p) => p.baseUrl !== "" && sameAddress(baseUrl ?? "", p.baseUrl));
  return found ? found.id : "custom";
}

/** Whether an address is OpenAI's own (its models are known, a key is required): the same host test the
 *  server makes, so the form and the resolver agree. */
export function isOpenAIAddress(baseUrl: string): boolean {
  try {
    return new URL(baseUrl.trim()).hostname === new URL(OPENAI_BASE_URL).hostname;
  } catch {
    return false;
  }
}
