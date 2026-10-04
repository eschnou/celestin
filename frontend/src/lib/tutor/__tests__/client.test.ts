import { afterEach, describe, expect, it, vi } from "vitest";
import { streamTurn } from "../client";
import type { TutorEvent } from "../types";

const SCOPE = { courseId: "maths-5e", chapterId: "suites" };

/** The golden transcript from the backend integration tests. */
const GOLDEN =
  'event: turn.start\ndata: {"turn_id":"abc"}\n\n' +
  'event: text.delta\ndata: {"block_id":0,"text":"Salut "}\n\n' +
  ": ping\n\n" +
  'event: board.set\ndata: {"card":{"kind":"exercise","title":"T","statement":"S","hint":null},"marker":"exercice posé"}\n\n' +
  'event: text.delta\ndata: {"block_id":1,"text":"À toi."}\n\n' +
  'event: turn.end\ndata: {"reason":"end","usage":{"input_tokens":9}}\n\n';

const encoder = new TextEncoder();

function bodyFrom(chunks: string[]): ReadableStream<Uint8Array> {
  let i = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i >= chunks.length) return controller.close();
      controller.enqueue(encoder.encode(chunks[i++]!));
    },
  });
}

/** An endless stream, so cancel() actually reaches the underlying source. */
function endlessBody(onCancel: () => void): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      controller.enqueue(encoder.encode('event: text.delta\ndata: {"block_id":0,"text":"x"}\n\n'));
    },
    cancel: onCancel,
  });
}

function mockFetch(response: Record<string, unknown>) {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, ...response });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function collect(signal?: AbortSignal): Promise<TutorEvent[]> {
  const out: TutorEvent[] = [];
  for await (const event of streamTurn(SCOPE, [], signal)) out.push(event);
  return out;
}

afterEach(() => vi.unstubAllGlobals());

describe("streamTurn", () => {
  it("posts the class, the chapter and the transcript (004 R6.3)", async () => {
    const fetchMock = mockFetch({ body: bodyFrom([GOLDEN]) });
    const out: TutorEvent[] = [];
    for await (const event of streamTurn(SCOPE, [{ kind: "learner", text: "salut" }]))
      out.push(event);
    const body = JSON.parse(fetchMock.mock.calls[0]![1].body as string);
    expect(body).toEqual({
      course_id: "maths-5e",
      chapter_id: "suites",
      history: [{ kind: "learner", text: "salut" }],
    });
  });

  it("yields every event of a golden transcript in order", async () => {
    mockFetch({ body: bodyFrom([GOLDEN]) });
    const events = await collect();
    expect(events.map((e) => e.event)).toEqual([
      "turn.start",
      "text.delta",
      "board.set",
      "text.delta",
      "turn.end",
    ]);
    expect(events[2]).toMatchObject({ marker: "exercice posé" });
    expect(events[4]).toMatchObject({ reason: "end" });
  });

  it("is indifferent to where the network splits the bytes", async () => {
    const chunks = GOLDEN.match(/[\s\S]{1,7}/g)!;
    mockFetch({ body: bodyFrom(chunks) });
    expect((await collect()).map((e) => e.event)).toHaveLength(5);
  });

  it("posts the transcript as JSON", async () => {
    const fetchMock = mockFetch({ body: bodyFrom([GOLDEN]) });
    for await (const _ of streamTurn(SCOPE, [{ kind: "learner", text: "salut" }])) break;
    const [, init] = fetchMock.mock.calls[0]!;
    expect(JSON.parse(init.body)).toEqual({
      course_id: "maths-5e",
      chapter_id: "suites",
      history: [{ kind: "learner", text: "salut" }],
    });
    expect(init.method).toBe("POST");
  });

  it("turns a non-200 into an error event carrying the server message", async () => {
    mockFetch({
      ok: false,
      status: 500,
      body: null,
      json: async () => ({ code: "pack_unavailable", message: "Le cours n'a pas pu être chargé." }),
    });
    const events = await collect();
    expect(events).toEqual([
      // The server's own code survives, rather than being flattened to http_error.
      { event: "error", code: "pack_unavailable", message: "Le cours n'a pas pu être chargé." },
      { event: "turn.end", reason: "end", usage: {} },
    ]);
  });

  it("explains a rejected request instead of blaming the network", async () => {
    // FastAPI validation errors carry `detail`, not `message`.
    mockFetch({
      ok: false,
      status: 422,
      body: null,
      json: async () => ({ detail: [{ loc: ["body", "history"], msg: "too long" }] }),
    });
    const [first] = await collect();
    expect(first).toMatchObject({ event: "error", code: "invalid_request" });
    expect((first as { message: string }).message).toContain("Recharge la page");
    expect((first as { message: string }).message).not.toContain("injoignable");
  });

  it("falls back to a French message when the error body is unreadable", async () => {
    mockFetch({
      ok: false,
      status: 502,
      body: null,
      json: async () => {
        throw new Error("not json");
      },
    });
    const [first] = await collect();
    expect(first).toMatchObject({ event: "error" });
    expect((first as { message: string }).message).toContain("Célestin");
  });

  it("stops quietly when the caller aborts before the response", async () => {
    const controller = new AbortController();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => {
        controller.abort();
        return Promise.reject(new DOMException("aborted", "AbortError"));
      }),
    );
    expect(await collect(controller.signal)).toEqual([]);
  });

  it("releases the connection when iteration stops early", async () => {
    // An endless stream: a closed one would make cancel() a no-op and prove nothing.
    const onCancel = vi.fn();
    mockFetch({ body: endlessBody(onCancel) });
    for await (const _ of streamTurn(SCOPE, [])) break;
    expect(onCancel).toHaveBeenCalled();
  });
});
