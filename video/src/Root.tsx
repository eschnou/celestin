import React from "react";
import { Composition } from "remotion";
import { Celestin, TOTAL_FRAMES } from "./Celestin";

export const RemotionRoot: React.FC = () => (
  <Composition
    id="Celestin"
    component={Celestin}
    durationInFrames={TOTAL_FRAMES}
    fps={30}
    width={1920}
    height={1080}
  />
);
