import { useEffect } from "react";

/** Apply `typed` after a pause in the typing, unless it is already what is applied. The usage screen's search
 *  and group filter use it, as the accounts list's search does. */
export function useDebouncedApply<T>(
  typed: T,
  applied: T,
  apply: (value: T) => void,
  delayMs = 250,
) {
  useEffect(() => {
    if (typed === applied) return;
    const id = setTimeout(() => apply(typed), delayMs);
    return () => clearTimeout(id);
  }, [typed, applied, apply, delayMs]);
}
