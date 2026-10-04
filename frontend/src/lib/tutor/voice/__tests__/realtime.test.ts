import { describe, expect, it } from "vitest";
import { functionOutputItem, parseServerEvent, systemTextItem, userTextItem } from "../realtime";

describe("parseServerEvent", () => {
  it("parses a known event", () => {
    expect(parseServerEvent('{"type":"response.created","response":{"id":"r"}}')).toEqual({
      type: "response.created",
      response: { id: "r" },
    });
  });

  it("ignores unknown types", () => {
    expect(parseServerEvent('{"type":"rate_limits.updated"}')).toBeNull();
  });

  it("returns null on malformed input", () => {
    expect(parseServerEvent("{nope")).toBeNull();
    expect(parseServerEvent("42")).toBeNull();
    expect(parseServerEvent('{"notype":1}')).toBeNull();
  });
});

describe("client event builders", () => {
  it("shape user, system and function output items", () => {
    expect(userTextItem("hi").item).toEqual({
      type: "message",
      role: "user",
      content: [{ type: "input_text", text: "hi" }],
    });
    expect(systemTextItem("s").item).toMatchObject({ role: "system" });
    expect(functionOutputItem("c1", '{"ok":true}').item).toEqual({
      type: "function_call_output",
      call_id: "c1",
      output: '{"ok":true}',
    });
  });
});
