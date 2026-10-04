/** Adding a chapter from a document (006 R1). */

import type { Limits } from "@/lib/tutor/types";
import { m } from "@/paraglide/messages";
import { DocumentPicker } from "./document-picker";
import { panel } from "./styles";

export function AddChapterForm({
  limits,
  onAdd,
  onCancel,
}: {
  limits: Limits;
  onAdd: (files: File[]) => Promise<unknown>;
  onCancel: () => void;
}) {
  return (
    <section aria-label={m.course_add_chapter()} className={`space-y-2 ${panel}`}>
      <p className="text-xs text-muted-foreground">{m.chapter_add_intro()}</p>
      <DocumentPicker
        id="chapter-document"
        limits={limits}
        submitLabel={m.chapter_add_submit()}
        confirm={null}
        onSubmit={onAdd}
        onCancel={onCancel}
      />
    </section>
  );
}
