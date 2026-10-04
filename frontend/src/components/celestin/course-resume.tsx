/**
 * The way back into the course: the chapter she was working on, or the next one, with one big button.
 * What a student does nine times out of ten when she opens a course; the list below is for the rest.
 */

import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";

import { useCourseLanguage } from "@/lib/course-language";
import type { Featured } from "@/lib/tutor/featured-chapter";
import { m } from "@/paraglide/messages";
import { actionLabel, chapterTitle, progressText } from "./chapter-row";
import { ProgressBar } from "./progress-bar";
import { primary } from "./styles";
import { cn } from "@/lib/utils";

export function ResumeCard({ courseId, featured }: { courseId: string; featured: Featured }) {
  const language = useCourseLanguage();
  const { row, resuming } = featured;
  return (
    <section
      aria-label={resuming ? m.course_resume_title() : m.course_next_title()}
      className="mt-5 rounded-2xl border border-primary/30 bg-primary/10 p-4 sm:p-5"
    >
      <p className="text-[11px] font-bold tracking-wide text-primary uppercase">
        {resuming ? m.course_resume_title() : m.course_next_title()}
      </p>
      <p lang={row.title ? language : undefined} className="mt-1 text-lg font-bold">
        {chapterTitle(row)}
      </p>
      <p className="mt-0.5 text-sm text-muted-foreground">{progressText(row)}</p>
      {row.state === "in_progress" && (
        <ProgressBar
          done={row.done_count}
          total={row.section_count}
          label={progressText(row)}
          className="mt-3"
        />
      )}
      <Link
        to="/courses/$courseId/chapters/$chapterId"
        params={{ courseId, chapterId: row.id }}
        className={cn(primary, "mt-4 min-h-11 w-full gap-2 px-5 text-base sm:w-auto")}
      >
        {resuming && row.last ? m.chapter_action_resume() : actionLabel(row)}
        <ArrowRight className="size-4" aria-hidden />
      </Link>
    </section>
  );
}
