import { describe, expect, it } from "vitest";
import { isOpenAIAddress, OPENAI_BASE_URL, PRESETS, presetById, presetOf } from "../ai-presets";

describe("the provider presets", () => {
  it("has the five providers, custom last", () => {
    expect(PRESETS.map((p) => p.id)).toEqual(["openai", "groq", "openrouter", "ollama", "custom"]);
    expect(presetById("custom").baseUrl).toBe("");
  });

  it("knows each preset by its address, with or without a trailing slash", () => {
    for (const p of PRESETS.filter((p) => p.id !== "custom")) {
      expect(presetOf(p.baseUrl)).toBe(p.id);
      expect(presetOf(`${p.baseUrl}/`)).toBe(p.id);
    }
    expect(presetOf("https://gpu.example/v1")).toBe("custom");
    expect(presetOf(null)).toBe("custom");
    expect(presetOf("")).toBe("custom");
  });

  it("every address is a usable base URL", () => {
    for (const p of PRESETS.filter((p) => p.id !== "custom")) {
      const url = new URL(p.baseUrl);
      expect(["http:", "https:"]).toContain(url.protocol);
      expect(p.baseUrl.endsWith("/")).toBe(false);
    }
  });

  it("recognises OpenAI's address only", () => {
    expect(isOpenAIAddress(OPENAI_BASE_URL)).toBe(true);
    expect(isOpenAIAddress(`${OPENAI_BASE_URL}/`)).toBe(true);
    expect(isOpenAIAddress("https://api.groq.com/openai/v1")).toBe(false);
  });

  it("suggests a voice model only for OpenAI", () => {
    expect(presetById("openai").models.voice).toBe("gpt-realtime-2.1");
    for (const id of ["groq", "openrouter", "ollama", "custom"] as const) {
      expect(presetById(id).models.voice).toBeUndefined();
    }
  });

  it("gives key links where the provider has accounts", () => {
    expect(presetById("openai").keyUrl).toMatch(/^https:\/\//);
    expect(presetById("ollama").keyUrl).toBeNull();
  });
});
