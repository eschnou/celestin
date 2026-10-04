import { describe, expect, it } from "vitest";
import { featuredChapter } from "../featured-chapter";
import type { ChapterRow } from "../types";

const row = (over: Partial<ChapterRow>): ChapterRow => ({
  id: "h",
  position: 1,
  title: "T",
  ready: true,
  section_count: 5,
  done_count: 0,
  state: "not_started",
  last: false,
  authoring_state: "idle",
  authoring_message: null,
  authoring_stage: null,
  pages_done: 0,
  page_count: 0,
  ...over,
});

describe("featuredChapter", () => {
  it("is the chapter she worked on last, if it is not finished", () => {
    const rows = [
      row({ id: "a", state: "in_progress" }),
      row({ id: "b", state: "in_progress", last: true }),
    ];
    expect(featuredChapter(rows)).toEqual({ row: rows[1], resuming: true });
  });

  it("is a chapter in progress when the last one is finished", () => {
    const rows = [
      row({ id: "a", state: "done", last: true }),
      row({ id: "b", state: "not_started" }),
      row({ id: "c", state: "in_progress" }),
    ];
    expect(featuredChapter(rows)).toEqual({ row: rows[2], resuming: true });
  });

  it("is the first chapter not started when none is in progress, and says it is not resuming", () => {
    const rows = [row({ id: "a", state: "done", last: true }), row({ id: "b" })];
    expect(featuredChapter(rows)).toEqual({ row: rows[1], resuming: false });
  });

  it("never offers a chapter that is not ready", () => {
    expect(featuredChapter([row({ ready: false, last: true, state: "in_progress" })])).toBeNull();
  });

  it("is nothing when everything is done", () => {
    expect(featuredChapter([row({ state: "done", last: true })])).toBeNull();
  });
});
