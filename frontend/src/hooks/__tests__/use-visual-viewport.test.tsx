// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useVisualViewport } from "../use-visual-viewport";

class FakeViewport extends EventTarget {
  height = 700;
  offsetTop = 0;
}

let viewport: FakeViewport;

beforeEach(() => {
  viewport = new FakeViewport();
  vi.stubGlobal("visualViewport", viewport);
  vi.stubGlobal("innerHeight", 700);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("useVisualViewport", () => {
  it("is unknown without the API", () => {
    vi.stubGlobal("visualViewport", null);
    const { result } = renderHook(() => useVisualViewport());
    expect(result.current).toEqual({ height: null, offsetTop: 0, keyboardOpen: false });
  });

  it("reports the height the page can use", () => {
    const { result } = renderHook(() => useVisualViewport());
    expect(result.current).toEqual({ height: 700, offsetTop: 0, keyboardOpen: false });
  });

  it("sees a keyboard as lost height, and a browser bar as nothing", () => {
    const { result } = renderHook(() => useVisualViewport());
    act(() => {
      viewport.height = 640;
      viewport.dispatchEvent(new Event("resize"));
    });
    expect(result.current.keyboardOpen).toBe(false);
    act(() => {
      viewport.height = 380;
      viewport.offsetTop = 12;
      viewport.dispatchEvent(new Event("resize"));
    });
    expect(result.current).toEqual({ height: 380, offsetTop: 12, keyboardOpen: true });
  });
});
