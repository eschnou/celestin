// @vitest-environment jsdom
/** The tutor's own words, markers and board chrome in both interface languages (spec 010 R3). */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { statusLabel } from "@/lib/tutor/labels";
import type { BoardCard, TranscriptEntry } from "@/lib/tutor/types";
import { withLocale } from "@/test/locale";
import { CardView, Whiteboard } from "../whiteboard";
import { TutorColumn } from "../tutor-column";
import { EMPTY_SESSION, reduce, type SessionEvent, type SessionState } from "../use-tutor-session";
import type { VoiceControls } from "../use-voice-session";

const play = (events: SessionEvent[], from: SessionState = EMPTY_SESSION) =>
  events.reduce(reduce, from);
const texts = (state: SessionState) => state.entries.map((entry) => entry.text);

describe("the session reducer's own text", () => {
  it("writes the voice markers and notices in French by default", () => {
    const state = play([
      { event: "voice.on" },
      { event: "voice.off", reason: "cap" },
      { event: "turn.end", reason: "max_rounds", usage: {} },
    ]);
    expect(texts(state)).toEqual([
      "séance vocale",
      "fin de la séance vocale : temps écoulé",
      "Célestin s'est emballé et son tour a été interrompu. Relance-le si besoin.",
    ]);
  });

  it("writes them in English when the event is applied under en", () =>
    withLocale("en", () => {
      const state = play([
        { event: "voice.on" },
        { event: "voice.off", reason: "idle" },
        { event: "voice.off", reason: "error" },
        { event: "turn.end", reason: "max_rounds", usage: {} },
      ]);
      expect(texts(state)).toEqual([
        "voice session",
        "voice session ended: long silence",
        "voice connection lost",
        "Célestin went on for too long and the answer was cut short. Ask again if you need to.",
      ]);
    }));

  it("keeps a server error and a server marker as received", () =>
    withLocale("en", () => {
      const state = play([
        { event: "board.clear", marker: "tableau effacé" },
        { event: "error", code: "overloaded", message: "Célestin est très sollicité." },
      ]);
      expect(texts(state)).toEqual(["tableau effacé", "Célestin est très sollicité."]);
    }));
});

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

function column(
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

describe("the tutor column in English", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(1_000_000_000);
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("labels the status line and the voice phases", () =>
    withLocale("en", () => {
      expect(statusLabel("idle", controls())).toBe("in session");
      expect(statusLabel("error", controls())).toBe("offline");
      expect(statusLabel("streaming", controls())).toBe("Célestin is writing…");
      expect(statusLabel("idle", controls({ phase: "listening", muted: true }))).toBe("Mic muted");
      expect(statusLabel("idle", controls({ phase: "working" }))).toBe(
        "Célestin is writing on the board",
      );
      expect(statusLabel("idle", controls({ phase: "connecting" }))).toBe("Connecting…");
    }));

  it("words the voice controls and the composer", () =>
    withLocale("en", () => {
      column(controls({ phase: "speaking", capAt: Date.now() + 754_000 }));
      expect(screen.getAllByText("Célestin is speaking").length).toBeGreaterThan(0);
      expect(screen.getByText("· 12:34").getAttribute("title")).toBe(
        "Time left in the voice session",
      );
      expect(screen.getByRole("button", { name: "Mute the microphone" })).toBeTruthy();
      expect(screen.getByRole("button", { name: "Hang up" })).toBeTruthy();
      expect(screen.getByPlaceholderText("Write or talk to Célestin…")).toBeTruthy();
      expect(screen.getByRole("button", { name: "Send" })).toBeTruthy();
    }));

  it("words the unmute control when muted", () =>
    withLocale("en", () => {
      column(controls({ phase: "listening", muted: true }));
      expect(screen.getByRole("button", { name: "Unmute the microphone" })).toBeTruthy();
    }));

  it("marks Célestin's and the learner's words as French, and nothing else", () =>
    withLocale("en", () => {
      column(controls(), [
        { id: "1", role: "tutor", text: "Bonjour !", interrupted: true, spoken: true },
        { id: "2", role: "learner", text: "Bonjour Célestin", spoken: false },
        { id: "3", role: "marker", text: "exercice posé", boardIndex: null },
        { id: "4", role: "error", text: "Connecte-toi.", code: "not_authenticated" },
      ] as TranscriptEntry[]);
      const inFrench = (node: HTMLElement) => node.closest('[lang="fr"]') !== null;
      expect(inFrench(screen.getByText("Bonjour !"))).toBe(true);
      expect(inFrench(screen.getByText("Bonjour Célestin"))).toBe(true);
      expect(inFrench(screen.getByText(/exercice posé/))).toBe(false);
      expect(inFrench(screen.getByText(/Connecte-toi\./))).toBe(false);
      // The interface's own words inside Célestin's entry follow the interface.
      const interrupted = screen.getByText("(interrupted)");
      expect(interrupted.getAttribute("lang")).toBe("en");
      expect(screen.getByRole("link", { name: "Sign in" })).toBeTruthy();
      expect(screen.getByLabelText("said aloud").getAttribute("lang")).toBe("en");
    }));
});

