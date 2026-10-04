import { afterEach, describe, expect, it, vi } from "vitest";
import { EMPTY_PROGRESS } from "../../types";

const SCOPE = { courseId: "maths-5e", chapterId: "suites" };
import { createVoiceSession, executeTool, reportUsage, VoiceRequestError } from "../client";
import { EMPTY_USAGE } from "../types";

afterEach(() => vi.unstubAllGlobals());

function mockFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status < 400,
    status,
    json: async () => body,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("createVoiceSession", () => {
  it("posts the scope and the history and maps the wire shape", async () => {
    const fetchMock = mockFetch(201, {
      session_id: "s1",
      secret: "ek_x",
      calls_url: "https://api.openai.com/v1/realtime/calls",
      expires_at: 1,
      model: "m",
      voice: "marin",
      limits: { max_session_s: 1500, idle_s: 180 },
      seed: [{ type: "message" }],
      opening: false,
    });
    const info = await createVoiceSession(SCOPE, [{ kind: "learner", text: "hi" }]);
    expect(JSON.parse(fetchMock.mock.calls[0]![1].body)).toEqual({
      course_id: "maths-5e",
      chapter_id: "suites",
      history: [{ kind: "learner", text: "hi" }],
    });
    expect(info).toEqual({
      sessionId: "s1",
      secret: "ek_x",
      callsUrl: "https://api.openai.com/v1/realtime/calls",
      expiresAt: 1,
      model: "m",
      voice: "marin",
      limits: { maxSessionS: 1500, idleS: 180 },
      seed: [{ type: "message" }],
      opening: false,
    });
  });

  it("surfaces the server's French message on 429", async () => {
    mockFetch(429, { code: "voice_rate_limited", message: "Trop de séances vocales." });
    await expect(createVoiceSession(SCOPE, [])).rejects.toMatchObject({
      code: "voice_rate_limited",
      message: "Trop de séances vocales.",
    });
  });
});

describe("executeTool", () => {
  it("posts the raw call and returns output, event, progress and state text", async () => {
    const fetchMock = mockFetch(200, {
      output: '{"ok":true}',
      event: { event: "section.start", section_id: "s", review: false, marker: "m" },
      progress: { done: [], active: "s" },
      state_text: "État",
    });
    const result = await executeTool(
      "s1",
      { callId: "c1", name: "start_section", arguments: '{"section_id":"s"}' },
      SCOPE,
    );
    expect(JSON.parse(fetchMock.mock.calls[0]![1].body)).toEqual({
      session_id: "s1",
      call_id: "c1",
      name: "start_section",
      arguments: '{"section_id":"s"}',
      course_id: "maths-5e",
      chapter_id: "suites",
    });
    expect(result.stateText).toBe("État");
    expect(result.progress).toEqual({ done: [], active: "s" });
  });

  it("omits stateText when the server sends null", async () => {
    mockFetch(200, { output: "{}", event: null, progress: EMPTY_PROGRESS, state_text: null });
    const result = await executeTool("s", { callId: "c", name: "x", arguments: "" }, SCOPE);
    expect("stateText" in result).toBe(false);
  });
});

describe("reportUsage", () => {
  const report = {
    session_id: "s",
    reason: "learner" as const,
    duration_s: 1,
    responses: 1,
    usage: EMPTY_USAGE,
  };

  it("uses sendBeacon when asked and available", () => {
    const beacon = vi.fn().mockReturnValue(true);
    vi.stubGlobal("navigator", { sendBeacon: beacon });
    const fetchMock = mockFetch(204, null);
    reportUsage(report, { beacon: true });
    expect(beacon).toHaveBeenCalledOnce();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("falls back to a keepalive fetch", () => {
    vi.stubGlobal("navigator", {});
    const fetchMock = mockFetch(204, null);
    reportUsage(report);
    expect(fetchMock.mock.calls[0]![1]).toMatchObject({ keepalive: true });
  });
});
