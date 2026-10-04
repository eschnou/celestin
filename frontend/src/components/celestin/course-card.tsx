/** One course on « Mes cours » (005 R1.1). */

import { Link } from "@tanstack/react-router";
import { AUTONYM } from "@/lib/locale";
import type { CourseSummary } from "@/lib/tutor/types";
import { m } from "@/paraglide/messages";
import { card, primary, secondary } from "./styles";

export function CourseCard({ course }: { course: CourseSummary }) {
  const resume = course.last_chapter;
  return (
    <article className={card} aria-label={course.name}>
      <p className="text-xs tracking-wide text-muted-foreground uppercase">
        {course.subject_label} ·{" "}
        <span lang={course.language} data-testid="course-language">
          {AUTONYM[course.language]}
        </span>
      </p>
      <h3 className="mt-1 text-base font-bold">{course.name}</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        {course.chapters_total === 0
          ? m.course_card_no_chapters()
          : m.course_card_progress({ done: course.chapters_done, total: course.chapters_total })}
        {course.generating > 0 && ` · ${m.course_card_generating({ count: course.generating })}`}
      </p>
      <div className="mt-auto flex flex-wrap gap-2 pt-4">
        {resume && (
          <Link
            to="/courses/$courseId/chapters/$chapterId"
            params={{ courseId: course.id, chapterId: resume.id }}
            className={primary}
          >
            {m.course_card_resume({ title: resume.title })}
          </Link>
        )}
        <Link
          to="/courses/$courseId"
          params={{ courseId: course.id }}
          className={resume ? secondary : primary}
        >
          {m.course_card_open()}
        </Link>
      </div>
    </article>
  );
}
