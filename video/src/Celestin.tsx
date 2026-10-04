import React from "react";
import { AbsoluteFill, Sequence, interpolate, staticFile, useVideoConfig } from "remotion";
import { Audio } from "@remotion/media";
import "@/lib/i18n";
import { FontsReady } from "./lib/fonts";
import { SceneFade } from "./lib/ui";
import { Intro } from "./scenes/Intro";
import { Deposit } from "./scenes/Deposit";
import { LessonScene } from "./scenes/LessonScene";
import { Showcase, SHOWCASE_FRAMES } from "./scenes/Showcase";
import { Guarantees, GUARANTEES_FRAMES } from "./scenes/Guarantees";
import { Outro } from "./scenes/Outro";

const OVERLAP = 12;

const SCENES = [
  { id: "intro", frames: 250, node: <Intro /> },
  { id: "deposit", frames: 340, node: <Deposit /> },
  { id: "lesson", frames: 840, node: <LessonScene /> },
  { id: "showcase", frames: SHOWCASE_FRAMES, node: <Showcase /> },
  { id: "guarantees", frames: GUARANTEES_FRAMES, node: <Guarantees /> },
  { id: "outro", frames: 280, node: <Outro /> },
];

/** Where each scene starts: every scene overlaps the previous one by OVERLAP frames. */
const STARTS = SCENES.map((_, i) =>
  SCENES.slice(0, i).reduce((sum, scene) => sum + scene.frames - OVERLAP, 0),
);
export const TOTAL_FRAMES =
  STARTS[SCENES.length - 1]! + SCENES[SCENES.length - 1]!.frames;

/** The soundtrack, faded in over 1 s and out over the last 3 s. */
const Soundtrack: React.FC = () => {
  const { fps, durationInFrames } = useVideoConfig();
  return (
    <Audio
      src={staticFile("organized-wonder.mp3")}
      volume={(f) =>
        0.75 *
        interpolate(f, [0, fps, durationInFrames - 3 * fps, durationInFrames], [0, 1, 1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      }
    />
  );
};

export const Celestin: React.FC = () => (
  <FontsReady>
    <Soundtrack />
    <AbsoluteFill style={{ background: "#06323c" }}>
      {SCENES.map((scene, i) => (
        <Sequence key={scene.id} from={STARTS[i]!} durationInFrames={scene.frames} name={scene.id}>
          <SceneFade
            inFrames={i === 0 ? 1 : OVERLAP}
            outFrames={i === SCENES.length - 1 ? 24 : OVERLAP}
          >
            {scene.node}
          </SceneFade>
        </Sequence>
      ))}
    </AbsoluteFill>
  </FontsReady>
);
