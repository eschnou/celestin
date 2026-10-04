/**
 * How the transcription marks what it could not read, per course language (spec 011 R4.3).
 * The backend's `MARKERS` table is the source (`domain/transcription.py`): these are the
 * examples the source editor's hint shows, so the student looks for the marks their own
 * document's transcription uses. Course text, not interface text.
 */
import type { CourseLanguage } from "@/lib/course-language";

export type MarkerExamples = { uncertain: string; illegible: string; page: string };

export const MARKER_EXAMPLES: Record<CourseLanguage, MarkerExamples> = {
  fr: { uncertain: "[incertain : …]", illegible: "[illisible]", page: "--- page N ---" },
  en: { uncertain: "[uncertain: …]", illegible: "[illegible]", page: "--- page N ---" },
};
