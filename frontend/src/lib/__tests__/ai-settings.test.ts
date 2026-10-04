import { QueryClient } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { afterAiChange, AI_KEY, aiModels, aiSettingsQuery, saveAiSettings, testAi } from "../admin";
import { fetchHealth } from "../tutor/health";

afterEach(() => vi.unstubAllGlobals());

function mockFetch(body: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => body });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const VIEW = { can_store: true, configured: true, voice_available: false };

describe("the AI provider calls (specs 013, 014)", () => {
  it("reads the view", async () => {
    const fetchMock = mockFetch(VIEW);
    expect(await (aiSettingsQuery.queryFn as () => Promise<unknown>)()).toEqual(VIEW);
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/admin/ai");
  });

  it("saves with PUT and the whole form in a JSON body", async () => {
    const fetchMock = mockFetch(VIEW);
    const request = {
      default: {
        base_url: "https://api.groq.com/openai/v1",
        api_style: "responses" as const,
        structured: "schema" as const,
        api_key: "gsk-1234",
        clear_key: false,
      },
      roles: { tutor: { model: "qwen/qwen3.8-27b", reasoning_effort: null, connection: null } },
    };
    expect(await saveAiSettings(request)).toEqual(VIEW);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/admin/ai");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual(request);
  });

  it("lists a slot's models with GET and the slot in the query", async () => {
    const listing = { status: "ok", ids: ["a", "b"], limited: false };
    const fetchMock = mockFetch(listing);
    expect(await aiModels("transcription")).toEqual(listing);
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/admin/ai/models?slot=transcription");
  });

  it("tests with POST, asking for a live check only when told to", async () => {
    const report = { roles: [] };
    const fetchMock = mockFetch(report);
    expect(await testAi()).toEqual(report);
    expect(await testAi(true)).toEqual(report);
    const [url, first] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/admin/ai/test");
    expect(first.method).toBe("POST");
    expect(JSON.parse(first.body)).toEqual({ live: false });
    expect(JSON.parse(fetchMock.mock.calls[1]![1].body)).toEqual({ live: true });
  });

  it("raises the server's refusal", async () => {
    mockFetch({ code: "ai_key_rejected", message: "Le fournisseur a refusé cette clé." }, 422);
    await expect(
      saveAiSettings({
        default: {
          base_url: "x",
          api_style: "responses",
          structured: "schema",
          api_key: null,
          clear_key: false,
        },
        roles: {},
      }),
    ).rejects.toMatchObject({ code: "ai_key_rejected", status: 422 });
  });
});

describe("after a change", () => {
  it("takes the server's answer as the new view and reads the health again", async () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(["health"], { voice: false, aiConfigured: false });
    const view = { ...VIEW } as never;
    mockFetch({ voice: true, ai_configured: true });
    await afterAiChange(queryClient, view);
    expect(queryClient.getQueryData(AI_KEY)).toBe(view);
    expect(queryClient.getQueryState(["health"])?.isInvalidated).toBe(true);
    expect(await fetchHealth()).toEqual({ voice: true, dictation: false, aiConfigured: true });
  });
});
