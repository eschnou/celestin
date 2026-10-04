// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { usePhotoWork, type PhotoDeps } from "../use-photo-work";

const jpeg = () => new Blob(["x"], { type: "image/jpeg" });

function deps(read: PhotoDeps["read"]): PhotoDeps {
  return { prepare: vi.fn(async (file: Blob) => file), read };
}

const flush = () => act(async () => {});

afterEach(cleanup);

describe("usePhotoWork", () => {
  it("reads a photo for the course and hands over the text", async () => {
    const read = vi.fn(async () => "  $x = 4$ ");
    const onText = vi.fn();
    const { result } = renderHook(() => usePhotoWork({ courseId: "c1", onText, deps: deps(read) }));
    act(() => result.current.read(jpeg()));
    expect(result.current.phase).toBe("reading");
    await flush();
    expect(read).toHaveBeenCalledWith("c1", expect.any(Blob), expect.any(AbortSignal));
    expect(onText).toHaveBeenCalledWith("$x = 4$");
    expect(result.current.phase).toBe("idle");
    expect(result.current.error).toBeNull();
  });

  it("refuses what is not an image, without a round trip", async () => {
    const read = vi.fn(async () => "x");
    const { result } = renderHook(() =>
      usePhotoWork({ courseId: "c1", onText: vi.fn(), deps: deps(read) }),
    );
    act(() => result.current.read(new Blob(["x"], { type: "application/pdf" })));
    expect(result.current.error).toEqual({ kind: "not-image" });
    expect(read).not.toHaveBeenCalled();
  });

  it("says so when the photo held nothing", async () => {
    const onText = vi.fn();
    const { result } = renderHook(() =>
      usePhotoWork({ courseId: "c1", onText, deps: deps(async () => "") }),
    );
    act(() => result.current.read(jpeg()));
    await flush();
    expect(onText).not.toHaveBeenCalled();
    expect(result.current.error).toEqual({ kind: "empty" });
  });

  it("reports a failure with its cause, and can be tried again", async () => {
    const cause = new Error("502");
    const read = vi.fn().mockRejectedValueOnce(cause).mockResolvedValueOnce("ok");
    const onText = vi.fn();
    const { result } = renderHook(() => usePhotoWork({ courseId: "c1", onText, deps: deps(read) }));
    act(() => result.current.read(jpeg()));
    await flush();
    expect(result.current.error).toEqual({ kind: "failed", cause });
    act(() => result.current.read(jpeg()));
    await flush();
    expect(result.current.error).toBeNull();
    expect(onText).toHaveBeenCalledWith("ok");
  });

  it("reads one photo at a time", async () => {
    let finish: (text: string) => void = () => {};
    const read = vi.fn(() => new Promise<string>((resolve) => (finish = resolve)));
    const { result } = renderHook(() =>
      usePhotoWork({ courseId: "c1", onText: vi.fn(), deps: deps(read) }),
    );
    act(() => result.current.read(jpeg()));
    act(() => result.current.read(jpeg()));
    await flush();
    expect(read).toHaveBeenCalledOnce();
    finish("done");
    await flush();
  });

  it("gives up on a call: the text never arrives", async () => {
    const read = vi.fn(
      (_c: string, _p: Blob, signal: AbortSignal) =>
        new Promise<string>((resolve) => signal.addEventListener("abort", () => resolve("late"))),
    );
    const onText = vi.fn();
    const { result } = renderHook(() => usePhotoWork({ courseId: "c1", onText, deps: deps(read) }));
    act(() => result.current.read(jpeg()));
    await flush();
    act(() => result.current.cancel());
    await flush();
    expect(onText).not.toHaveBeenCalled();
    expect(result.current.phase).toBe("idle");
    expect(result.current.error).toBeNull();
  });
});
