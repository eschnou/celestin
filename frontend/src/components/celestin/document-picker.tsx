/** Choosing a chapter's pages: one PDF, or photos in page order (006 R1, design 3.9). */

import { useEffect, useRef, useState } from "react";
import { apiMessage } from "@/lib/tutor/client";
import { formatMegabytes } from "@/lib/i18n-format";
import type { Limits } from "@/lib/tutor/types";
import { m } from "@/paraglide/messages";
import { SaveButton } from "./content/save-button";
import { label, secondary } from "./styles";

type Photo = { file: File; url: string; key: number };
type Selection =
  { kind: "none" } | { kind: "pdf"; file: File } | { kind: "photos"; photos: Photo[] };

const PDF = "application/pdf";

function filesOf(selection: Selection): File[] {
  if (selection.kind === "pdf") return [selection.file];
  if (selection.kind === "photos") return selection.photos.map((photo) => photo.file);
  return [];
}

/** Why the selection cannot be sent, or null. The PDF's page count is only known after upload. */
const totalSize = (files: File[]) => files.reduce((total, file) => total + file.size, 0);

export function selectionProblem(files: File[], limits: Limits): string | null {
  const size = totalSize(files);
  if (size > limits.document_max_bytes)
    return m.content_picker_too_big({ size: formatMegabytes(limits.document_max_bytes) });
  const pdf = files.length === 1 && files[0]?.type === PDF;
  if (!pdf && files.length > limits.document_max_pages)
    return m.content_picker_too_many({ max: limits.document_max_pages });
  return null;
}

export function DocumentPicker({
  id,
  limits,
  submitLabel,
  confirm,
  onSubmit,
  onCancel,
}: {
  id: string;
  limits: Limits;
  submitLabel: string;
  /** A confirmation before sending, when sending replaces what the student has. */
  confirm: string | null;
  onSubmit: (files: File[]) => Promise<unknown>;
  onCancel: () => void;
}) {
  const [selection, setSelection] = useState<Selection>({ kind: "none" });
  const photos = selection.kind === "photos" ? selection.photos : [];
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const nextKey = useRef(0);

  // Thumbnails hold object URLs: free the ones still shown when the picker goes away.
  const shown = useRef<Photo[]>([]);
  shown.current = photos;
  useEffect(() => () => shown.current.forEach((photo) => URL.revokeObjectURL(photo.url)), []);

  const release = (photos: Photo[]) => photos.forEach((photo) => URL.revokeObjectURL(photo.url));

  const choose = (chosen: File[]) => {
    setError(null);
    if (chosen.length === 0) return;
    const refused = chosen.find((file) => !limits.document_types.includes(file.type));
    if (refused) {
      setError(m.content_picker_type_refused({ name: refused.name }));
      return;
    }
    const pdf = chosen.find((file) => file.type === PDF);
    if (pdf) {
      if (chosen.length > 1) {
        setError(m.content_picker_one_pdf());
        return;
      }
      release(photos);
      setSelection({ kind: "pdf", file: pdf }); // a PDF replaces whatever was chosen
      return;
    }
    const added = chosen.map((file) => ({
      file,
      url: URL.createObjectURL(file),
      key: nextKey.current++,
    }));
    setSelection((current) => ({
      kind: "photos",
      photos: [...(current.kind === "photos" ? current.photos : []), ...added],
    }));
  };

  const setPhotos = (next: Photo[]) =>
    setSelection(next.length ? { kind: "photos", photos: next } : { kind: "none" });
  const move = (index: number, by: -1 | 1) => {
    const next = [...photos];
    const [here, there] = [next[index], next[index + by]];
    if (!here || !there) return;
    next[index] = there;
    next[index + by] = here;
    setPhotos(next);
  };
  const remove = (index: number) => {
    release(photos.slice(index, index + 1));
    setPhotos(photos.filter((_, i) => i !== index));
  };

  const files = filesOf(selection);
  const problem = selectionProblem(files, limits);
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await onSubmit(files);
    } catch (err) {
      setError(apiMessage(err, m.content_picker_send_failed()));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <div>
        <label className={label} htmlFor={id}>
          {m.content_picker_label()}
        </label>
        <p className="mb-2 text-xs text-muted-foreground">
          {m.content_picker_hint({
            pages: limits.document_max_pages,
            size: formatMegabytes(limits.document_max_bytes),
          })}
        </p>
        {/* The native control is hidden: its text follows the browser's language and
            would say « no file » after each choice, since the field is reset. */}
        <input
          id={id}
          type="file"
          multiple
          accept={limits.document_types.join(",")}
          onChange={(event) => {
            choose(Array.from(event.target.files ?? []));
            event.target.value = ""; // the same file can be chosen again
          }}
          className="peer sr-only"
        />
        <label
          htmlFor={id}
          className={`${secondary} cursor-pointer peer-focus-visible:ring-2 peer-focus-visible:ring-ring`}
        >
          {selection.kind === "photos" ? m.content_picker_add() : m.content_picker_choose()}
        </label>
      </div>

      {selection.kind === "pdf" && (
        <p className="text-sm">
          <span className="font-semibold">{selection.file.name}</span> ·{" "}
          {formatMegabytes(selection.file.size)}
        </p>
      )}
      {selection.kind === "photos" && (
        <ol
          className="grid grid-cols-2 gap-3 sm:grid-cols-4"
          aria-label={m.content_picker_pages_label()}
        >
          {photos.map((photo, index) => (
            <li key={photo.key} className="space-y-1 rounded-md border border-border p-2">
              <img
                src={photo.url}
                alt={m.content_picker_page({ n: index + 1 })}
                className="aspect-[3/4] w-full rounded object-cover"
              />
              <p className="text-xs font-semibold">{m.content_picker_page({ n: index + 1 })}</p>
              <div className="flex flex-wrap gap-1">
                <button
                  type="button"
                  className={secondary}
                  onClick={() => move(index, -1)}
                  disabled={index === 0}
                  aria-label={m.content_picker_up({ n: index + 1 })}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className={secondary}
                  onClick={() => move(index, 1)}
                  disabled={index === photos.length - 1}
                  aria-label={m.content_picker_down({ n: index + 1 })}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className={secondary}
                  onClick={() => remove(index)}
                  aria-label={m.content_picker_remove({ n: index + 1 })}
                >
                  {m.common_remove()}
                </button>
              </div>
            </li>
          ))}
        </ol>
      )}
      {files.length > 0 && (
        <p className={`text-xs ${problem ? "text-destructive" : "text-muted-foreground"}`}>
          {problem ??
            (selection.kind === "photos"
              ? m.content_picker_total({
                  count: files.length,
                  size: formatMegabytes(totalSize(files)),
                })
              : m.content_picker_pdf_unchecked())}
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <SaveButton
          label={busy ? m.content_picker_sending() : submitLabel}
          confirm={confirm}
          disabled={busy || files.length === 0 || problem !== null}
          onSave={() => void submit()}
        />
        <button type="button" onClick={onCancel} className={secondary}>
          {m.common_cancel()}
        </button>
      </div>
    </div>
  );
}
