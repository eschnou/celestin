import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Mic, MicOff, Send, Square } from "lucide-react";

import { useCompactLayout } from "@/components/celestin/compact-layout";
import { PhotoButton } from "@/components/celestin/photo-button";
import {
  usePhotoWork,
  type PhotoDeps,
  type PhotoError,
} from "@/components/celestin/use-photo-work";
import type { WebcamDeps } from "@/components/celestin/webcam-camera";
import {
  useDictation,
  type DictationDeps,
  type DictationError,
} from "@/components/celestin/use-dictation";
import type { SessionStatus } from "@/components/celestin/use-tutor-session";
import type { VoiceControls } from "@/components/celestin/use-voice-session";
import { useCourseLanguage } from "@/lib/course-language";
import { apiMessage } from "@/lib/tutor/client";
import { useLearnerSentences } from "@/lib/tutor/prompts";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";

const PALETTE = ["√", "π", "²", "ⁿ", "⁄", "]", "[", ";", "∞", "≤", "≥", "≠", "∅", "∪"];

/** The sentence under the field for a take that gave nothing. */
function dictationMessage(error: DictationError): string {
  switch (error.kind) {
    case "denied":
      return m.lesson_dictation_denied();
    case "empty":
      return m.lesson_dictation_empty();
    case "failed":
      return apiMessage(error.cause, m.lesson_dictation_failed());
  }
}

/** The sentence under the field for a photo that gave nothing. */
function photoMessage(error: PhotoError): string {
  switch (error.kind) {
    case "not-image":
      return m.lesson_photo_not_image();
    case "empty":
      return m.lesson_photo_empty();
    case "failed":
      return apiMessage(error.cause, m.lesson_photo_failed());
  }
}

/** The learner's line to Célestin: text, symbols, camera, dictation, send. Larger touch
 *  targets and a 16 px field on a small screen (below that, iOS zooms in on focus).
 *  The microphone here is dictation (a spoken take becomes written text in the field);
 *  talking with Célestin is the call button next to his name. During a call the
 *  microphone is the call's mute. */
