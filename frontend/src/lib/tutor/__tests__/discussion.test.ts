import { afterEach, describe, expect, it, vi } from "vitest";

import { discussionTransport, recordVoiceTurn, startConversation, TURN_URL } from "../discussion";

const CONVERSATION = {
  id: "c".repeat(32),
  chapter_id: "b".repeat(32),
  entries: [],
  entry_count: 0,
  created_at: "",
};

function stub(status = 200, body: unknown = {}) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status < 400,
    status,
    json: async () => body,
    body: null,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("discussion requests", () => {
  it("starts a conversation on the chapter's nested route", async () => {
    const fetchMock = stub(200, { conversation: CONVERSATION });
    await startConversation("c 1", "h1");
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/courses/c%201/chapters/h1/discussion");
    expect(init.method).toBe("POST");
  });

  it("posts the message, never the transcript", async () => {
    const fetchMock = stub(500);
    const stream = discussionTransport({ courseId: "c1", chapterId: "h1", conversationId: "conv" })(
      { message: "et les suites ?" },
      new AbortController().signal,
    );
    await stream.next();
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe(TURN_URL);
    expect(JSON.parse(init.body)).toEqual({
      course_id: "c1",
      chapter_id: "h1",
      conversation_id: "conv",
      message: "et les suites ?",
    });
    expect(init.body).not.toContain("history");
  });

  it("sends a null message for the opening turn", async () => {
    const fetchMock = stub(500);
    const stream = discussionTransport({ courseId: "c1", chapterId: "h1", conversationId: "conv" })(
      { message: null },
      new AbortController().signal,
    );
    await stream.next();
    expect(JSON.parse(fetchMock.mock.calls[0]![1].body).message).toBeNull();
  });

  it("turns a pre-stream failure into an error event and a turn end", async () => {
    stub(409, { code: "conversation_closed", message: "Ouvre une nouvelle discussion." });
    const stream = discussionTransport({ courseId: "c1", chapterId: "h1", conversationId: "conv" })(
      { message: "salut" },
      new AbortController().signal,
    );
    const first = await stream.next();
    const second = await stream.next();
    expect(first.value).toEqual({
      event: "error",
      code: "conversation_closed",
      message: "Ouvre une nouvelle discussion.",
    });
    expect(second.value).toMatchObject({ event: "turn.end" });
  });

  it("reports a spoken turn, and sends nothing when there is nothing to report", async () => {
    const fetchMock = stub(204);
    await recordVoiceTurn({ courseId: "c1", chapterId: "h1", conversationId: "conv" }, []);
    expect(fetchMock).not.toHaveBeenCalled();

    await recordVoiceTurn({ courseId: "c1", chapterId: "h1", conversationId: "conv" }, [
      { kind: "learner", text: "salut" },
    ]);
    expect(JSON.parse(fetchMock.mock.calls[0]![1].body)).toMatchObject({
      conversation_id: "conv",
      entries: [{ kind: "learner", text: "salut" }],
    });
  });
});
