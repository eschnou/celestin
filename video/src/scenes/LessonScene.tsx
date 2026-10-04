import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { OUT, rise } from "../lib/ease";
import { AppWindow, Headline, Marker } from "../lib/ui";
import { LESSON_LOGICAL, LessonInside } from "./Lesson";

/** What the viewer should notice, in step with what the board is doing. */
const CAPTIONS = [
  { from: 3.2, to: 12.8, text: "La formule vient de la page 14 de ton cours." },
  { from: 12.8, to: 16.6, text: "L'exemple, c'est celui de ton prof." },
  { from: 16.6, to: 23.4, text: "À toi de calculer : Célestin ne donne pas la réponse." },
  { from: 23.4, to: 99, text: "Puis il fait le point sur ce que tu as acquis." },
];

const SubCaption: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  return (
    <div style={{ position: "relative", height: 48, marginTop: 10 }}>
      {CAPTIONS.map((c, i) => {
        const p = rise(t, c.from, c.from + 0.5) * (1 - rise(t, c.to - 0.4, c.to));
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: 0,
              opacity: p,
              transform: `translateY(${(1 - p) * 14}px)`,
              fontSize: 36,
              fontWeight: 700,
              color: "oklch(0.4 0.07 183)",
              whiteSpace: "nowrap",
            }}
          >
            {c.text}
          </div>
        );
      })}
    </div>
  );
};

export const LessonScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const enter = rise(frame, 6, 36, OUT);
  return (
    <AbsoluteFill className="bg-paper" style={{ color: "oklch(0.24 0.015 250)" }}>
      <div style={{ position: "absolute", left: 96, top: 36 }}>
        <Headline
          size={66}
          start={2}
          lines={[
            <span key="a">
              Célestin enseigne avec{" "}
              <Marker start={20} duration={22} color="oklch(0.9 0.08 350)">
                ton cours.
              </Marker>
            </span>,
          ]}
        />
        <SubCaption />
      </div>
      <AppWindow left={96} top={196} {...LESSON_LOGICAL} scale={1.32} enter={enter}>
        <LessonInside total={durationInFrames} />
      </AppWindow>
    </AbsoluteFill>
  );
};
