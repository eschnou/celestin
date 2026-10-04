import { useCallback, useLayoutEffect, useRef, type ReactNode } from "react";
import { Loader2, RotateCcw } from "lucide-react";
import celestinMark from "@/assets/celestin-mark.svg";
import { statusLabel } from "@/lib/tutor/labels";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";
import { useCompactLayout } from "./compact-layout";
import { Composer } from "./composer";
import { CallButton } from "./call-button";
import type { DictationDeps } from "./use-dictation";
import type { PhotoDeps } from "./use-photo-work";
import type { WebcamDeps } from "./webcam-camera";
import { Countdown, Entry } from "./transcript";
import { TutorCaption } from "./tutor-caption";
import type { SessionStatus } from "./use-tutor-session";
import type { VoiceControls } from "./use-voice-session";
import type { TranscriptEntry } from "@/lib/tutor/types";

type TutorColumnProps = {
  entries: TranscriptEntry[];
  status: SessionStatus;
  /** Voice controls (003). `supported` false keeps the mic inert. */
  voice: VoiceControls;
  onSend: (text: string) => void;
  onCancel: () => void;
  onRetry: () => void;
  onShowBoard: (index: number) => void;
  /** The position strip and the chapter map, under the header. A discussion passes
   *  none: nothing said there can move the path, so showing it would imply otherwise
   *  (007 R6.3). On a small screen the frame mounts it above the board instead. */
  path?: ReactNode;
  /** Mode-specific controls in the header, before the call button. */
  headerAction?: ReactNode;
  /** The backend offers dictation: the composer's microphone (`/api/health`). */
  dictation?: boolean;
  /** The browser's microphone and the transcription, replaced in tests. */
  dictationDeps?: DictationDeps;
  /** The chapter mixes two languages (a language course): no language hint for dictation. */
  mixedLanguages?: boolean;
  /** The course the photo of her work is read for: gives the composer its camera. */
  courseId?: string;
  photoDeps?: PhotoDeps;
  webcamDeps?: WebcamDeps;
};

function TutorHeader({
  status,
  voice,
  action,
}: {
  status: SessionStatus;
  voice: VoiceControls;
  action?: ReactNode;
}) {
  const label = statusLabel(status, voice);
  const live = voice.phase !== "off";
  return (
    <div className="flex items-center gap-2.5 border-b border-border px-4 py-3">
      <img src={celestinMark} alt="" className="size-8" />
      <div className="min-w-0 leading-tight">
        <p className="text-sm font-bold">{m.lesson_tutor_name()}</p>
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span
            className={cn(
              "size-1.5 rounded-full",
              status === "error"
                ? "bg-destructive"
                : live && voice.phase === "speaking"
                  ? "bg-primary"
                  : "bg-success",
            )}
          />
          {label}
          {live && voice.capAt !== null && <Countdown capAt={voice.capAt} />}
        </p>
      </div>
      <div className="ml-auto flex items-center gap-1">
        {action}
        <CallButton voice={voice} status={status} className="size-8" />
      </div>
    </div>
  );
}

export function TutorColumn({
  entries,
  status,
  voice,
  onSend,
  onCancel,
  onRetry,
  onShowBoard,
  path,
  headerAction,
  dictation = false,
  dictationDeps,
  mixedLanguages = false,
  courseId,
  photoDeps,
  webcamDeps,
}: TutorColumnProps) {
  const compact = useCompactLayout();
  const composer = (
    <Composer
      status={status}
      voice={voice}
      onSend={onSend}
      onCancel={onCancel}
      dictation={dictation}
      {...(dictationDeps ? { dictationDeps } : {})}
      mixedLanguages={mixedLanguages}
      {...(courseId ? { courseId } : {})}
      {...(photoDeps ? { photoDeps } : {})}
      {...(webcamDeps ? { webcamDeps } : {})}
    />
  );
  const streaming = status === "streaming";
  const voiceOn = voice.phase !== "off";

  const scrollRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);

  /** Follow the newest message, but stop the moment the learner scrolls up. */
  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
  }, []);

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el && stickRef.current) el.scrollTop = el.scrollHeight;
  }, [entries]);

  /* Announced without re-reading the whole transcript on every chunk. */
  const announce = (
    <p className="sr-only" role="status" aria-live="polite">
      {voiceOn
        ? statusLabel(status, voice)
        : streaming
          ? m.lesson_a11y_answering()
          : m.lesson_a11y_done()}
    </p>
  );

  /* A small screen: the board has the room, so the talk is a caption and the composer. */
  if (compact) {
    return (
      <section className="bg-background">
        <TutorCaption
          entries={entries}
          status={status}
          voice={voice}
          onRetry={onRetry}
          onShowBoard={onShowBoard}
          action={headerAction}
        />
        {announce}
        {composer}
      </section>
    );
  }

  return (
    <section className="flex h-full min-h-0 flex-col bg-background">
      <TutorHeader status={status} voice={voice} action={headerAction} />

      {path && <div className="px-4 pt-3">{path}</div>}

      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="min-h-0 flex-1 space-y-3.5 overflow-y-auto px-4 py-4"
      >
        {entries.map((entry) => (
          <Entry key={entry.id} entry={entry} onShowBoard={onShowBoard} />
        ))}

        {streaming && entries.at(-1)?.role !== "tutor" && (
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="size-3 animate-spin" /> {m.lesson_thinking()}
          </p>
        )}

        {status === "error" && !voiceOn && (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-sm font-semibold transition-colors hover:bg-secondary"
          >
            <RotateCcw className="size-3.5" /> {m.error_retry()}
          </button>
        )}
      </div>

      {announce}

      {composer}
    </section>
  );
}