export function Composer({
  status,
  voice,
  onSend,
  onCancel,
  dictation = false,
  dictationDeps,
  mixedLanguages = false,
  courseId,
  photoDeps,
  webcamDeps,
}: {
  status: SessionStatus;
  voice: VoiceControls;
  onSend: (text: string) => void;
  onCancel: () => void;
  /** The backend offers dictation (`/api/health`). */
  dictation?: boolean;
  /** The browser's microphone and the transcription, replaced in tests. */
  dictationDeps?: DictationDeps;
  /** The chapter mixes two languages (a language course): dictation gets no language hint. */
  mixedLanguages?: boolean;
  /** The course the photo of her work is read for (its language, its owner). Without it, no camera. */
  courseId?: string;
  photoDeps?: PhotoDeps;
  webcamDeps?: WebcamDeps;
}) {
  const compact = useCompactLayout();
  const language = useCourseLanguage();
  const said = useLearnerSentences();
  const [draft, setDraft] = useState("");
  const [focused, setFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const streaming = status === "streaming";
  const voiceOn = voice.phase !== "off";

  const dictate = useDictation({
    language: mixedLanguages ? null : language,
    // The text lands in the field to be read, fixed and sent: it is not sent for her.
    onText: (text) => setDraft((d) => (d.trim() ? `${d.trimEnd()} ${text}` : text)),
    suspended: voiceOn,
    ...(dictationDeps ? { deps: dictationDeps } : {}),
  });
  const dictating = dictate.phase !== "idle";

  // A photo of her work becomes text in the field, to be read and corrected before it is sent.
  const [photoNote, setPhotoNote] = useState(false);
  const photo = usePhotoWork({
    courseId: courseId ?? "",
    onText: (text) => {
      setDraft((d) => (d.trim() ? `${d.trimEnd()}\n\n${said.work(text)}` : said.work(text)));
      setPhotoNote(true);
    },
    ...(photoDeps ? { deps: photoDeps } : {}),
  });
  const reading = photo.phase === "reading";
  const { error: photoError, clearError: clearPhotoError } = photo;
  useEffect(() => {
    if (!photoError) return;
    const timer = setTimeout(clearPhotoError, 9000);
    return () => clearTimeout(timer);
  }, [photoError, clearPhotoError]);
  const { error: dictationError, clearError } = dictate;
  useEffect(() => {
    if (!dictationError) return;
    const timer = setTimeout(clearError, 7000);
    return () => clearTimeout(timer);
  }, [dictationError, clearError]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, compact ? 96 : 128)}px`;
  }, [draft, compact]);

  const submit = useCallback(() => {
    if (!draft.trim() || streaming) return;
    onSend(draft);
    setDraft("");
    setPhotoNote(false);
  }, [draft, onSend, streaming]);

  const icon = cn(
    "inline-flex items-center justify-center rounded-md transition-colors",
    compact ? "size-10" : "size-8",
  );
  const quiet = `${icon} text-muted-foreground hover:bg-secondary hover:text-foreground`;

  return (
    <div
      className={cn(
        "bg-background",
        compact
          ? "px-3 pt-2 pb-[max(0.75rem,env(safe-area-inset-bottom))]"
          : "border-t border-border px-4 pt-3 pb-4",
      )}
    >
      {focused && (
        <div
          className={cn(
            "panel-down mb-2 flex gap-1",
            compact ? "-mx-3 overflow-x-auto px-3" : "flex-wrap",
          )}
        >
          {PALETTE.map((sym) => (
            <button
              key={sym}
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => setDraft((d) => d + sym)}
              className={cn(
                "shrink-0 rounded-md border border-border bg-card text-foreground transition-colors hover:bg-secondary",
                compact ? "size-9 text-base" : "size-7 text-sm",
              )}
            >
              {sym}
            </button>
          ))}
        </div>
      )}
      {(dictationError || photoError) && (
        <p role="alert" className="mb-1.5 text-xs text-destructive">
          {photoError
            ? photoMessage(photoError)
            : dictationError
              ? dictationMessage(dictationError)
              : null}
        </p>
      )}
      {photoNote && !photoError && (
        <p className="mb-1.5 text-xs text-muted-foreground">{m.lesson_photo_hint()}</p>
      )}
      <p className="sr-only" role="status" aria-live="polite">
        {dictate.phase === "listening"
          ? m.lesson_dictation_listening()
          : dictate.phase === "transcribing"
            ? m.lesson_dictation_transcribing()
            : ""}
      </p>
      <div className="flex items-end gap-1 rounded-lg border border-input bg-card p-1.5 focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/25">
        <textarea
          ref={textareaRef}
          rows={1}
          value={draft}
          disabled={streaming}
          onChange={(e) => setDraft(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={
            reading
              ? m.lesson_photo_reading()
              : dictate.phase === "starting"
                ? m.lesson_dictation_starting()
                : dictate.phase === "listening"
                  ? m.lesson_dictation_listening()
                  : dictate.phase === "transcribing"
                    ? m.lesson_dictation_transcribing()
                    : streaming
                      ? m.lesson_placeholder_streaming()
                      : voiceOn
                        ? m.lesson_placeholder_voice()
                        : m.lesson_placeholder()
          }
          aria-label={m.lesson_message_label()}
          className={cn(
            "max-h-32 flex-1 resize-none bg-transparent px-2 py-1.5 outline-none placeholder:text-muted-foreground disabled:opacity-60",
            compact ? "min-h-10 text-base" : "min-h-8 text-sm",
          )}
        />
        {courseId && (
          <PhotoButton
            onPhoto={photo.read}
            busy={reading}
            disabled={streaming}
            className={quiet}
            {...(webcamDeps ? { webcamDeps } : {})}
          />
        )}
        {voiceOn ? (
          <button
            type="button"
            onClick={voice.toggleMute}
            aria-pressed={voice.muted}
            title={voice.muted ? m.voice_unmute() : m.voice_mute()}
            aria-label={voice.muted ? m.voice_unmute() : m.voice_mute()}
            className={cn(
              icon,
              "hover:bg-secondary",
              voice.muted ? "text-warning" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {voice.muted ? <MicOff className="size-4" /> : <Mic className="size-4" />}
          </button>
        ) : (
          dictation &&
          dictate.supported && (
            <DictationButton
              phase={dictate.phase}
              level={dictate.level}
              className={icon}
              quiet={quiet}
              disabled={streaming && !dictating}
              onClick={dictate.toggle}
            />
          )
        )}
        {streaming ? (
          <button
            type="button"
            onClick={onCancel}
            title={m.lesson_stop_title()}
            aria-label={m.lesson_stop_label()}
            className={cn(icon, "bg-secondary text-foreground hover:opacity-90")}
          >
            <Square className="size-3.5" />
          </button>
        ) : (
          <button
            type="button"
            onClick={submit}
            disabled={!draft.trim()}
            title={m.lesson_send()}
            aria-label={m.lesson_send()}
            className={cn(
              icon,
              "bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-40",
            )}
          >
            <Send className="size-4" />
          </button>
        )}
      </div>
    </div>
  );
}

/** The microphone: a tap to start, a tap to finish (a take also ends when she stops talking), a tap to give
 *  up while it is being transcribed. The ring around it breathes with her voice. */
function DictationButton({
  phase,
  level,
  className,
  quiet,
  disabled,
  onClick,
}: {
  phase: "idle" | "starting" | "listening" | "transcribing";
  level: number;
  className: string;
  quiet: string;
  disabled: boolean;
  onClick: () => void;
}) {
  const label =
    phase === "idle"
      ? m.lesson_dictation_start()
      : phase === "listening"
        ? m.lesson_dictation_stop()
        : m.lesson_dictation_cancel();
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      aria-pressed={phase === "listening"}
      style={
        phase === "listening"
          ? {
              boxShadow: `0 0 0 ${Math.round(level * 8)}px color-mix(in oklab, var(--color-destructive) 25%, transparent)`,
            }
          : undefined
      }
      className={cn(
        phase === "idle" ? quiet : `${className} bg-destructive/10 text-destructive`,
        "transition-shadow duration-100 disabled:opacity-40",
      )}
    >
      {phase === "listening" ? (
        <Square className="size-3.5" fill="currentColor" />
      ) : phase === "idle" ? (
        <Mic className="size-4" />
      ) : (
        <Loader2 className="size-4 animate-spin" />
      )}
    </button>
  );
}
