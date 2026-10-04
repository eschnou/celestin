// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { preparePhoto, readWork, workUrl } from "../work";

afterEach(() => vi.unstubAllGlobals());

describe("readWork", () => {
  it("posts the photo to the course's route and returns the text, trimmed", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({
      ok: true,
      status: 200,
      json: async () => ({ text: "  $x = 4$  " }),
    }));
    vi.stubGlobal("fetch", fetchMock);
    const text = await readWork("c 1", new Blob(["a"], { type: "image/jpeg" }));
    expect(text).toBe("$x = 4$");
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe(workUrl("c 1"));
    expect(url).toBe("/api/courses/c%201/work");
    expect(init?.method).toBe("POST");
    expect(((init?.body as FormData).get("photo") as File).name).toBe("work.jpg");
  });

  it("raises the server's own message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 422,
        json: async () => ({ code: "document_invalid", message: "La photo 1 est illisible." }),
      })),
    );
    await expect(readWork("c", new Blob(["a"]))).rejects.toMatchObject({
      code: "document_invalid",
      message: "La photo 1 est illisible.",
    });
  });
});

describe("preparePhoto", () => {
  it("sends the original where the browser cannot decode pictures", async () => {
    const file = new Blob(["a"], { type: "image/jpeg" });
    expect(await preparePhoto(file)).toBe(file);
  });

  it("sends the original when the picture cannot be decoded", async () => {
    vi.stubGlobal("createImageBitmap", vi.fn().mockRejectedValue(new Error("no")));
    const file = new Blob(["a"], { type: "image/heic" });
    expect(await preparePhoto(file)).toBe(file);
  });

  it("keeps a small JPEG as it is, without redrawing it", async () => {
    const close = vi.fn();
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn().mockResolvedValue({ width: 1200, height: 900, close }),
    );
    const file = new Blob(["a"], { type: "image/jpeg" });
    expect(await preparePhoto(file)).toBe(file);
    expect(close).toHaveBeenCalledOnce();
  });
});
