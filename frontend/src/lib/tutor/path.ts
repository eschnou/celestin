/**
 * Display-only mirror of the backend's locked path (`app/services/path.py`).
 *
 * It colours rows before the first turn and nothing else: the backend recomputes
 * states from what it receives, so this cannot unlock anything. Tested against the
 * same case table as the backend (`__tests__/path_cases.json`).
 */

import type { Progress, SectionState } from "./types";

export function sectionStates(
  sections: readonly { id: string }[],
  progress: Progress,
): Record<string, SectionState> {
  const done = new Set(progress.done);
  const states: Record<string, SectionState> = {};
  let availableTaken = progress.active !== null;
  for (const { id } of sections) {
    if (done.has(id)) states[id] = "done";
    else if (id === progress.active) states[id] = "active";
    else if (!availableTaken) {
      states[id] = "available";
      availableTaken = true;
    } else states[id] = "locked";
  }
  return states;
}
