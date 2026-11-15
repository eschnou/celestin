/** Révision requests and the chooser's and the « Bilan »'s pure rules (spec 020). */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  latestResults,
  preselected,
  resultKey,
  REVISION_TURN_URL,
  revisionTransport,
  startRevision,
} from "../revision";
import { learnerSentences } from "../prompts";
import type { RevisionChapter } from "../types";

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

const chapter = (id: string, over: Partial<RevisionChapter> = {}): RevisionChapter => ({
  id,
  position: 1,
  title: id,
  ready: true,
  section_count: 4,
  done_count: 0,
  skipped_count: 0,
  sections: [],
  ...over,
});

describe("révision requests", () => {
  it("starts a révision on the course's route, and answers with the GET's read", async () => {
    const read = {
      revision: { id: "r1", chapter_ids: ["h1"], entries: [], entry_count: 0, created_at: "" },
      chapters: [chapter("h1")],
      results: [{ chapter_id: "h1", section_id: "s1", outcome: "shaky", at: "2026-11-10" }],
    };
    const fetchMock = stub(201, read);
    const view = await startRevision("c 1", ["h1", "h2"]);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/courses/c%201/revision");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ chapter_ids: ["h1", "h2"] });
    expect(view).toEqual(read);
  });

  it("posts the course, the révision and the message, never the transcript", async () => {
    const fetchMock = stub(500);
    const stream = revisionTransport({ courseId: "c1", revisionId: "r1" })(
      { message: "Pour moi, c'est acquis." },
      new AbortController().signal,
    );
    await stream.next();
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe(REVISION_TURN_URL);
    expect(url).toBe("/api/revision/turn");
    expect(JSON.parse(init.body)).toEqual({
      course_id: "c1",
      revision_id: "r1",
      message: "Pour moi, c'est acquis.",
    });
  });

  it("opens with a null message", async () => {
    const fetchMock = stub(500);
    await revisionTransport({ courseId: "c1", revisionId: "r1" })(
      { message: null },
      new AbortController().signal,
    ).next();
    expect(JSON.parse(fetchMock.mock.calls[0]![1].body).message).toBeNull();
  });

  it("turns a closed révision into an error event with the server's words", async () => {
    stub(409, { code: "conversation_closed", message: "Cette révision est close." });
    const stream = revisionTransport({ courseId: "c1", revisionId: "r1" })(
      { message: "salut" },
      new AbortController().signal,
    );
    expect((await stream.next()).value).toEqual({
      event: "error",
      code: "conversation_closed",
      message: "Cette révision est close.",
    });
  });
});

describe("the chooser's preselection", () => {
  it("ticks the ready chapters with progress, done or skipped", () => {
    expect(
      preselected([
        chapter("a", { done_count: 2 }),
        chapter("b"),
        chapter("c", { skipped_count: 1 }),
        chapter("d", { ready: false, done_count: 3 }),
      ]),
    ).toEqual(["a", "c"]);
  });

  it("ticks every ready chapter when none has progress", () => {
    expect(preselected([chapter("a"), chapter("b"), chapter("c", { ready: false })])).toEqual([
      "a",
      "b",
    ]);
  });

  it("ticks only the chapter she came from, when it is ready", () => {
    const chapters = [
      chapter("a", { done_count: 2 }),
      chapter("b"),
      chapter("c", { ready: false }),
    ];
    expect(preselected(chapters, "b")).toEqual(["b"]);
    // A chapter that is not ready, or not the course's, falls back to the rule.
    expect(preselected(chapters, "c")).toEqual(["a"]);
    expect(preselected(chapters, "zz")).toEqual(["a"]);
  });
});

describe("the latest result per section", () => {
  it("lays what was noted on this page over the server's read, dated now", () => {
    const latest = latestResults(
      [
        { chapter_id: "h1", section_id: "s1", outcome: "shaky", at: "2026-11-01T10:00:00Z" },
        { chapter_id: "h1", section_id: "s2", outcome: "todo", at: "2026-11-02T10:00:00Z" },
      ],
      [
        { chapter_id: "h1", section_id: "s1", outcome: "todo" },
        { chapter_id: "h1", section_id: "s1", outcome: "solid" },
      ],
      "2026-11-15T09:00:00Z",
    );
    expect(latest.get(resultKey("h1", "s1"))).toEqual({
      outcome: "solid",
      at: "2026-11-15T09:00:00Z",
    });
    expect(latest.get(resultKey("h1", "s2"))).toMatchObject({ outcome: "todo" });
    expect(latest.get(resultKey("h2", "s1"))).toBeUndefined();
  });
});

describe("the quick replies' sentences", () => {
  it("are the student's words in the course's language", () => {
    expect(learnerSentences("fr").assess("solid")).toBe("Pour moi, c'est acquis.");
    expect(learnerSentences("fr").assess("shaky")).toBe("Pour moi, c'est fragile.");
    expect(learnerSentences("fr").assess("todo")).toBe("Pour moi, c'est à revoir.");
    expect(learnerSentences("en").assess("shaky")).toBe("I'd say it's shaky.");
    expect(learnerSentences("nl").assess("solid")).toBe("Voor mij is dat gekend.");
  });
});
