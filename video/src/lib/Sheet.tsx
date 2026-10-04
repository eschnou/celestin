import React from "react";
import { Math } from "@/components/celestin/math";
import { rise, OUT } from "./ease";
import { HAND } from "./fonts";

const INK = "oklch(0.24 0.015 250)";
const PINK = "oklch(0.94 0.045 350)";
const PEN = "#1f5fbf";
const RED = "#d1322f";

/** Text on the sheet that a highlighter pen sweeps over at a given frame. */
const Hl: React.FC<{
  frame: number;
  at: number;
  color: string;
  children: React.ReactNode;
}> = ({ frame, at, color, children }) => {
  const p = rise(frame, at, at + 16, OUT);
  return (
    <span
      style={{
        backgroundImage: `linear-gradient(${color},${color})`,
        backgroundRepeat: "no-repeat",
        backgroundSize: `${p * 100}% 90%`,
        backgroundPosition: "0 80%",
        padding: "0 4px",
        margin: "0 -4px",
      }}
    >
      {children}
    </span>
  );
};

/** A pen stroke that draws itself: an ellipse around a notation. */
const Circle: React.FC<{ frame: number; at: number; w: number; h: number }> = ({
  frame,
  at,
  w,
  h,
}) => {
  const p = rise(frame, at, at + 20, OUT);
  return (
    <svg
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      style={{ position: "absolute", left: -14, top: -4, overflow: "visible" }}
    >
      <path
        d={`M ${w * 0.5} 3 C ${w * 0.95} -2, ${w + 10} ${h * 0.5}, ${w * 0.7} ${h - 2} C ${w * 0.4} ${h + 6}, -6 ${h * 0.8}, 4 ${h * 0.35} C 10 ${h * 0.1}, ${w * 0.4} 0, ${w * 0.62} 4`}
        fill="none"
        stroke={RED}
        strokeWidth={3.2}
        strokeLinecap="round"
        pathLength={1}
        strokeDasharray={1}
        strokeDashoffset={1 - p}
      />
    </svg>
  );
};

/**
 * The teacher's handout: typed course, a pink highlighter on what the teacher insists on,
 * a pen in the margin. Fixed at 700 × 900; callers scale it.
 */
export const Sheet: React.FC<{ frame?: number; compact?: boolean }> = ({
  frame = 9999,
  compact = false,
}) => (
  <div
    style={{
      position: "relative",
      width: 700,
      height: 900,
      background: "#fffefb",
      color: INK,
      padding: "52px 56px",
      boxSizing: "border-box",
      borderRadius: 6,
      backgroundImage:
        "linear-gradient(to right, transparent 54px, rgba(209,50,47,0.28) 54px, rgba(209,50,47,0.28) 56px, transparent 56px)",
    }}
  >
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        fontSize: 17,
        letterSpacing: 2.4,
        fontWeight: 700,
        color: "oklch(0.53 0.018 250)",
        textTransform: "uppercase",
      }}
    >
      <span>Mathématiques · 5e</span>
      <span>Mme Dubois</span>
    </div>
    <h2 style={{ fontSize: 40, fontWeight: 900, margin: "22px 0 6px", lineHeight: 1.1 }}>
      Chapitre 4 — Suites géométriques
    </h2>
    <div style={{ height: 3, width: 90, background: "oklch(0.55 0.09 183)", borderRadius: 2 }} />

    <p style={{ fontSize: 23, lineHeight: 1.5, marginTop: 28 }}>
      <b>1. Définition.</b> Une suite est{" "}
      <Hl frame={frame} at={70} color="rgba(255, 221, 87, 0.75)">
        <b>géométrique</b>
      </Hl>{" "}
      si l'on passe d'un terme au suivant en multipliant toujours par le même nombre{" "}
      <Math tex="q" />, appelé la{" "}
      <Hl frame={frame} at={78} color="rgba(255, 221, 87, 0.75)">
        <b>raison</b>
      </Hl>
      .
    </p>

    <p style={{ fontSize: 23, lineHeight: 1.5, marginTop: 24 }}>
      <b>2. Somme des <Math tex="n" /> premiers termes.</b>
    </p>
    <div
      style={{
        marginTop: 10,
        background: PINK,
        borderRadius: 10,
        padding: "20px 16px 14px",
        textAlign: "center",
        color: "oklch(0.38 0.09 350)",
        opacity: 1,
      }}
    >
      <div style={{ fontSize: 30 }}>
        <Math tex="S_n = u_1 \cdot \dfrac{1-q^n}{1-q}" />
      </div>
      <div style={{ fontSize: 15, fontWeight: 700, marginTop: 4 }}>à connaître — p. 14</div>
    </div>
    <p style={{ fontSize: 23, lineHeight: 1.5, marginTop: 24 }}>
      Cette formule n'est valable que si{" "}
      <span style={{ position: "relative", display: "inline-block" }}>
        <Math tex="q \neq 1" />
        <Circle frame={frame} at={110} w={92} h={34} />
      </span>
      .
    </p>
    {!compact && (
      <div
        style={{
          marginTop: 22,
          border: "1.5px solid oklch(0.912 0.006 250)",
          borderRadius: 8,
          padding: "14px 18px",
          fontSize: 22,
          background: "oklch(0.968 0.005 240)",
        }}
      >
        <b style={{ fontSize: 15, letterSpacing: 2, color: "oklch(0.53 0.018 250)" }}>EXEMPLE</b>
        <div style={{ marginTop: 4 }}>
          <Hl frame={frame} at={150} color="rgba(255,205,225,0.9)">
            Pour <Math tex="u_1 = 3" /> et <Math tex="q = 2" />, on a <Math tex="S_4 = 45" />.
          </Hl>
        </div>
      </div>
    )}

    <div
      style={{
        position: "absolute",
        right: 52,
        top: 300,
        fontFamily: HAND,
        fontWeight: 700,
        fontSize: 34,
        color: PEN,
        transform: "rotate(-6deg)",
        opacity: rise(frame, 40, 60),
        lineHeight: 1,
      }}
    >
      par cœur !
    </div>
    <div
      style={{
        position: "absolute",
        right: 38,
        bottom: 54,
        fontFamily: HAND,
        fontWeight: 700,
        fontSize: 40,
        color: RED,
        transform: "rotate(-4deg)",
        opacity: rise(frame, 130, 150),
        lineHeight: 1,
      }}
    >
      Interro jeudi !
    </div>
  </div>
);