describe("the board in English", () => {
  afterEach(cleanup);

  const RECAP: BoardCard = {
    kind: "recap",
    acquired: ["Lire $u_n$."],
    watch: ["Les indices."],
    next: "On passe aux sommes.",
  };
  const EXERCISE: BoardCard = {
    kind: "exercise",
    title: "Le manuel",
    statement: "Combien de pages ?",
    hint: "Compte les chapitres.",
  };

  it("words the empty board and the page-turn button, French card text stays", () =>
    withLocale("en", () => {
      render(<Whiteboard card={null} cards={[]} onSelect={() => {}} />);
      expect(screen.getByText("Board")).toBeTruthy();
      expect(screen.getByText("The board is empty. Célestin will write on it.")).toBeTruthy();
    }));

  it("words the history strip, the fixed headings and the next-step button", () =>
    withLocale("en", () => {
      const onNextStep = vi.fn();
      render(
        <Whiteboard
          card={RECAP}
          cards={[EXERCISE, RECAP]}
          onSelect={() => {}}
          nextStep={{ kind: "step" }}
          onNextStep={onNextStep}
        />,
      );
      // Strip: label and status are the board's, the title is Célestin's.
      expect(screen.getAllByText("Exercise").length).toBeGreaterThan(0);
      expect(screen.getAllByText("seen").length).toBe(2);
      expect(screen.getByText("Le manuel").getAttribute("lang")).toBe("fr");
      // The recap card: fixed words are English, the items are French.
      expect(screen.getAllByText("What to remember").length).toBeGreaterThan(0);
      expect(screen.getByText("Learned")).toBeTruthy();
      expect(screen.getByText("To watch")).toBeTruthy();
      expect(screen.getByText("Les indices.").closest('[lang="fr"]')).not.toBeNull();
      expect(screen.getByText("Learned").getAttribute("lang")).toBe("en");
      fireEvent.click(screen.getByRole("button", { name: "Next step" }));
      expect(onNextStep).toHaveBeenCalledOnce();
    }));

  it("says what the page-turn button waits for, and names the next section", () =>
    withLocale("en", () => {
      const view = render(
        <Whiteboard
          card={EXERCISE}
          cards={[EXERCISE]}
          onSelect={() => {}}
          nextStep={null}
          onNextStep={() => {}}
        />,
      );
      expect(screen.getByText("Célestin will tell you when to move on.")).toBeTruthy();
      expect(
        (screen.getByRole("button", { name: "Next step" }) as HTMLButtonElement).disabled,
      ).toBe(true);
      view.rerender(
        <Whiteboard
          card={EXERCISE}
          cards={[EXERCISE]}
          onSelect={() => {}}
          nextStep={{ kind: "section", sectionId: "s2" }}
          onNextStep={() => {}}
        />,
      );
      expect(screen.getByRole("button", { name: "Next section" })).toBeTruthy();
    }));

  it("words the hint label and a single definition", () =>
    withLocale("en", () => {
      render(<CardView card={EXERCISE} />);
      expect(screen.getByText("Hint")).toBeTruthy();
      expect(screen.getByText("Compte les chapitres.")).toBeTruthy();
    }));

  it("keeps the French words under the French interface", () => {
    render(<Whiteboard card={null} cards={[]} onSelect={() => {}} />);
    expect(screen.getByText("Tableau")).toBeTruthy();
    expect(screen.getByText("Le tableau est vide. Célestin va y écrire.")).toBeTruthy();
  });
});
