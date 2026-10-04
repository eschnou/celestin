import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { OUT, rise } from "./ease";

export const TEAL_DEEP = "linear-gradient(135deg, #11636f 0%, #06323c 100%)";

/** Cross-fades a scene in and out over its own sequence. */
export const SceneFade: React.FC<{
  children: React.ReactNode;
  inFrames?: number;
  outFrames?: number;
}> = ({ children, inFrames = 12, outFrames = 12 }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const opacity = interpolate(
    frame,
    [0, inFrames, durationInFrames - outFrames, durationInFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
};

/** The product's own screen at 1280 px logical width, enlarged to read on a video. */
export const AppWindow: React.FC<{
  children: React.ReactNode;
  left: number;
  top: number;
  width: number; // logical px
  height: number; // logical px
  scale: number;
  enter?: number; // 0 → 1
}> = ({ children, left, top, width, height, scale, enter = 1 }) => (
  <div
    style={{
      position: "absolute",
      left,
      top: top + (1 - enter) * 40,
      width: width * scale,
      height: height * scale,
      opacity: enter,
      borderRadius: 20,
      overflow: "hidden",
      background: "white",
      boxShadow: "0 30px 80px rgba(6,50,60,0.22), 0 6px 18px rgba(6,50,60,0.12)",
      border: "1px solid rgba(0,0,0,0.06)",
    }}
  >
    <div
      className="flex flex-col"
      style={{ width, height, transform: `scale(${scale})`, transformOrigin: "top left" }}
    >
      {children}
    </div>
  </div>
);

/** A big headline whose lines rise in one after the other. */
export const Headline: React.FC<{
  lines: React.ReactNode[];
  size: number;
  color?: string;
  start?: number;
  gap?: number; // frames between lines
  weight?: number;
}> = ({ lines, size, color = "oklch(0.24 0.015 250)", start = 0, gap = 8, weight = 900 }) => {
  const frame = useCurrentFrame();
  return (
    <div style={{ fontSize: size, fontWeight: weight, lineHeight: 1.08, color, letterSpacing: -1.5 }}>
      {lines.map((line, i) => {
        const p = rise(frame, start + i * gap, start + i * gap + 22, OUT);
        return (
          <div key={i} style={{ opacity: p, transform: `translateY(${(1 - p) * 34}px)` }}>
            {line}
          </div>
        );
      })}
    </div>
  );
};

/** A pink highlighter stroke that sweeps behind its text — the colour of « ton cours ». */
export const Marker: React.FC<{
  children: React.ReactNode;
  start: number;
  duration?: number;
  color?: string;
}> = ({ children, start, duration = 18, color = "oklch(0.9 0.08 350)" }) => {
  const frame = useCurrentFrame();
  const p = rise(frame, start, start + duration, OUT);
  return (
    <span
      style={{
        backgroundImage: `linear-gradient(${color}, ${color})`,
        backgroundRepeat: "no-repeat",
        backgroundSize: `${p * 100}% 88%`,
        backgroundPosition: "0 70%",
        borderRadius: 8,
        padding: "0 10px",
        margin: "0 -10px",
        boxDecorationBreak: "clone",
      }}
    >
      {children}
    </span>
  );
};

/** What a tutor message looks like while Célestin is still writing it (maths stay whole). */
export function typedPrefix(text: string, progress: number): string {
  const tokens = text.split(/(\$[^$]+\$|\s+)/).filter(Boolean);
  const words = tokens.filter((t) => !/^\s+$/.test(t)).length;
  const keep = Math.ceil(Math.min(Math.max(progress, 0), 1) * words);
  const out: string[] = [];
  let seen = 0;
  for (const token of tokens) {
    if (!/^\s+$/.test(token)) {
      if (seen >= keep) break;
      seen += 1;
    }
    out.push(token);
  }
  return out.join("").trimEnd();
}
