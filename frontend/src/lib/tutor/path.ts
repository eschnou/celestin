/**
 * Display-only mirror of the backend's path rules (`app/services/path.py`, spec 019).
 *
 * No section is locked: the path's order is the one Célestin proposes. This colours rows
 * and names the proposed next section, nothing else: the backend recomputes states from
 * what it stores. Tested against the same case table as the backend
 * (`__tests__/path_cases.json`).
 */

import type { Progress, SectionState } from "./types";

/** The first section, in path order, that is neither done, skipped nor active: what a
 *  completion or a skip proposes next. Null when there is none. */
export function nextSection(
  sections: readonly { id: string }[],
  progress: Progress,
): string | null {
  const done = new Set(progress.done);
  const skipped = new Set(progress.skipped);
  for (const { id } of sections) {
    if (!done.has(id) && !skipped.has(id) && id !== progress.active) return id;
  }
  return null;
}

export function sectionStates(
  sections: readonly { id: string }[],
  progress: Progress,
): Record<string, SectionState> {
  const done = new Set(progress.done);
  const skipped = new Set(progress.skipped);
  // The proposed one exists only while nothing is being worked.
  const proposed = progress.active === null ? nextSection(sections, progress) : null;
  const states: Record<string, SectionState> = {};
  for (const { id } of sections) {
    if (done.has(id)) states[id] = "done";
    else if (id === progress.active) states[id] = "active";
    else if (skipped.has(id)) states[id] = "skipped";
    else if (id === proposed) states[id] = "available";
    else states[id] = "open";
  }
  return states;
}
