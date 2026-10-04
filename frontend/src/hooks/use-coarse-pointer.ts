import { useEffect, useState } from "react";

/**
 * Whether the main pointer is a finger (a phone or a tablet) rather than a mouse. Decides what « take a
 * photo » means: on a phone the browser's own camera, on a computer the webcam. False without `matchMedia`.
 */
export function useCoarsePointer(): boolean {
  const [coarse, setCoarse] = useState(false);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(pointer: coarse)");
    const update = () => setCoarse(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return coarse;
}
