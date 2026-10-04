/** The head of a course page: its mark, its name, where she stands, and the few things that manage it. */

import { Ellipsis, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog } from "@/components/celestin/confirm-dialog";
import { field, primary, secondary } from "@/components/celestin/styles";
import { SubjectIcon } from "@/components/celestin/subject-icon";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { CourseLanguage } from "@/lib/course-language";
import { AUTONYM } from "@/lib/locale";
import { apiMessage } from "@/lib/tutor/client";
import type { SubjectId } from "@/lib/tutor/types";
import { m } from "@/paraglide/messages";

export function CourseHeader({
  name,
  subject,
  subjectLabel,
  language,
  chaptersTotal,
  chaptersDone,
  onRename,
  onDelete,
}: {
  name: string;
  subject: SubjectId;
  subjectLabel: string;
  language: CourseLanguage;
  chaptersTotal: number;
  chaptersDone: number;
  onRename: (name: string) => Promise<void>;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [value, setValue] = useState(name);
  const [error, setError] = useState<string | null>(null);
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || trimmed.length > 80) {
      setError(m.course_name_length());
      return;
    }
    try {
      await onRename(trimmed);
      setEditing(false);
      setError(null);
    } catch (err) {
      setError(apiMessage(err, m.course_rename_failed()));
    }
  };
  return (
    <div className="mt-4 flex items-start gap-3">
      <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
        <SubjectIcon subject={subject} className="size-6" />
      </span>
      <div className="min-w-0 flex-1">
        {editing ? (
          <form
            onSubmit={(event) => void save(event)}
            className="flex flex-wrap gap-2"
            aria-label={m.course_rename_form()}
          >
            <label htmlFor="rename-course" className="sr-only">
              {m.course_name_label()}
            </label>
            <input
              id="rename-course"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              className={`${field} max-w-sm`}
            />
            <button type="submit" className={primary}>
              {m.common_save()}
            </button>
            <button type="button" onClick={() => setEditing(false)} className={secondary}>
              {m.common_cancel()}
            </button>
            {error && <p className="w-full text-xs text-destructive">{error}</p>}
          </form>
        ) : (
          <>
            <h1 className="text-2xl leading-tight font-bold break-words">{name}</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {subjectLabel} ·{" "}
              <span lang={language} data-testid="course-language">
                {AUTONYM[language]}
              </span>
              {chaptersTotal > 0 &&
                ` · ${m.course_card_progress({ done: chaptersDone, total: chaptersTotal })}`}
            </p>
          </>
        )}
      </div>
      {!editing && (
        <DropdownMenu>
          <DropdownMenuTrigger
            aria-label={m.course_menu()}
            className="inline-flex size-10 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            <Ellipsis className="size-5" aria-hidden />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              onSelect={() => {
                setValue(name);
                setEditing(true);
              }}
            >
              <Pencil /> {m.course_rename()}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={() => setConfirming(true)}
              className="text-destructive focus:text-destructive"
            >
              <Trash2 /> {m.course_delete()}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={m.course_delete_title({ name })}
        description={m.course_delete_description({ count: chaptersTotal })}
        confirm={m.course_delete()}
        onConfirm={onDelete}
        destructive
      />
    </div>
  );
}
