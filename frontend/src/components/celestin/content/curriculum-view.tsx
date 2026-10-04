/** The path as a readable list: what each section does and when it ends (005 R5.1). */

import { useCourseLanguage } from "@/lib/course-language";
import { KIND_LABEL } from "@/lib/tutor/labels";
import type { SectionFull } from "@/lib/tutor/types";
import { m } from "@/paraglide/messages";
import { panel } from "@/components/celestin/styles";

export function CurriculumView({ sections }: { sections: SectionFull[] }) {
  const language = useCourseLanguage();
  return (
    <ol className="space-y-3">
      {sections.map((section) => (
        <li key={section.id} className={`${panel}`}>
          <p className="text-xs tracking-wide text-muted-foreground uppercase">
            {section.index} · {KIND_LABEL[section.kind]()}
          </p>
          <h3 lang={language} className="mt-1 font-semibold">
            {section.title}
          </h3>
          <p lang={language} className="mt-1 text-sm">
            {section.goal}
          </p>
          {section.kind === "teach" ? (
            <ol
              lang={language}
              className="mt-2 list-decimal space-y-0.5 pl-5 text-sm text-muted-foreground"
            >
              {section.beats.map((beat, i) => (
                <li key={i}>{beat}</li>
              ))}
            </ol>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">
              {m.content_exercises_from({
                count: section.count ?? 0,
                list: section.exercises.join(" ; "),
              })}
            </p>
          )}
          <p className="mt-2 text-xs text-muted-foreground">
            {m.content_done_when({ text: section.done_when })}
          </p>
        </li>
      ))}
    </ol>
  );
}
