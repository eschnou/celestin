/**
 * Before a révision (spec 020 D2): which chapters the test covers. Every chapter of the
 * course is listed in its order, the ready ones with a checkbox and their done / skipped
 * counts, the others disabled. A refusal from the server (too large, nothing chosen, not
 * ready, the day's quota) is said above the list, and the choice stays as it was.
 */

import { useState } from "react";

import { ChapterHeading, progressText } from "@/components/celestin/chapter-row";
import { alertBox, primary, secondary } from "@/components/celestin/styles";
import { Checkbox } from "@/components/ui/checkbox";
import { preselected } from "@/lib/tutor/revision";
import type { RevisionChapter } from "@/lib/tutor/types";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";

export function RevisionChooser({
  chapters,
  wanted,
  onStart,
  pending,
  error,
  onBack,
}: {
  chapters: RevisionChapter[];
  /** `?chapter=`: the chapter the student came from, ticked alone. */
  wanted?: string | undefined;
  /** The chosen chapters, in course order. */
  onStart: (chapterIds: string[]) => void;
  pending: boolean;
  /** The server's refusal of the last start, in its own words. */
  error: string | null;
  /** There is a live révision to go back to (« Nouvelle révision » brought her here). */
  onBack?: (() => void) | undefined;
}) {
  // Only ready chapters are ever ticked: the preselection takes ready ones, and a chapter that
  // is not ready has its checkbox disabled.
  const [checked, setChecked] = useState<ReadonlySet<string>>(
    () => new Set(preselected(chapters, wanted)),
  );
  const ready = chapters.some((c) => c.ready);
  const chosen = chapters.filter((c) => checked.has(c.id)).map((c) => c.id);

  const toggle = (id: string, on: boolean) =>
    setChecked((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-2xl px-4 py-6">
        <h1 className="text-xl font-bold">{m.revision_choose_title()}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{m.revision_choose_lead()}</p>
        {error && (
          <p role="alert" className={cn(alertBox, "mt-4")}>
            {error}
          </p>
        )}
        {!ready && <p className="mt-4 text-sm text-muted-foreground">{m.revision_no_ready()}</p>}
        <fieldset className="mt-4">
          <legend className="sr-only">{m.revision_choose_label()}</legend>
          <ul className="space-y-2">
            {chapters.map((chapter) => {
              const id = `revision-chapter-${chapter.id}`;
              return (
                <li key={chapter.id}>
                  <label
                    htmlFor={id}
                    className={cn(
                      "flex items-start gap-3 rounded-xl border border-border bg-background p-3 shadow-sheet sm:p-4",
                      chapter.ready ? "cursor-pointer" : "opacity-60",
                    )}
                  >
                    <Checkbox
                      id={id}
                      checked={checked.has(chapter.id)}
                      disabled={!chapter.ready || pending}
                      onCheckedChange={(state) => toggle(chapter.id, state === true)}
                      className="mt-1 size-5"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block font-semibold">
                        <ChapterHeading chapter={chapter} />
                      </span>
                      <span className="block text-sm text-muted-foreground">
                        {chapter.ready ? progressText(chapter) : m.revision_chapter_not_ready()}
                      </span>
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        </fieldset>
        <div className="mt-5 flex flex-wrap gap-2">
          <button
            type="button"
            className={cn(primary, "min-h-10 px-4")}
            disabled={chosen.length === 0 || pending}
            onClick={() => onStart(chosen)}
          >
            {m.revision_start()}
          </button>
          {onBack && (
            <button
              type="button"
              className={cn(secondary, "min-h-10 px-4")}
              disabled={pending}
              onClick={onBack}
            >
              {m.revision_back_to_live()}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
