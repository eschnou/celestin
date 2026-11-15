/** The révision's top bar (spec 020): the way back to the course, the mode, the course's
 *  language and who is signed in. The chapter bar's sibling, for a course-scoped screen. */

import { Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";

import { iconButton } from "@/components/celestin/styles";
import { BAR } from "@/components/celestin/tutor-board-split";
import { UserMenu } from "@/components/celestin/user-menu";
import { useIsDesktop } from "@/hooks/use-is-desktop";
import type { User } from "@/lib/auth";
import type { CourseLanguage } from "@/lib/course-language";
import { AUTONYM } from "@/lib/locale";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";

export function RevisionBar({
  course,
  user,
}: {
  course: { id: string; name: string; language: CourseLanguage };
  user: User;
}) {
  const isDesktop = useIsDesktop();
  if (!isDesktop) {
    return (
      <div className="flex items-center gap-1 border-b border-border bg-background px-2 py-1">
        <Link
          to="/courses/$courseId"
          params={{ courseId: course.id }}
          aria-label={course.name}
          title={course.name}
          className={cn(iconButton, "size-10 shrink-0")}
        >
          <ArrowLeft className="size-5" />
        </Link>
        <h1 className="min-w-0 flex-1 truncate text-sm font-semibold">{m.revision_title()}</h1>
        <UserMenu user={user} compact />
      </div>
    );
  }
  return (
    <div className={BAR}>
      <Link
        to="/courses/$courseId"
        params={{ courseId: course.id }}
        className="text-muted-foreground hover:underline"
      >
        ← {course.name}
      </Link>
      <span className="text-muted-foreground">·</span>
      <h1 className="truncate font-semibold">{m.revision_title()}</h1>
      <span
        lang={course.language}
        data-testid="course-language"
        className="hidden shrink-0 rounded border border-border px-1.5 text-xs text-muted-foreground sm:inline"
      >
        {AUTONYM[course.language]}
      </span>
      <UserMenu user={user} className="ml-auto" />
    </div>
  );
}
