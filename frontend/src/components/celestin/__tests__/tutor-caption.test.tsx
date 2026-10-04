// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TutorCaption } from "../tutor-caption";
import type { SessionStatus } from "../use-tutor-session";
import type { VoiceControls } from "../use-voice-session";
import type { TranscriptEntry } from "@/lib/tutor/types";

const VOICE: VoiceControls = {
  phase: "off",
  muted: false,
  capAt: null,
  supported: true,
  start: vi.fn(async () => {}),
  stop: vi.fn(),
  toggleMute: vi.fn(),
  sendText: vi.fn(),
};

const SAID: TranscriptEntry[] = [
  { id: "1", role: "tutor", text: "Une suite est une liste ordonnée.", blockId: 0 },
  { id: "2", role: "marker", text: "exemple posé", boardIndex: 0 },
  { id: "3", role: "learner", text: "d'accord" },
  { id: "4", role: "tutor", text: "Voyons un exemple.", blockId: 1 },
];

function mount(
  entries: TranscriptEntry[],
  status: SessionStatus = "idle",
  props: { onRetry?: () => void; onShowBoard?: (i: number) => void } = {},
) {
  render(
    <TutorCaption
      entries={entries}
      status={status}
      voice={VOICE}
      onRetry={props.onRetry ?? vi.fn()}
      onShowBoard={props.onShowBoard ?? vi.fn()}
    />,
  );
}

afterEach(cleanup);

describe("TutorCaption", () => {
  it("shows only Célestin's last message", () => {
    mount(SAID);
    expect(screen.getByText("Voyons un exemple.")).toBeTruthy();
    expect(screen.queryByText("Une suite est une liste ordonnée.")).toBeNull();
    expect(screen.queryByText("d'accord")).toBeNull();
  });

  it("shows no caption before Célestin has spoken, only the call button", () => {
    mount([]);
    expect(screen.queryByRole("button", { name: /conversation/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Appeler Célestin" })).toBeTruthy();
  });

  it("calls Célestin, and hangs up during a call", () => {
    const start = vi.fn(async () => {});
    const stop = vi.fn();
    const { rerender } = render(
      <TutorCaption
        entries={SAID}
        status="idle"
        voice={{ ...VOICE, start }}
        onRetry={vi.fn()}
        onShowBoard={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Appeler Célestin" }));
    expect(start).toHaveBeenCalledOnce();
    rerender(
      <TutorCaption
        entries={SAID}
        status="idle"
        voice={{ ...VOICE, phase: "listening", stop }}
        onRetry={vi.fn()}
        onShowBoard={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Raccrocher" }));
    expect(stop).toHaveBeenCalledOnce();
  });

  it("says he is thinking while the learner's line waits for an answer", () => {
    mount([{ id: "1", role: "learner", text: "d'accord" }], "streaming");
    expect(screen.getByText(/Célestin écrit/)).toBeTruthy();
    expect(screen.queryByText("d'accord")).toBeNull();
  });

  it("keeps his last message beside a failure, with a retry", () => {
    const onRetry = vi.fn();
    mount([...SAID, { id: "5", role: "error", text: "Célestin est très sollicité." }], "error", {
      onRetry,
    });
    expect(screen.getByText("Voyons un exemple.")).toBeTruthy();
    expect(screen.getByText("Célestin est très sollicité.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("ignores a failure older than what he said since", () => {
    mount([{ id: "0", role: "error", text: "Ancienne erreur." }, ...SAID]);
    expect(screen.queryByText("Ancienne erreur.")).toBeNull();
  });

  it("opens the whole conversation, and a board marker closes it and shows the card", async () => {
    const onShowBoard = vi.fn();
    mount(SAID, "idle", { onShowBoard });
    fireEvent.click(
      screen.getByRole("button", { name: "Voir toute la conversation avec Célestin" }),
    );
    expect(await screen.findByRole("dialog")).toBeTruthy();
    expect(screen.getByText("Une suite est une liste ordonnée.")).toBeTruthy();
    expect(screen.getByText("d'accord")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /exemple posé/ }));
    expect(onShowBoard).toHaveBeenCalledWith(0);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
