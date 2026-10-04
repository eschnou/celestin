/** The dictation route: one recording in, the text out (the backend's `POST /api/dictation`). */

import { sendForm } from "@/lib/tutor/client";
import type { CourseLanguage } from "@/lib/course-language";

export const DICTATION_URL = "/api/dictation";

/** The extension the server uses to name the file, from what the browser recorded. */
export function recordingName(type: string): string {
  const base = type.split(";", 1)[0]?.trim().toLowerCase() ?? "";
  if (base.includes("mp4") || base.includes("m4a") || base.includes("aac")) return "dictation.mp4";
  if (base.includes("ogg")) return "dictation.ogg";
  return "dictation.webm";
}

export async function transcribe(
  audio: Blob,
  /** `language: null`: no hint (a language course mixes two languages: the wrong hint is worse than none). */
  opts: { language: CourseLanguage | null; durationMs: number },
  signal?: AbortSignal,
): Promise<string> {
  const form = new FormData();
  form.append("audio", audio, recordingName(audio.type));
  if (opts.language) form.append("language", opts.language);
  form.append("duration_ms", String(Math.round(opts.durationMs)));
  const response = await sendForm(DICTATION_URL, form, "POST", signal);
  const body = (await response.json()) as { text?: unknown };
  return typeof body.text === "string" ? body.text.trim() : "";
}
