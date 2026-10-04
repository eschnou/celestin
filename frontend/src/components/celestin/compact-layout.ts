import { createContext, useContext } from "react";

/**
 * True inside the small-screen frame of `TutorBoardSplit`: the board takes the
 * screen, Célestin's last words sit above the composer, the rest is on demand.
 * A context rather than a prop, so the tutor column, the strip and the composer
 * follow the frame without the lesson and the discussion each having to know.
 */
const CompactLayout = createContext(false);

export const CompactLayoutProvider = CompactLayout.Provider;
export const useCompactLayout = (): boolean => useContext(CompactLayout);
