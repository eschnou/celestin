import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../client";
import {
  addChapter,
  createCourse,
  GENERATING_POLL_MS,
  pollWhileGenerating,
  renameCourse,
  replaceDocument,
  saveCurriculum,
  savePack,
  saveSource,
} from "../courses";
import type { ChapterRow } from "../types";

function stub(status = 200, body: unknown = {}) {
  const fetchMock = vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => body });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("course requests", () => {
  it("send the expected methods and bodies", async () => {
    const fetchMock = stub();
    await createCourse("Physique", "sciences", "fr");
    await renameCourse("c 1", "Physique 5e");
    await savePack("c1", "h1", 3, "# P");
    await saveCurriculum("c1", "h1", 3, { title: "T", sections: [] });
    await saveSource("c1", "h1", "nouveau texte");
    const calls = fetchMock.mock.calls.map(([url, init]) => [
      url,
      init.method,
      JSON.parse(init.body),
    ]);
    expect(calls).toEqual([
      ["/api/courses", "POST", { name: "Physique", subject: "sciences", language: "fr" }],
      ["/api/courses/c%201", "PATCH", { name: "Physique 5e" }],
      ["/api/courses/c1/chapters/h1/pack", "PUT", { version: 3, pack: "# P" }],
      [
        "/api/courses/c1/chapters/h1/curriculum",
        "PUT",
        { version: 3, curriculum: { title: "T", sections: [] } },
      ],
      ["/api/courses/c1/chapters/h1/source", "PUT", { source_text: "nouveau texte" }],
    ]);
  });

  it("send documents as a multipart form, one `files` field per file in page order", async () => {
    const fetchMock = stub();
    const pages = [
      new File(["a"], "p1.jpg", { type: "image/jpeg" }),
      new File(["b"], "p2.jpg", { type: "image/jpeg" }),
    ];
    await addChapter("c1", pages);
    await replaceDocument("c1", "h1", pages.slice(0, 1));
    const [[addUrl, add], [replaceUrl, replace]] = fetchMock.mock.calls as [
      [string, RequestInit],
      [string, RequestInit],
    ];
    expect([addUrl, add.method, replaceUrl, replace.method]).toEqual([
      "/api/courses/c1/chapters",
      "POST",
      "/api/courses/c1/chapters/h1/document",
      "PUT",
    ]);
    expect(add.body).toBeInstanceOf(FormData);
    expect((add.body as FormData).getAll("files").map((f) => (f as File).name)).toEqual([
      "p1.jpg",
      "p2.jpg",
    ]);
    expect(add.headers).toBeUndefined(); // the browser sets the multipart boundary
  });

  it("carry the issues of a refused edit", async () => {
    stub(422, {
      code: "content_invalid",
      message: "Le contenu n'est pas valide.",
      issues: [{ where: "§ 5", message: "section manquante" }],
    });
    const error = await savePack("c1", "h1", 1, "#").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).issues).toEqual([{ where: "§ 5", message: "section manquante" }]);
    expect((error as ApiError).code).toBe("content_invalid");
  });
});

describe("polling", () => {
  const rows = (states: ChapterRow["authoring_state"][]) => ({
    chapters: states.map((authoring_state) => ({ authoring_state }) as ChapterRow),
  });

  it("runs only while a chapter is generating", () => {
    expect(pollWhileGenerating(rows(["idle", "generating"]))).toBe(GENERATING_POLL_MS);
    expect(GENERATING_POLL_MS).toBeGreaterThanOrEqual(3000);
    expect(pollWhileGenerating(rows(["idle", "failed"]))).toBe(false);
    expect(pollWhileGenerating(undefined)).toBe(false);
  });
});
