import { describe, expect, it } from "vitest";
import { parseChunk } from "../sse";

describe("parseChunk", () => {
  it("parses a single frame", () => {
    const { frames, rest } = parseChunk('event: turn.start\ndata: {"turn_id":"a"}\n\n');
    expect(frames).toEqual([{ event: "turn.start", data: '{"turn_id":"a"}' }]);
    expect(rest).toBe("");
  });

  it("parses several frames in one chunk", () => {
    const { frames } = parseChunk(
      'event: text.delta\ndata: {"text":"a"}\n\nevent: text.delta\ndata: {"text":"b"}\n\n',
    );
    expect(frames.map((f) => f.data)).toEqual(['{"text":"a"}', '{"text":"b"}']);
  });

  it("retains a partial frame in the carry", () => {
    const first = parseChunk('event: text.delta\ndata: {"te');
    expect(first.frames).toEqual([]);
    const second = parseChunk('xt":"à"}\n\n', first.rest);
    expect(second.frames).toEqual([{ event: "text.delta", data: '{"text":"à"}' }]);
    expect(second.rest).toBe("");
  });

  it("handles a split across the frame terminator", () => {
    const a = parseChunk('event: turn.end\ndata: {"reason":"end"}\n');
    expect(a.frames).toEqual([]);
    const b = parseChunk("\n", a.rest);
    expect(b.frames).toHaveLength(1);
  });

  it("joins multi-line data", () => {
    const { frames } = parseChunk("event: x\ndata: one\ndata: two\n\n");
    expect(frames[0]!.data).toBe("one\ntwo");
  });

  it("ignores heartbeat comments", () => {
    const { frames } = parseChunk(': ping\n\nevent: x\ndata: {"a":1}\n\n');
    expect(frames).toEqual([{ event: "x", data: '{"a":1}' }]);
  });

  it("ignores a frame with no data line", () => {
    expect(parseChunk("event: x\n\n").frames).toEqual([]);
  });

  it("defaults the event name when none is given", () => {
    expect(parseChunk("data: hello\n\n").frames).toEqual([{ event: "message", data: "hello" }]);
  });

  it("strips exactly one leading space after data:", () => {
    expect(parseChunk("data:  two spaces\n\n").frames[0]!.data).toBe(" two spaces");
  });
});
