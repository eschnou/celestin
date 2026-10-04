/**
 * The chapter's top bar, the same in the lesson and on the discussion route:
 * which course (and the way back to it), which chapter, which of its two modes
 * is on screen, its content, who is signed in, the way out (005, 007).
 */

import { Link } from "@tanstack/react-router";
import { ArrowLeft, FileText } from "lucide-react";

import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { useIsDesktop } from "@/hooks/use-is-desktop";
import { iconButton } from "@/components/celestin/styles";
import { BAR } from "@/components/celestin/tutor-board-split";
import { UserMenu } from "@/components/celestin/user-menu";
import type { User } from "@/lib/auth";
import { useCourseLanguage } from "@/lib/course-language";
import { AUTONYM } from "@/lib/locale";
import type { ChapterView } from "@/lib/tutor/types";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";

export type ChapterMode = "parcours" | "discussion";

export function ChapterBar({
  chapter,
  user,
  mode,
  onMode,
}: {
  chapter: ChapterView;
  user: User;
  mode: ChapterMode;
  /** The lesson switches in place, keeping the séance mounted (007 R1.3); without
   *  it, the standalone discussion route links to the parcours instead. */
  onMode?: (mode: ChapterMode) => void;
}) {
  const language = useCourseLanguage();
  const isDesktop = useIsDesktop();
  if (!isDesktop) {
    /* A phone: the way back, the two modes, and one menu for the rest (015). The
       chapter's title is in the line under the bar. */
    return (
      <div className="flex items-center gap-1 border-b border-border bg-background px-2 py-1">
        <Link
          to="/courses/$courseId"
          params={{ courseId: chapter.course_id }}
          aria-label={chapter.course_name}
          title={chapter.course_name}
          className={cn(iconButton, "size-10 shrink-0")}
        >
          <ArrowLeft className="size-5" />
        </Link>
        <ModeSwitch chapter={chapter} mode={mode} onMode={onMode} compact />
        <UserMenu user={user} compact>
          <DropdownMenuItem asChild>
            <Link
              to="/courses/$courseId/chapters/$chapterId/content"
              params={{ courseId: chapter.course_id, chapterId: chapter.id }}
            >
              <FileText /> {m.chapter_content()}
            </Link>
          </DropdownMenuItem>
        </UserMenu>
      </div>
    );
  }
  return (
    <div className={BAR}>
      <Link
        to="/courses/$courseId"
        params={{ courseId: chapter.course_id }}
        className="text-muted-foreground hover:underline"
      >
        ← {chapter.course_name}
      </Link>
      <span className="text-muted-foreground">·</span>
      <span lang={language} className="truncate font-semibold">
        {chapter.title}
      </span>
      <span
        lang={language}
        data-testid="course-language"
        className="hidden shrink-0 rounded border border-border px-1.5 text-xs text-muted-foreground sm:inline"
      >
        {AUTONYM[language]}
      </span>
      <ModeSwitch chapter={chapter} mode={mode} onMode={onMode} />
      <Link
        to="/courses/$courseId/chapters/$chapterId/content"
        params={{ courseId: chapter.course_id, chapterId: chapter.id }}
        className="shrink-0 text-muted-foreground hover:underline"
      >
        {m.chapter_content()}
      </Link>
      <UserMenu user={user} className="ml-auto" />
    </div>
  );
}

const SEGMENT = "rounded px-2 py-0.5 font-medium transition-colors";
const ACTIVE = "bg-background text-foreground shadow-sm";
const IDLE = "text-muted-foreground hover:text-foreground";

/** Message functions, not strings: the language is read when the bar renders. */
const TITLES: Record<ChapterMode, () => string> = {
  parcours: m.lesson_mode_path_title,
  discussion: m.lesson_mode_discussion_title,
};

/** Which mode is on screen, and the way to the other one. */
function ModeSwitch({
  chapter,
  mode,
  onMode,
  compact = false,
}: {
  chapter: ChapterView;
  mode: ChapterMode;
  onMode?: ((mode: ChapterMode) => void) | undefined;
  /** Phone: the two segments share the bar, each one a finger wide. */
  compact?: boolean;
}) {
  const segment = (target: ChapterMode, label: string) => {
    const active = mode === target;
    const className = cn(
      SEGMENT,
      active ? ACTIVE : IDLE,
      compact && "flex-1 py-2 text-center text-sm",
    );
    if (!onMode && !active && target === "parcours") {
      return (
        <Link
          to="/courses/$courseId/chapters/$chapterId"
          params={{ courseId: chapter.course_id, chapterId: chapter.id }}
          title={TITLES[target]()}
          className={className}
        >
          {label}
        </Link>
      );
    }
    return (
      <button
        type="button"
        aria-pressed={active}
        title={TITLES[target]()}
        onClick={active ? undefined : () => onMode?.(target)}
        className={className}
      >
        {label}
      </button>
    );
  };
  return (
    <div
      className={cn(
        "flex items-center gap-0.5 rounded-md bg-secondary p-0.5",
        compact ? "min-w-0 flex-1" : "shrink-0",
      )}
    >
      {segment("parcours", m.lesson_mode_path())}
      {segment("discussion", m.lesson_mode_discussion())}
    </div>
  );
}
