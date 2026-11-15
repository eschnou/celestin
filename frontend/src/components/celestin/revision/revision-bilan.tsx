/**
 * The « Bilan » of a révision (spec 020): per chapter of the révision, each section with the
 * student's latest self-assessment and its date (« pas encore testée » otherwise), where its
 * path stands when that helps, and the ways to work on it: the chapter's parcours, and the
 * cahier once the section is done. These are her own judgements, and the sheet says so.
 */

import { Link } from "@tanstack/react-router";

import { ChapterHeading } from "@/components/celestin/chapter-row";
import { SectionLabel } from "@/components/celestin/section-label";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useIsDesktop } from "@/hooks/use-is-desktop";
import { useCourseLanguage } from "@/lib/course-language";
import { formatDate } from "@/lib/i18n-format";
import { resultKey, type Assessment } from "@/lib/tutor/revision";
import type { RevisionChapter, RevisionSection } from "@/lib/tutor/types";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";
import { OutcomeChip } from "./outcome";

const LINK = "text-xs font-semibold text-primary hover:underline";

export function RevisionBilan({
  open,
  onOpenChange,
  courseId,
  chapters,
  results,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  courseId: string;
  /** The révision's chapters, in course order. */
  chapters: RevisionChapter[];
  /** The latest self-assessment per section (`resultKey`). */
  results: ReadonlyMap<string, Assessment>;
}) {
  const isDesktop = useIsDesktop();
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side={isDesktop ? "right" : "bottom"}
        className={cn(
          "flex flex-col gap-0 p-0",
          isDesktop ? "w-full sm:max-w-md" : "h-[85dvh] rounded-t-xl",
        )}
      >
        <SheetHeader className="border-b border-border px-4 py-3 text-left">
          <SheetTitle className="text-base">{m.revision_bilan_title()}</SheetTitle>
          <SheetDescription>{m.revision_bilan_lead()}</SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-4 py-4">
          {chapters.map((chapter) => (
            <ChapterResults
              key={chapter.id}
              courseId={courseId}
              chapter={chapter}
              results={results}
            />
          ))}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function ChapterResults({
  courseId,
  chapter,
  results,
}: {
  courseId: string;
  chapter: RevisionChapter;
  results: ReadonlyMap<string, Assessment>;
}) {
  return (
    <section aria-labelledby={`bilan-${chapter.id}`}>
      <h3 id={`bilan-${chapter.id}`} className="text-sm font-bold">
        <ChapterHeading chapter={chapter} />
      </h3>
      <ul className="mt-2 divide-y divide-border rounded-lg border border-border bg-background">
        {chapter.sections.map((section) => (
          <SectionResult
            key={section.id}
            courseId={courseId}
            chapterId={chapter.id}
            section={section}
            result={results.get(resultKey(chapter.id, section.id)) ?? null}
          />
        ))}
      </ul>
    </section>
  );
}

function SectionResult({
  courseId,
  chapterId,
  section,
  result,
}: {
  courseId: string;
  chapterId: string;
  section: RevisionSection;
  result: Assessment | null;
}) {
  const language = useCourseLanguage();
  return (
    <li className="px-3 py-2.5" data-section={section.id}>
      <SectionLabel section={section} className="text-xs" />
      <p lang={language} className="mt-0.5 text-sm font-medium">
        {section.title}
      </p>
      <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        {result ? (
          <>
            <OutcomeChip outcome={result.outcome} />
            <span>{m.revision_noted_on({ date: formatDate(result.at) })}</span>
          </>
        ) : (
          <span>{m.revision_not_tested()}</span>
        )}
        {section.state === "skipped" && (
          <span className="rounded border border-dashed border-muted-foreground/60 px-1">
            {m.lesson_state_skipped()}
          </span>
        )}
        {section.state === "todo" && (
          <span className="rounded border border-border px-1">{m.revision_section_todo()}</span>
        )}
      </p>
      <p className="mt-1.5 flex gap-3">
        <Link
          to="/courses/$courseId/chapters/$chapterId"
          params={{ courseId, chapterId }}
          className={LINK}
        >
          {m.lesson_mode_path()}
        </Link>
        {section.state === "done" && (
          <Link
            to="/courses/$courseId/chapters/$chapterId/notebook"
            params={{ courseId, chapterId }}
            hash={section.id}
            className={LINK}
          >
            {m.chapter_notebook()}
          </Link>
        )}
      </p>
    </li>
  );
}
