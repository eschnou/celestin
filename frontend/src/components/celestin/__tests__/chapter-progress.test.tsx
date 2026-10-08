// @vitest-environment jsdom
/** What a running preparation shows (spec 016 R5): the stage, the characters received, the slow notice. */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChapterRow } from "@/lib/tutor/types";
import { withLocale } from "@/test/locale";
import { ChapterStateCard } from "../chapter-state-card";
import { isSlow, preparingDetail, preparingLabel, SLOW_AFTER_S } from "../chapter-row";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, ...rest }: { children: React.ReactNode }) => <a {...rest}>{children}</a>,
}));

afterEach(cleanup);

const row = (over: Partial<ChapterRow> = {}): ChapterRow => ({
  id: "h1",
  position: 1,
  title: null,
  ready: false,
  section_count: 0,
  done_count: 0,
  state: "not_started",
  last: false,
  authoring_state: "generating",
  authoring_message: null,
  authoring_stage: "pack",
  pages_done: 12,
  page_count: 12,
  authoring_received_chars: 0,
  authoring_quiet_s: 1,
  ...over,
});

const card = (r: ChapterRow) =>
  render(<ChapterStateCard courseId="c1" row={r} onRetry={() => {}} error={null} />);

describe("preparingLabel", () => {
  it("names the stage", () => {
    expect(preparingLabel(row({ authoring_stage: "transcription", pages_done: 4 }))).toBe(
      "Lecture des pages… (4/12)",
    );
    expect(preparingLabel(row({ authoring_stage: "pack" }))).toBe("Rédaction du chapitre…");
    expect(preparingLabel(row({ authoring_stage: "curriculum" }))).toBe(
      "Construction du parcours…",
    );
    expect(preparingLabel(row({ authoring_stage: null }))).toBe("En préparation…");
  });

  it("names it in English under an English interface", () =>
    withLocale("en", () => {
      expect(preparingLabel(row({ authoring_stage: "pack" }))).toBe("Writing the chapter…");
      expect(preparingLabel(row({ authoring_stage: "curriculum" }))).toBe("Building the path…");
      expect(preparingLabel(row({ authoring_stage: null }))).toBe("Preparing…");
    }));
});

describe("preparingDetail", () => {
  it("adds the count while the pack or the path is written, grouped as the interface groups numbers", () => {
    const fr = preparingDetail(row({ authoring_received_chars: 12400 }));
    expect(fr.replace(/\s/g, " ")).toBe("Rédaction du chapitre… 12 400 caractères reçus");
    expect(
      preparingDetail(row({ authoring_stage: "curriculum", authoring_received_chars: 1 })),
    ).toContain("1 caractère reçu");
  });

  it("groups them the English way under an English interface", () =>
    withLocale("en", () => {
      expect(preparingDetail(row({ authoring_received_chars: 12400 }))).toBe(
        "Writing the chapter… 12,400 characters received",
      );
    }));

  it("shows no count before anything arrived, nor while pages are read", () => {
    expect(preparingDetail(row({ authoring_received_chars: 0 }))).toBe("Rédaction du chapitre…");
    expect(
      preparingDetail(
        row({ authoring_stage: "transcription", authoring_received_chars: 500, pages_done: 2 }),
      ),
    ).toBe("Lecture des pages… (2/12)");
  });
});

describe("isSlow", () => {
  it("is true from 45 s without movement, and only while generating", () => {
    expect(SLOW_AFTER_S).toBe(45);
    expect(isSlow(row({ authoring_quiet_s: 44 }))).toBe(false);
    expect(isSlow(row({ authoring_quiet_s: 45 }))).toBe(true);
    expect(isSlow(row({ authoring_quiet_s: null }))).toBe(false);
    expect(isSlow(row({ authoring_state: "failed", authoring_quiet_s: 300 }))).toBe(false);
  });
});

describe("the preparation card", () => {
  it("shows the stage and the count in the polite live region", () => {
    card(row({ authoring_received_chars: 12400 }));
    const live = document.querySelector("[aria-live='polite']");
    expect(live?.textContent?.replace(/\s/g, " ")).toContain(
      "Rédaction du chapitre… 12 400 caractères reçus",
    );
    expect(screen.queryByText("Toujours en cours, le service est lent.")).toBeNull();
  });

  it("adds the slow notice in the same live region once nothing has moved for 45 s", () => {
    card(row({ authoring_quiet_s: 50 }));
    const notice = screen.getByText("Toujours en cours, le service est lent.");
    expect(notice.closest("[aria-live='polite']")).not.toBeNull();
  });

  it("says it in English, and not at 44 s", () =>
    withLocale("en", () => {
      card(row({ authoring_quiet_s: 44 }));
      expect(screen.queryByText("Still working, the service is slow.")).toBeNull();
      cleanup();
      card(row({ authoring_quiet_s: 46 }));
      expect(screen.getByText("Still working, the service is slow.")).toBeTruthy();
    }));

  it("keeps the page-reading hint while the pages are read", () => {
    card(row({ authoring_stage: "transcription", pages_done: 4 }));
    expect(screen.getByText(/Lecture des pages… \(4\/12\)/)).toBeTruthy();
  });

  it("shows no slow notice on a failed preparation", () => {
    card(row({ authoring_state: "failed", authoring_message: "Échec", authoring_quiet_s: 99 }));
    expect(screen.queryByText("Toujours en cours, le service est lent.")).toBeNull();
  });
});
