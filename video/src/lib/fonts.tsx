import React, { useEffect, useState } from "react";
import { continueRender, delayRender } from "remotion";
import { loadFont as loadLato } from "@remotion/google-fonts/Lato";
import { loadFont as loadCaveat } from "@remotion/google-fonts/Caveat";

loadLato("normal", { weights: ["400", "700", "900"], subsets: ["latin", "latin-ext"] });
loadLato("italic", { weights: ["400"], subsets: ["latin", "latin-ext"] });
const caveat = loadCaveat("normal", { weights: ["500", "700"], subsets: ["latin"] });

export const HAND = caveat.fontFamily;

const KATEX = [
  "16px KaTeX_Main",
  "bold 16px KaTeX_Main",
  "italic 16px KaTeX_Main",
  "italic 16px KaTeX_Math",
  "16px KaTeX_AMS",
  "16px KaTeX_Size1",
  "16px KaTeX_Size2",
  "16px KaTeX_Size3",
  "16px KaTeX_Size4",
];

/** Holds the first frames until the KaTeX faces (loaded lazily by the browser) are in. */
export const FontsReady: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [handle] = useState(() => delayRender("fonts"));
  useEffect(() => {
    Promise.all(KATEX.map((face) => document.fonts.load(face, "Sn=∑1−q")))
      .then(() => document.fonts.ready)
      .then(() => continueRender(handle))
      .catch(() => continueRender(handle));
  }, [handle]);
  return <>{children}</>;
};
