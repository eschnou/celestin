/** Editing the pack, with a preview and the validator's reasons (005 R5.2). */

import { useState } from "react";
import { field, secondary } from "@/components/celestin/styles";
import { useCourseLanguage } from "@/lib/course-language";
import type { ChapterContent } from "@/lib/tutor/types";
import { m } from "@/paraglide/messages";
import { PackView } from "./pack-view";
import { EditorFooter, useContentSave } from "./save-button";

export function PackEditor({
  content,
  onSave,
  onCancel,
  onReload,
}: {
  content: ChapterContent;
  onSave: (pack: string) => Promise<unknown>;
  onCancel: () => void;
  onReload: () => void;
}) {
  const language = useCourseLanguage();
  const [text, setText] = useState(content.pack ?? "");
  const [preview, setPreview] = useState(false);
  const saving = useContentSave();
  return (
    <div className="space-y-3">
      <div className="flex gap-2" role="tablist" aria-label={m.content_mode()}>
        <button
          type="button"
          role="tab"
          aria-selected={!preview}
          onClick={() => setPreview(false)}
          className={secondary}
        >
          {m.content_tab_edit()}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={preview}
          onClick={() => setPreview(true)}
          className={secondary}
        >
          {m.content_tab_preview()}
        </button>
      </div>
      {preview ? (
        <div className="rounded-xl border border-border bg-background p-4">
          <PackView markdown={text} />
        </div>
      ) : (
        <>
          <label htmlFor="pack-editor" className="sr-only">
            {m.chapter_content()}
          </label>
          <textarea
            id="pack-editor"
            lang={language}
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={28}
            className={`${field} font-mono text-xs`}
          />
          <p className="text-xs text-muted-foreground">{m.content_pack_hint()}</p>
        </>
      )}
      <EditorFooter
        label={m.content_pack_save()}
        confirm={content.has_progress ? m.content_reset_warning() : null}
        state={saving}
        issues={saving.issues}
        onSave={() => void saving.run(() => onSave(text))}
        onCancel={onCancel}
        onReload={onReload}
      />
    </div>
  );
}
