import React from "react";
import { AbsoluteFill, Sequence, interpolate, useCurrentFrame } from "remotion";
import { CardView } from "@/components/celestin/whiteboard";
import { Scrub } from "../lib/Scrub";
import { OUT, rise } from "../lib/ease";
import { SHOWCASE } from "../lib/data";
import { AppWindow, Headline, Marker } from "../lib/ui";

const PER_CARD = 74;
const OVERLAP = 10;
const FIRST = 34;
export const SHOWCASE_FRAMES = FIRST + PER_CARD * SHOWCASE.length + 24;

const CARD = { width: 760, height: 640 };
const SCALE = 1.34;
const STAGE_LEFT = 1920 - 96 - CARD.width * SCALE; // right-aligned stage

/** One card of the stage: the product's own `CardView`, fading out as the next slides in. */
const Slide: React.FC<{ index: number }> = ({ index }) => {
  const frame = useCurrentFrame();
  const last = index === SHOWCASE.length - 1;
  const out = last ? 0 : rise(frame, PER_CARD - 2, PER_CARD + OVERLAP);
  return (
    <AbsoluteFill style={{ opacity: 1 - out }}>
      <Scrub>
        <div className="h-full w-full p-4">
          <CardView card={SHOWCASE[index]!.card} />
        </div>
      </Scrub>
    </AbsoluteFill>
  );
};

export const Showcase: React.FC = () => {
  const frame = useCurrentFrame();
  const current = Math.min(
    SHOWCASE.length - 1,
    Math.max(0, Math.floor((frame - FIRST) / PER_CARD)),
  );
  const started = frame >= FIRST;
  const enter = rise(frame, 8, 40, OUT);
  return (
    <AbsoluteFill className="bg-paper" style={{ color: "oklch(0.24 0.015 250)" }}>
      <div style={{ position: "absolute", left: 120, top: 120, width: 640 }}>
        <Headline
          size={84}
          start={2}
          lines={[
            "Chaque idée",
            <span key="b">
              a son{" "}
              <Marker start={24} duration={22} color="oklch(0.9 0.08 350)">
                tableau.
              </Marker>
            </span>,
          ]}
        />
        <div
          style={{
            marginTop: 30,
            fontSize: 30,
            lineHeight: 1.35,
            color: "oklch(0.45 0.02 250)",
            opacity: rise(frame, 30, 52),
          }}
        >
          Célestin dessine avec les données de ton cours, dans sa notation : virgule décimale,
          intervalles{" "}
          <b style={{ color: "oklch(0.24 0.015 250)", whiteSpace: "nowrap" }}>]a ; b[</b>, suites dès{" "}
          <b style={{ color: "oklch(0.24 0.015 250)" }}>u₁</b>.
        </div>
      </div>

      <div style={{ position: "absolute", left: 120, top: 600 }}>
        {SHOWCASE.map((item, i) => {
          const active = started && i === current;
          const seen = started && i < current;
          const p = rise(frame, 20 + i * 4, 40 + i * 4);
          return (
            <div
              key={item.key}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 18,
                height: 50,
                opacity: p * (active ? 1 : seen ? 0.5 : 0.62),
                transform: `translateX(${(1 - p) * -24}px)`,
                fontSize: 31,
                fontWeight: active ? 900 : 700,
                color: active ? "oklch(0.4 0.07 183)" : "oklch(0.45 0.02 250)",
              }}
            >
              <span
                style={{
                  width: 16,
                  height: 16,
                  borderRadius: 8,
                  background: active ? "oklch(0.55 0.09 183)" : "oklch(0.88 0.01 250)",
                  transform: `scale(${active ? 1.25 : 1})`,
                }}
              />
              {item.label}
            </div>
          );
        })}
      </div>

      <AppWindow
        left={STAGE_LEFT}
        top={(1080 - CARD.height * SCALE) / 2}
        {...CARD}
        scale={SCALE}
        enter={enter}
      >
        <div className="relative h-full w-full bg-paper">
          {SHOWCASE.map((item, i) => (
            <Sequence
              key={item.key}
              from={FIRST + i * PER_CARD}
              durationInFrames={i === SHOWCASE.length - 1 ? PER_CARD + 60 : PER_CARD + OVERLAP}
            >
              <Slide index={i} />
            </Sequence>
          ))}
        </div>
      </AppWindow>
    </AbsoluteFill>
  );
};

void interpolate;
