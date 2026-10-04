/**
 * Célestin on a small screen (015): the board has the room, so what he says is a
 * caption above the composer: his last message, a few lines of it. Tapping it
 * opens the whole conversation in a sheet. The status (voice, writing, offline)
 * and a failed turn's retry live here too.
 */

import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { ChevronUp, Loader2, RotateCcw } from "lucide-react";

import celestinMark from "@/assets/celestin-mark.svg";
import { RichText } from "@/components/celestin/board-blocks";
import { CallButton } from "@/components/celestin/call-button";
import { Countdown, Entry } from "@/components/celestin/transcript";
import type { SessionStatus } from "@/components/celestin/use-tutor-session";
import type { VoiceControls } from "@/components/celestin/use-voice-session";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useVisualViewport } from "@/hooks/use-visual-viewport";
import { useCourseLanguage } from "@/lib/course-language";
import { statusLabel } from "@/lib/tutor/labels";
import type { TranscriptEntry } from "@/lib/tutor/types";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";

/** What the caption shows: the last thing Célestin said, and a failure that came after it. */
function captionEntries(entries: TranscriptEntry[]): {
  said: TranscriptEntry | null;
  failure: TranscriptEntry | null;
} {
  let said: TranscriptEntry | null = null;
  for (let i = entries.length - 1; i >= 0; i--) {
    const entry = entries[i];
    if (entry?.role === "tutor") {
      said = entry;
      break;
    }
  }
  const failure = entries.filter((e) => e.role === "error").at(-1) ?? null;
  const after =
    said === null || (failure !== null && entries.indexOf(failure) > entries.indexOf(said));
  return { said, failure: after ? failure : null };
}

export function TutorCaption({
  entries,
  status,
  voice,
  onRetry,
  onShowBoard,
  action,
}: {
  entries: TranscriptEntry[];
  status: SessionStatus;
  voice: VoiceControls;
  onRetry: () => void;
  onShowBoard: (index: number) => void;
  /** Mode-specific control (a discussion's « Nouvelle conversation »). */
  action?: ReactNode;
}) {
  const language = useCourseLanguage();
  const { keyboardOpen } = useVisualViewport();
  const [open, setOpen] = useState(false);
  const live = voice.phase !== "off";
  const streaming = status === "streaming";
  const latest = entries.at(-1);
  // A turn in flight after the learner spoke: his words are not Célestin's yet.
  const waiting = streaming && latest?.role !== "tutor";
  const { said, failure } = waiting ? { said: null, failure: null } : captionEntries(entries);
  const label = live || status !== "idle" ? statusLabel(status, voice) : null;
  const hasCaption = said !== null || failure !== null || waiting || label !== null;

  return (
    <div className="px-3 pt-2">
      <div className="flex items-start gap-1">
        {hasCaption ? (
          <button
            type="button"
            onClick={() => setOpen(true)}
            disabled={entries.length === 0}
            aria-label={m.lesson_transcript_open()}
            className="flex min-h-10 min-w-0 flex-1 items-start gap-2.5 rounded-lg px-1 py-1.5 text-left transition-colors active:bg-secondary/60"
          >
            <img src={celestinMark} alt="" className="mt-0.5 size-6 shrink-0" />
            <span className="min-w-0 flex-1">
              {label && (
                <span
                  className={cn(
                    "mb-0.5 flex items-center gap-1.5 text-xs",
                    status === "error" ? "text-destructive" : "text-muted-foreground",
                  )}
                >
                  {waiting && <Loader2 className="size-3 animate-spin" />}
                  {label}
                  {live && voice.capAt !== null && <Countdown capAt={voice.capAt} />}
                </span>
              )}
              {waiting && !label && (
                <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Loader2 className="size-3 animate-spin" /> {m.lesson_thinking()}
                </span>
              )}
              {said && (
                <span
                  lang={language}
                  className={cn(
                    "block text-sm leading-snug text-foreground",
                    keyboardOpen ? "line-clamp-1" : "line-clamp-3",
                  )}
                >
                  <RichText text={said.text} />
                </span>
              )}
              {failure && (
                <span
                  className={cn(
                    "block text-sm leading-snug text-destructive",
                    said && "mt-1",
                    keyboardOpen ? "line-clamp-1" : "line-clamp-2",
                  )}
                >
                  {failure.text}
                </span>
              )}
            </span>
            {entries.length > 0 && (
              <ChevronUp className="mt-1 size-4 shrink-0 text-muted-foreground" aria-hidden />
            )}
          </button>
        ) : (
          <span className="flex-1" />
        )}
        {action}
        <CallButton voice={voice} status={status} className="size-10" />
      </div>
      {status === "error" && !live && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-1 ml-1 inline-flex min-h-10 items-center gap-1.5 rounded-md border border-border bg-card px-3 text-sm font-semibold transition-colors hover:bg-secondary"
        >
          <RotateCcw className="size-3.5" /> {m.error_retry()}
        </button>
      )}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="bottom" className="flex h-[80dvh] flex-col gap-0 rounded-t-xl p-0">
          <SheetHeader className="border-b border-border px-4 py-3 text-left">
            <SheetTitle className="text-base">{m.lesson_transcript_title()}</SheetTitle>
            <SheetDescription className="sr-only">
              {m.lesson_transcript_description()}
            </SheetDescription>
          </SheetHeader>
          <Transcript
            entries={entries}
            onShowBoard={(index) => {
              setOpen(false);
              onShowBoard(index);
            }}
          />
        </SheetContent>
      </Sheet>
    </div>
  );
}

/** The whole conversation, opened on its end. */
function Transcript({
  entries,
  onShowBoard,
}: {
  entries: TranscriptEntry[];
  onShowBoard: (index: number) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  // Once, on opening: the conversation is read from its end, then left where she scrolls it.
  useLayoutEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, []);
  return (
    <div ref={ref} className="min-h-0 flex-1 space-y-3.5 overflow-y-auto px-4 py-4">
      {entries.map((entry) => (
        <Entry key={entry.id} entry={entry} onShowBoard={onShowBoard} />
      ))}
    </div>
  );
}
