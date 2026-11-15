/**
 * The screen a stored conversation is worked in: a discussion (spec 007) or a révision
 * (spec 020). The tutor column and the board, the lesson's own, without the strip, the map
 * or the page-turn button: nothing said here can move the path. The two modes differ by
 * their session (query, transport), their header actions and what sits under the composer;
 * the frame, the cards and the way a picked option becomes a learner message are this file.
 */

import { SquarePen } from "lucide-react";
import { useCallback, type ReactNode } from "react";

import { useCompactLayout } from "@/components/celestin/compact-layout";
import { ConfirmDialog } from "@/components/celestin/confirm-dialog";
import { iconButton } from "@/components/celestin/styles";
import { TutorBoardSplit } from "@/components/celestin/tutor-board-split";
import { TutorColumn } from "@/components/celestin/tutor-column";
import type { TutorSession } from "@/components/celestin/use-tutor-session";
import type { VoiceControls } from "@/components/celestin/use-voice-session";
import { Whiteboard } from "@/components/celestin/whiteboard";
import { useHealth } from "@/lib/tutor/health";
import { useLearnerSentences } from "@/lib/tutor/prompts";
import type { Option, SubjectId } from "@/lib/tutor/types";
import { cn } from "@/lib/utils";

export function ConversationScreen({
  session,
  voice,
  courseId,
  subject,
  headerAction,
  composerFooter,
  top,
}: {
  session: TutorSession;
  /** The call's controls; absent in a mode without voice (a révision, spec 020 D5). */
  voice?: VoiceControls;
  /** The course the photo of her work is read for. */
  courseId: string;
  subject: SubjectId;
  headerAction?: ReactNode;
  composerFooter?: ReactNode;
  /** A phone's line above the board. */
  top?: ReactNode;
}) {
  const said = useLearnerSentences();
  const health = useHealth();
  const send = voice && voice.phase !== "off" ? voice.sendText : session.send;
  const onAnswer = useCallback((option: Option) => send(said.answer(option.text)), [send, said]);

  const tutor = (
    <TutorColumn
      entries={session.entries}
      status={session.status}
      {...(voice ? { voice } : {})}
      onSend={send}
      onCancel={session.cancel}
      onRetry={session.retry}
      onShowBoard={session.showBoard}
      dictation={health.data?.dictation === true}
      courseId={courseId}
      mixedLanguages={subject === "languages"}
      headerAction={headerAction}
      composerFooter={composerFooter}
    />
  );
  const board = (
    <Whiteboard
      card={session.board}
      cards={session.boards}
      onSelect={session.showBoard}
      onAnswer={onAnswer}
    />
  );

  return (
    <div className="h-full min-h-0 w-full bg-paper">
      <TutorBoardSplit tutor={tutor} board={board} top={top} />
    </div>
  );
}

/** A panel's one line while it loads, or after it failed. */
export function PanelMessage({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
      <p>{children}</p>
    </div>
  );
}

/** Starts over, after saying what is closed and what is kept: « Nouvelle conversation »,
 *  « Nouvelle révision ». The tutor header's icon, confirmed first. */
export function NewSessionButton({
  label,
  title,
  description,
  onConfirm,
  disabled = false,
}: {
  label: string;
  title: string;
  description: string;
  onConfirm: () => void;
  disabled?: boolean;
}) {
  const compact = useCompactLayout();
  return (
    <ConfirmDialog
      trigger={
        <button
          type="button"
          title={label}
          aria-label={label}
          className={cn(iconButton, compact && "size-10")}
          disabled={disabled}
        >
          <SquarePen className="size-4" />
        </button>
      }
      title={title}
      description={description}
      confirm={label}
      onConfirm={onConfirm}
    />
  );
}

/** A phone's line above the board: what this conversation is about. `lang` when it is
 *  course text (a chapter's title). */
export function PhoneTitle({ children, lang }: { children: ReactNode; lang?: string }) {
  return (
    <p lang={lang} className="truncate px-3 py-2 text-sm font-semibold">
      {children}
    </p>
  );
}
