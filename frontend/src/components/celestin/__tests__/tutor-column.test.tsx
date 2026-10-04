// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TutorColumn } from "../tutor-column";
import { statusLabel } from "@/lib/tutor/labels";
import type { DictationDeps } from "../use-dictation";
import type { VoiceControls } from "../use-voice-session";
import type { TranscriptEntry } from "@/lib/tutor/types";

function controls(overrides: Partial<VoiceControls> = {}): VoiceControls {
  return {
    phase: "off",
    muted: false,
    capAt: null,
    supported: true,
    start: vi.fn(async () => {}),
    stop: vi.fn(),
    toggleMute: vi.fn(),
    sendText: vi.fn(),
    ...overrides,
  };
}

function mount(
  voice: VoiceControls,
  entries: TranscriptEntry[] = [],
  status: "idle" | "error" = "idle",
) {
  render(
    <TutorColumn
      entries={entries}
      status={status}
      voice={voice}
      onSend={vi.fn()}
      onCancel={vi.fn()}
      onRetry={vi.fn()}
      onShowBoard={vi.fn()}
    />,
  );
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(1_000_000_000);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("TutorColumn voice controls", () => {
  it("starts a session from the call button, not from the composer's microphone", () => {
    const voice = controls();
    mount(voice);
    fireEvent.click(screen.getByRole("button", { name: "Appeler Célestin" }));
    expect(voice.start).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", { name: /micro/ })).toBeNull();
  });

  it("stays inert when unsupported", () => {
    const voice = controls({ supported: false });
    mount(voice);
    const button = screen.getByRole("button", { name: "Appeler (bientôt)" });
    fireEvent.click(button);
    expect(voice.start).not.toHaveBeenCalled();
  });

  it("shows the phase, the countdown, the mute and the hang-up buttons while active", () => {
    const voice = controls({ phase: "speaking", capAt: Date.now() + 754_000 });
    mount(voice);
    expect(screen.getAllByText("Célestin parle").length).toBeGreaterThan(0);
    expect(screen.getByText("· 12:34")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Couper le micro" }));
    expect(voice.toggleMute).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Raccrocher" }));
    expect(voice.stop).toHaveBeenCalledOnce();
    const textarea = screen.getByPlaceholderText(
      "Écris ou parle à Célestin…",
    ) as HTMLTextAreaElement;
    expect(textarea.disabled).toBe(false);
  });

  it("labels a muted session and the working phase", () => {
    expect(statusLabel("idle", controls({ phase: "listening", muted: true }))).toBe("Micro coupé");
    expect(statusLabel("idle", controls({ phase: "working" }))).toBe("Célestin écrit au tableau");
    expect(statusLabel("idle", controls())).toBe("en séance");
    expect(statusLabel("error", controls())).toBe("hors ligne");
  });

  it("marks spoken entries and hides retry during voice", () => {
    const entries: TranscriptEntry[] = [
      { id: "1", role: "learner", text: "Bonjour", spoken: true },
      { id: "2", role: "tutor", text: "Salut", blockId: 0, spoken: true },
      { id: "3", role: "error", text: "oops" },
    ];
    mount(controls({ phase: "listening" }), entries, "error");
    expect(screen.getAllByRole("img", { name: "dit à voix haute" })).toHaveLength(2);
    expect(screen.queryByRole("button", { name: /Réessayer/ })).toBeNull();
  });
});

describe("TutorColumn dictation", () => {
  function takeDeps(over: Partial<DictationDeps> = {}): DictationDeps {
    return {
      supported: true,
      begin: vi.fn(async () => ({
        level: () => 0.004,
        finish: async () => ({ blob: new Blob(["x"]), durationMs: 1 }),
        cancel: vi.fn(),
      })),
      transcribe: vi.fn(async () => "la somme"),
      now: () => Date.now(),
      tickMs: 50,
      ...over,
    };
  }

  function mountWith(voice: VoiceControls, dictation: boolean, deps: DictationDeps) {
    render(
      <TutorColumn
        entries={[]}
        status="idle"
        voice={voice}
        onSend={vi.fn()}
        onCancel={vi.fn()}
        onRetry={vi.fn()}
        onShowBoard={vi.fn()}
        dictation={dictation}
        dictationDeps={deps}
      />,
    );
  }

  it("has no microphone in the composer unless the server offers dictation", () => {
    mountWith(controls(), false, takeDeps());
    expect(screen.queryByRole("button", { name: "Dicter un message" })).toBeNull();
  });

  it("has none in a browser that cannot record", () => {
    mountWith(controls(), true, takeDeps({ supported: false }));
    expect(screen.queryByRole("button", { name: "Dicter un message" })).toBeNull();
  });

  it("starts a take from the microphone, says it listens, and stops on a second tap", async () => {
    const deps = takeDeps();
    mountWith(controls(), true, deps);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Dicter un message" }));
    });
    expect(screen.getByPlaceholderText("Parle, je t'écoute…")).toBeTruthy();
    expect(deps.begin).toHaveBeenCalledOnce();
    expect(
      screen.getByRole("button", { name: "Terminer la dictée" }).getAttribute("aria-pressed"),
    ).toBe("true");
  });

  it("explains a refused microphone under the field", async () => {
    const deps = takeDeps({
      begin: vi.fn(async () => {
        throw new Error("denied");
      }),
    });
    mountWith(controls(), true, deps);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Dicter un message" }));
    });
    expect(screen.getByRole("alert").textContent).toMatch(/Le micro est bloqué/);
  });

  it("is the call's mute, not a dictation, while a call is open", () => {
    mountWith(controls({ phase: "listening" }), true, takeDeps());
    expect(screen.queryByRole("button", { name: "Dicter un message" })).toBeNull();
    expect(screen.getByRole("button", { name: "Couper le micro" })).toBeTruthy();
  });
});

