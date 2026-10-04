import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import celestinMark from "@/assets/celestin-mark.svg";
import { APP_NAME } from "@/lib/brand";
import { rise } from "../lib/ease";
import { TEAL_DEEP } from "../lib/ui";

export const Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame: frame - 6, fps, config: { damping: 14, stiffness: 120 } });
  const glow = 0.5 + 0.5 * Math.sin(frame / 18);
  const lines = ["Ton cours.", "Ton prof.", "Ta notation."];
  return (
    <AbsoluteFill
      style={{ background: TEAL_DEEP, alignItems: "center", justifyContent: "center", overflow: "hidden" }}
    >
      <AbsoluteFill
        style={{
          background: `radial-gradient(760px 520px at 50% 40%, rgba(120,214,214,${0.16 + glow * 0.05}), transparent 70%)`,
        }}
      />
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", color: "white" }}>
        <img
          src={celestinMark}
          alt=""
          style={{
            display: "block",
            width: 230,
            height: 230,
            transform: `scale(${pop}) rotate(${(1 - pop) * -12}deg)`,
            filter: "drop-shadow(0 24px 40px rgba(0,0,0,0.35))",
          }}
        />
        <div
          style={{
            fontSize: 168,
            fontWeight: 900,
            letterSpacing: -4,
            lineHeight: 1,
            marginTop: 26,
            opacity: rise(frame, 22, 46),
            transform: `translateY(${(1 - rise(frame, 22, 46)) * 30}px)`,
          }}
        >
          {APP_NAME}
        </div>
        <div
          style={{
            fontSize: 52,
            marginTop: 24,
            fontWeight: 400,
            color: "#bfe6e8",
            opacity: rise(frame, 46, 72),
            transform: `translateY(${(1 - rise(frame, 46, 72)) * 20}px)`,
          }}
        >
          Le tuteur qui apprend avec toi le cours de ton prof.
        </div>
        <div style={{ display: "flex", gap: 44, justifyContent: "center", marginTop: 56 }}>
          {lines.map((text, i) => {
            const p = rise(frame, 96 + i * 12, 96 + i * 12 + 20);
            return (
              <div
                key={text}
                style={{
                  fontSize: 44,
                  fontWeight: 900,
                  color: "#ffd36b",
                  opacity: p,
                  transform: `translateY(${(1 - p) * 18}px)`,
                }}
              >
                {text}
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

void interpolate;
