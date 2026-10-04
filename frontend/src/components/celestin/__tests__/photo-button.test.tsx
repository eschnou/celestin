// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PhotoButton } from "../photo-button";
import type { WebcamDeps } from "../webcam-camera";
import { withLocale } from "@/test/locale";

function pointer(coarse: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("coarse") ? coarse : false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

function webcam(over: Partial<WebcamDeps> = {}) {
  const track = { stop: vi.fn() };
  const deps: WebcamDeps = {
    getCamera: vi.fn(async () => ({ getTracks: () => [track] }) as unknown as MediaStream),
    capture: vi.fn(async () => new Blob(["jpeg"], { type: "image/jpeg" })),
    ...over,
  };
  return { deps, track };
}

function mount(onPhoto = vi.fn(), deps?: WebcamDeps) {
  render(
    <PhotoButton
      onPhoto={onPhoto}
      busy={false}
      disabled={false}
      className="btn"
      {...(deps ? { webcamDeps: deps } : {})}
    />,
  );
  return onPhoto;
}

const openMenu = () =>
  fireEvent.keyDown(screen.getByRole("button", { name: "Joindre une photo de mon travail" }), {
    key: "Enter",
  });

beforeEach(() => {
  vi.stubGlobal(
    "URL",
    Object.assign(URL, { createObjectURL: () => "blob:x", revokeObjectURL: () => {} }),
  );
  Object.defineProperty(navigator, "mediaDevices", {
    value: { getUserMedia: vi.fn() },
    configurable: true,
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  Object.defineProperty(navigator, "mediaDevices", { value: undefined, configurable: true });
});

describe("PhotoButton on a phone", () => {
  it("offers the phone's camera and its gallery, as file inputs", async () => {
    pointer(true);
    const onPhoto = mount();
    openMenu();
    expect(await screen.findByRole("menuitem", { name: "Prendre une photo" })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Choisir une image" })).toBeTruthy();
    const camera = screen.getByTestId("photo-camera-input") as HTMLInputElement;
    expect([camera.accept, camera.getAttribute("capture")]).toEqual(["image/*", "environment"]);
    expect(
      (screen.getByTestId("photo-file-input") as HTMLInputElement).hasAttribute("capture"),
    ).toBe(false);
    const file = new File(["x"], "feuille.jpg", { type: "image/jpeg" });
    fireEvent.change(camera, { target: { files: [file] } });
    expect(onPhoto).toHaveBeenCalledWith(file);
  });

  it("never opens the webcam dialog", async () => {
    pointer(true);
    mount();
    openMenu();
    fireEvent.click(await screen.findByRole("menuitem", { name: "Prendre une photo" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("PhotoButton on a computer", () => {
  it("takes a picture with the webcam, can retake it, and releases the camera", async () => {
    pointer(false);
    const { deps, track } = webcam();
    const onPhoto = mount(vi.fn(), deps);
    openMenu();
    await act(async () => {
      fireEvent.click(await screen.findByRole("menuitem", { name: "Prendre une photo" }));
    });
    expect(await screen.findByRole("dialog")).toBeTruthy();
    await act(async () => {});
    fireEvent.click(await screen.findByRole("button", { name: "Prendre la photo" }));
    expect(await screen.findByRole("img", { name: "La photo prise" })).toBeTruthy();
    expect(track.stop).toHaveBeenCalled(); // the camera's light goes off as soon as the picture is taken
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Refaire" }));
    });
    expect(deps.getCamera).toHaveBeenCalledTimes(2);
    fireEvent.click(await screen.findByRole("button", { name: "Prendre la photo" }));
    await screen.findByRole("img", { name: "La photo prise" });
    fireEvent.click(screen.getByRole("button", { name: "Utiliser cette photo" }));
    expect(onPhoto).toHaveBeenCalledWith(expect.any(Blob));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("says when the camera is blocked, and points to the chooser", async () => {
    pointer(false);
    const { deps } = webcam({
      getCamera: vi.fn(async () => {
        throw new DOMException("no", "NotAllowedError");
      }),
    });
    mount(vi.fn(), deps);
    openMenu();
    await act(async () => {
      fireEvent.click(await screen.findByRole("menuitem", { name: "Prendre une photo" }));
    });
    expect((await screen.findByRole("alert")).textContent).toMatch(/La caméra est bloquée/);
  });

  it("opens the file chooser for « Choisir une image »", async () => {
    pointer(false);
    const onPhoto = mount();
    const input = screen.getByTestId("photo-file-input") as HTMLInputElement;
    const click = vi.spyOn(input, "click").mockImplementation(() => {});
    openMenu();
    fireEvent.click(await screen.findByRole("menuitem", { name: "Choisir une image" }));
    expect(click).toHaveBeenCalledOnce();
    const file = new File(["x"], "a.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [file] } });
    expect(onPhoto).toHaveBeenCalledWith(file);
  });

  it("goes straight to the chooser when there is no webcam", () => {
    pointer(false);
    Object.defineProperty(navigator, "mediaDevices", { value: undefined, configurable: true });
    mount();
    const input = screen.getByTestId("photo-file-input") as HTMLInputElement;
    const click = vi.spyOn(input, "click").mockImplementation(() => {});
    fireEvent.click(screen.getByRole("button", { name: "Joindre une photo de mon travail" }));
    expect(click).toHaveBeenCalledOnce();
  });

  it("words the camera in English", () =>
    withLocale("en", async () => {
      pointer(false);
      mount(vi.fn(), webcam().deps);
      fireEvent.keyDown(screen.getByRole("button", { name: "Attach a photo of my work" }), {
        key: "Enter",
      });
      await act(async () => {
        fireEvent.click(await screen.findByRole("menuitem", { name: "Take a photo" }));
      });
      expect(await screen.findByText("Photograph my work")).toBeTruthy();
      expect(await screen.findByRole("button", { name: "Take the photo" })).toBeTruthy();
    }));
});