describe("TutorColumn photographed work", () => {
  const photoDeps = (text: string) => ({
    prepare: vi.fn(async (file: Blob) => file),
    read: vi.fn(async () => text),
  });

  function mountPhoto(deps: ReturnType<typeof photoDeps>, withCourse = true) {
    render(
      <TutorColumn
        entries={[]}
        status="idle"
        voice={controls()}
        onSend={vi.fn()}
        onCancel={vi.fn()}
        onRetry={vi.fn()}
        onShowBoard={vi.fn()}
        {...(withCourse ? { courseId: "c1" } : {})}
        photoDeps={deps}
      />,
    );
  }
  const choose = async (type = "image/jpeg") => {
    const input = screen.getByTestId("photo-file-input");
    await act(async () => {
      fireEvent.change(input, { target: { files: [new File(["x"], "w.jpg", { type })] } });
    });
  };

  it("has no camera without a course to read the photo for", () => {
    mountPhoto(photoDeps("x"), false);
    expect(screen.queryByRole("button", { name: "Joindre une photo de mon travail" })).toBeNull();
  });

  it("puts what was read in the field, to be corrected, with the sentence that frames it", async () => {
    const deps = photoDeps("$2x = 8$\n$x = [incertain: 4 | 9]$");
    mountPhoto(deps);
    await choose();
    expect(deps.read).toHaveBeenCalledWith("c1", expect.any(Blob), expect.any(AbortSignal));
    const field = screen.getByLabelText("Message pour Célestin") as HTMLTextAreaElement;
    expect(field.value).toBe(
      "Voici mon travail, lu sur ma photo :\n$2x = 8$\n$x = [incertain: 4 | 9]$",
    );
    // She is told to read it again: it is her message, not the model's.
    expect(screen.getByText(/Relis ce que j'ai lu/)).toBeTruthy();
  });

  it("adds to what she had already typed", async () => {
    mountPhoto(photoDeps("$x = 4$"));
    const field = screen.getByLabelText("Message pour Célestin") as HTMLTextAreaElement;
    fireEvent.change(field, { target: { value: "Je ne suis pas sûre." } });
    await choose();
    expect(field.value).toBe(
      "Je ne suis pas sûre.\n\nVoici mon travail, lu sur ma photo :\n$x = 4$",
    );
  });

  it("says so when nothing could be read", async () => {
    mountPhoto(photoDeps(""));
    await choose();
    expect(screen.getByRole("alert").textContent).toMatch(/Je n'ai rien lu sur cette photo/);
    expect((screen.getByLabelText("Message pour Célestin") as HTMLTextAreaElement).value).toBe("");
  });

  it("refuses a file that is not a picture", async () => {
    const deps = photoDeps("x");
    mountPhoto(deps);
    await choose("application/pdf");
    expect(screen.getByRole("alert").textContent).toMatch(/Choisis une photo/);
    expect(deps.read).not.toHaveBeenCalled();
  });
});

describe("TutorColumn lost session (004 R4.4.4)", () => {
  it("offers a sign-in link on a not_authenticated error", () => {
    mount(controls(), [
      { id: "1", role: "error", text: "Connecte-toi pour continuer.", code: "not_authenticated" },
    ]);
    const link = screen.getByRole("link", { name: "Se connecter" }) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toMatch(/^\/login\?redirect=/);
  });
});
