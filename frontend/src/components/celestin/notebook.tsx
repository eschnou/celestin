/**
 * The cahier (spec 018 D8): what Célestin wrote on the board, section by section, as it
 * was shown, read back from the stored séances. No model call, nothing to answer.
 *
 * Every card is drawn by the board's own `CardView`, in reading mode: no answer reaches
 * anyone, there is no page-turn button and no history strip. A worked example shows all
 * its steps (it always does); a check question reveals its right option and its feedback
 * only once an option is picked. Title cards are skipped: the section heading says it.
 * The exchange between the boards is behind a toggle, rendered by the transcript's own
 * `Entry`.
 */

import { useEffect, useState } from "react";

import { SectionLabel } from "@/components/celestin/section-label";
import { panel } from "@/components/celestin/styles";
import { Entry } from "@/components/celestin/transcript";
import { CardView } from "@/components/celestin/whiteboard";
import { Switch } from "@/components/ui/switch";
import { useCourseLanguage } from "@/lib/course-language";
import type {
  ChapterView,
  Notebook,
  NotebookItem,
  SectionOverview,
  TranscriptEntry,
} from "@/lib/tutor/types";
import { m } from "@/paraglide/messages";

/** The sections to show, each with its overview. The server sends them in path order, each
 *  with at least one item; a section the chapter no longer has (the server reads the current
 *  version only, so this is a guard) is left out. */
function notebookSections(
  chapter: Pick<ChapterView, "sections">,
  notebook: Notebook,
): { section: SectionOverview; items: NotebookItem[] }[] {
  const byId = new Map(chapter.sections.map((s) => [s.id, s]));
  return notebook.sections.flatMap((entry) => {
    const section = byId.get(entry.section_id);
    return section ? [{ section, items: entry.items }] : [];
  });
}

const noop = () => {};

export function NotebookView({
  chapter,
  notebook,
  anchor,
}: {
  chapter: ChapterView;
  notebook: Notebook;
  /** A section id from the URL's hash: scrolled into view once the page is drawn. */
  anchor?: string | undefined;
}) {
  const language = useCourseLanguage();
  const [exchanges, setExchanges] = useState(false);
  const sections = notebookSections(chapter, notebook);

  useEffect(() => {
    if (!anchor) return;
    document.getElementById(anchor)?.scrollIntoView?.({ block: "start" });
  }, [anchor]);

  return (
    <div className="mt-3 space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs tracking-wide text-muted-foreground uppercase">
            {m.chapter_notebook()}
          </p>
          <h1 lang={language} className="text-xl font-bold">
            {chapter.title}
          </h1>
          <p className="text-sm text-muted-foreground">{m.notebook_lead()}</p>
        </div>
        {sections.length > 0 && (
          <label className="flex shrink-0 items-center gap-2 text-sm print:hidden">
            <Switch checked={exchanges} onCheckedChange={setExchanges} />
            {m.notebook_show_exchanges()}
          </label>
        )}
      </div>

      {sections.length === 0 ? (
        <p className={`${panel} text-sm text-muted-foreground`}>{m.notebook_empty()}</p>
      ) : (
        sections.map(({ section, items }) => (
          <NotebookSectionView
            key={section.id}
            section={section}
            items={items}
            exchanges={exchanges}
          />
        ))
      )}
    </div>
  );
}

function NotebookSectionView({
  section,
  items,
  exchanges,
}: {
  section: SectionOverview;
  items: NotebookItem[];
  exchanges: boolean;
}) {
  const language = useCourseLanguage();
  // Title cards are said by the heading, the exchange shown only when asked for: a section
  // can be left with nothing (a title card alone), which the page says.
  const shown = items.filter((item) =>
    item.kind === "card" ? item.card.kind !== "title" : exchanges,
  );
  const headingId = `notebook-${section.id}`;
  return (
    <section id={section.id} aria-labelledby={headingId} className="scroll-mt-4 space-y-3">
      <header className="flex items-baseline gap-2 border-b border-border pb-2 break-after-avoid">
        <SectionLabel section={section} className="text-sm" />
        <h2 id={headingId} lang={language} className="min-w-0 text-lg font-bold">
          {section.title}
        </h2>
      </header>
      {shown.length === 0 ? (
        <p className="text-sm text-muted-foreground">{m.notebook_section_empty()}</p>
      ) : (
        shown.map((item, i) =>
          item.kind === "card" ? (
            <div key={i} className="break-inside-avoid" data-card={item.card.kind}>
              <CardView card={item.card} reread />
            </div>
          ) : (
            <Entry key={i} entry={asEntry(item, `${section.id}-${i}`)} onShowBoard={noop} />
          ),
        )
      )}
    </section>
  );
}

/** A said line as the transcript renders it. */
function asEntry(item: Exclude<NotebookItem, { kind: "card" }>, id: string): TranscriptEntry {
  return item.kind === "learner"
    ? { id, role: "learner", text: item.text }
    : { id, role: "tutor", text: item.text, blockId: 0 };
}
