/**
 * Reading a photo of her work into text. One photo at a time: while it is being read a second is refused, and
 * the call can be given up. The text is handed to `onText` for the composer; nothing else is kept.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { preparePhoto, readWork } from "@/lib/tutor/work";

export type PhotoError =
  { kind: "not-image" } | { kind: "empty" } | { kind: "failed"; cause: unknown };

export type PhotoDeps = {
  prepare: (file: Blob) => Promise<Blob>;
  read: (courseId: string, photo: Blob, signal: AbortSignal) => Promise<string>;
};

const defaultDeps: PhotoDeps = { prepare: preparePhoto, read: readWork };

export type PhotoControls = {
  phase: "idle" | "reading";
  error: PhotoError | null;
  /** Reads the photo; ignored while another is being read. */
  read: (file: Blob) => void;
  cancel: () => void;
  clearError: () => void;
};

export function usePhotoWork(opts: {
  courseId: string;
  onText: (text: string) => void;
  deps?: PhotoDeps;
}): PhotoControls {
  const deps = opts.deps ?? defaultDeps;
  const [phase, setPhase] = useState<"idle" | "reading">("idle");
  const [error, setError] = useState<PhotoError | null>(null);
  const busy = useRef(false);
  const abort = useRef<AbortController | null>(null);
  const latest = useRef({ ...opts, deps });
  useEffect(() => {
    latest.current = { ...opts, deps };
  });

  const read = useCallback((file: Blob) => {
    if (busy.current) return;
    setError(null);
    if (!file.type.startsWith("image/")) {
      setError({ kind: "not-image" });
      return;
    }
    busy.current = true;
    const controller = new AbortController();
    abort.current = controller;
    setPhase("reading");
    void (async () => {
      try {
        const { deps: d, courseId, onText } = latest.current;
        const photo = await d.prepare(file);
        const text = (await d.read(courseId, photo, controller.signal)).trim();
        if (controller.signal.aborted) return;
        if (text) onText(text);
        else setError({ kind: "empty" });
      } catch (cause) {
        if (!controller.signal.aborted) setError({ kind: "failed", cause });
      } finally {
        if (abort.current === controller) abort.current = null;
        busy.current = false;
        setPhase("idle");
      }
    })();
  }, []);

  const cancel = useCallback(() => {
    abort.current?.abort();
  }, []);
  useEffect(() => cancel, [cancel]);
  const clearError = useCallback(() => setError(null), []);

  return { phase, error, read, cancel, clearError };
}
