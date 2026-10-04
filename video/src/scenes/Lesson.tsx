import React from "react";
import { Sequence, useCurrentFrame, useVideoConfig } from "remotion";
import celestinMark from "@/assets/celestin-mark.svg";
import { ChapterStrip } from "@/components/celestin/chapter-strip";
import { Composer } from "@/components/celestin/composer";
import { Entry } from "@/components/celestin/transcript";
import { Whiteboard } from "@/components/celestin/whiteboard";
import { statusLabel } from "@/lib/tutor/labels";
import { m } from "@/paraglide/messages";
import type { BoardCard, Progress, TranscriptEntry } from "@/lib/tutor/types";
import { Scrub } from "../lib/Scrub";
import { OUT, rise } from "../lib/ease";
import { BOARD_BEATS, CHAPTER, LESSON_LINES, PROGRESS_AT } from "../lib/data";
import { typedPrefix } from "../lib/ui";

const NOOP = () => {};
const VOICE_OFF = {
  phase: "off" as const,
  muted: false,
  capAt: null,
  supported: false,
  start: async () => {},
  stop: NOOP,
  toggleMute: NOOP,
  sendText: NOOP,
};

/** The slim bar above the lesson, as the product draws it. */
export const LessonBar: React.FC = () => (
  <div className="flex items-center gap-3 border-b border-border bg-background px-4 py-1.5 text-xs">
    <span className="text-muted-foreground">← Mathématiques 5e</span>
    <span className="text-muted-foreground">·</span>
    <span className="truncate font-semibold">{CHAPTER.title}</span>
    <span className="rounded border border-border px-1.5 text-xs text-muted-foreground">
      Français
    </span>
    <span className="ml-auto flex rounded-md bg-secondary p-0.5 text-xs font-semibold">
      <span className="rounded bg-background px-2.5 py-0.5 shadow-sheet">Parcours</span>
      <span className="px-2.5 py-0.5 text-muted-foreground">Discussion</span>
    </span>
  </div>
);

function progressAt(t: number): Progress {
  if (t >= 23.8) return PROGRESS_AT.end;
  if (t >= 17.2) return { done: ["s1", "s2"], active: "s3" };
  return PROGRESS_AT.mid;
}

/** The tutor column: header, position strip, the conversation, the composer. */
const TutorPane: React.FC<{ t: number }> = ({ t }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const entries = LESSON_LINES.filter((line) => t >= line.at);
  const writing = LESSON_LINES.some(
    (line) => line.typed && t >= line.at && t < line.at + line.typed,
  );
  return (
    <section className="flex h-full min-h-0 flex-col bg-background">
      <div className="flex items-center gap-2.5 border-b border-border px-4 py-3">
        <img src={celestinMark} alt="" className="size-8" />
        <div className="min-w-0 leading-tight">
          <p className="text-sm font-bold">{m.lesson_tutor_name()}</p>
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className="size-1.5 rounded-full bg-success" />
            {statusLabel(writing ? "streaming" : "idle", VOICE_OFF)}
          </p>
        </div>
      </div>
      <div className="px-4 pt-3">
        <ChapterStrip chapter={CHAPTER} progress={progressAt(t)} onOpen={NOOP} />
      </div>
      <div
        className="flex min-h-0 flex-1 flex-col justify-end gap-3.5 overflow-hidden px-4 py-4"
        style={{ maskImage: "linear-gradient(to bottom, transparent 0, black 36px)" }}
      >
        {entries.map((line) => {
          const age = frame - line.at * fps;
          const p = rise(age, 0, 14, OUT);
          const entry: TranscriptEntry =
            line.entry.role === "tutor" && line.typed
              ? { ...line.entry, text: typedPrefix(line.entry.text, (t - line.at) / line.typed) }
              : line.entry;
          return (
            <div key={line.entry.id} style={{ opacity: p, transform: `translateY(${(1 - p) * 10}px)` }}>
              <Entry entry={entry} onShowBoard={NOOP} />
            </div>
          );
        })}
      </div>
      <Composer status="idle" voice={VOICE_OFF} onSend={NOOP} onCancel={NOOP} dictation />
    </section>
  );
};

/** The whiteboard: one fresh board per card, so each card's own CSS animation plays. */
const BoardPane: React.FC<{ total: number }> = ({ total }) => {
  const { fps } = useVideoConfig();
  const beats = BOARD_BEATS.map((beat) => ({ ...beat, from: Math.round(beat.at * fps) }));
  const shown = (i: number): BoardCard[] => beats.slice(0, i + 1).map((b) => b.card);
  return (
    <div className="relative h-full">
      <Sequence from={0} durationInFrames={beats[0]!.from}>
        <Scrub>
          <div className="h-full w-full">
            <Whiteboard card={null} cards={[]} onSelect={NOOP} />
          </div>
        </Scrub>
      </Sequence>
      {beats.map((beat, i) => (
        <Sequence
          key={i}
          from={beat.from}
          durationInFrames={(beats[i + 1]?.from ?? total) - beat.from}
        >
          <BoardAt cards={shown(i)} kind={beat.card.kind} />
        </Sequence>
      ))}
    </div>
  );
};

const BoardAt: React.FC<{ cards: BoardCard[]; kind: BoardCard["kind"] }> = ({ cards, kind }) => {
  const frame = useCurrentFrame();
  const card = cards[cards.length - 1]!;
  const ready = frame > 70 && (kind === "explanation" || kind === "worked_example");
  return (
    <Scrub>
      <div className="h-full w-full">
        <Whiteboard
          card={card}
          cards={cards}
          onSelect={NOOP}
          nextStep={ready ? { kind: "step" } : null}
          onNextStep={kind === "recap" ? undefined : NOOP}
        />
      </div>
    </Scrub>
  );
};

export const LESSON_LOGICAL = { width: 1280, height: 644 };

/** The inside of the lesson window; the caller places and scales it. */
export const LessonInside: React.FC<{ total: number }> = ({ total }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  return (
    <>
      <LessonBar />
      <div className="flex min-h-0 flex-1">
        <div className="min-h-0 border-r border-border" style={{ width: "35%" }}>
          <TutorPane t={t} />
        </div>
        <div className="min-h-0 flex-1">
          <BoardPane total={total} />
        </div>
      </div>
    </>
  );
};
