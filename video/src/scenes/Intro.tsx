import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { Sheet } from "../lib/Sheet";
import { OUT, rise } from "../lib/ease";
import { Headline, TEAL_DEEP } from "../lib/ui";

const PINK = "oklch(0.9 0.08 350)";

/** Little four-point stars, the ones of the logo, drifting slowly in the dark. */
const Stars: React.FC = () => {
  const frame = useCurrentFrame();
  const stars = [
    [110, 140, 26, 0], [640, 90, 16, 20], [880, 300, 22, 8], [180, 880, 18, 30], [760, 960, 28, 14],
    [980, 620, 14, 40], [1860, 120, 20, 5], [1700, 980, 24, 22],
  ] as const;
  return (
    <>
      {stars.map(([x, y, s, d], i) => {
        const tw = 0.55 + 0.45 * Math.sin((frame + d * 4) / 14);
        return (
          <svg
            key={i}
            width={s * 2}
            height={s * 2}
            viewBox="-1 -1 2 2"
            style={{ position: "absolute", left: x, top: y - frame * 0.12, opacity: 0.35 * tw }}
          >
            <path d="M0 -1 Q0.12 -0.12 1 0 Q0.12 0.12 0 1 Q-0.12 0.12 -1 0 Q-0.12 -0.12 0 -1Z" fill="#ffd36b" />
          </svg>
        );
      })}
    </>
  );
};

export const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const sheetIn = rise(frame, 6, 44);
  const float = Math.sin(frame / 38) * 6;
  const marked = frame > 34;
  return (
    <AbsoluteFill style={{ background: TEAL_DEEP, overflow: "hidden" }}>
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(1000px 700px at 1350px 520px, rgba(120,214,214,0.20), transparent 70%)",
        }}
      />
      <Stars />

      <div style={{ position: "absolute", left: 120, top: 250, width: 900 }}>
        <Headline
          size={112}
          color="white"
          start={4}
          gap={10}
          lines={[
            "Ton prof a écrit",
            <span key="m" style={{ position: "relative", display: "inline-block" }}>
              <span
                style={{
                  position: "absolute",
                  left: -16,
                  right: -16,
                  top: "18%",
                  bottom: "2%",
                  background: PINK,
                  borderRadius: 14,
                  transformOrigin: "left",
                  transform: `scaleX(${rise(frame, 24, 48)})`,
                }}
              />
              <span style={{ position: "relative", color: marked ? "#06323c" : "white" }}>
                ton cours.
              </span>
            </span>,
          ]}
        />
        <div style={{ marginTop: 44, fontSize: 46, lineHeight: 1.35, color: "#bfe6e8", fontWeight: 400 }}>
          {["Ses définitions.", "Sa notation.", "Ses exemples."].map((text, i) => {
            const p = rise(frame, 66 + i * 14, 66 + i * 14 + 20);
            return (
              <div
                key={i}
                style={{ opacity: p, transform: `translateX(${(1 - p) * -28}px)`, fontWeight: 700 }}
              >
                {text}
              </div>
            );
          })}
        </div>
        <div
          style={{
            marginTop: 40,
            fontSize: 44,
            fontWeight: 900,
            color: "white",
            opacity: rise(frame, 150, 176),
            transform: `translateY(${(1 - rise(frame, 150, 176)) * 20}px)`,
          }}
        >
          Célestin t'apprend <span style={{ color: "#ffd36b" }}>ce cours-là.</span>
        </div>
      </div>

      <div
        style={{
          position: "absolute",
          left: 1120,
          top: 70 + (1 - sheetIn) * 160 + float,
          width: 700,
          height: 900,
          opacity: sheetIn,
          transform: `rotate(${interpolate(sheetIn, [0, 1], [6, -2.2])}deg) scale(1.0)`,
          boxShadow: "0 50px 100px rgba(0,0,0,0.45), 0 10px 30px rgba(0,0,0,0.25)",
          borderRadius: 6,
        }}
      >
        <Sheet frame={frame} />
      </div>
    </AbsoluteFill>
  );
};
