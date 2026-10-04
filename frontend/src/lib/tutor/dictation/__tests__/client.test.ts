import { afterEach, describe, expect, it, vi } from "vitest";
import { recordingName, transcribe } from "../client";

afterEach(() => vi.unstubAllGlobals());

describe("recordingName", () => {
  it.each([
    ["audio/webm;codecs=opus", "dictation.webm"],
    ["audio/mp4", "dictation.mp4"],
    ["audio/x-m4a", "dictation.mp4"],
    ["audio/ogg;codecs=opus", "dictation.ogg"],
    ["", "dictation.webm"],
  ])("%s → %s", (type, name) => expect(recordingName(type)).toBe(name));
});

describe("transcribe", () => {
  it("posts the recording with the course's language and its length, and returns the text", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({
      ok: true,
      status: 200,
      json: async () => ({ text: "  la somme de deux entiers  " }),
    }));
    vi.stubGlobal("fetch", fetchMock);
    const text = await transcribe(new Blob(["a"], { type: "audio/mp4" }), {
      language: "en",
      durationMs: 4200.4,
    });
    expect(text).toBe("la somme de deux entiers");
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/dictation");
    expect(init?.method).toBe("POST");
    const form = init?.body as FormData;
    expect([form.get("language"), form.get("duration_ms")]).toEqual(["en", "4200"]);
    expect((form.get("audio") as File).name).toBe("dictation.mp4");
  });

  it("sends no language at all when there is no hint to give", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({
      ok: true,
      status: 200,
      json: async () => ({ text: "ik heb een boek" }),
    }));
    vi.stubGlobal("fetch", fetchMock);
    await transcribe(new Blob(["a"], { type: "audio/webm" }), { language: null, durationMs: 1000 });
    const form = fetchMock.mock.calls[0]![1]?.body as FormData;
    expect(form.has("language")).toBe(false);
  });

  it("raises the server's own message when it refuses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 429,
        json: async () => ({ code: "dictation_rate_limited", message: "Trop de dictées." }),
      })),
    );
    await expect(
      transcribe(new Blob(["a"]), { language: "fr", durationMs: 1000 }),
    ).rejects.toMatchObject({ code: "dictation_rate_limited", status: 429 });
  });
});
