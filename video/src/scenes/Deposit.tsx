import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { Check, FileText, Lock } from "lucide-react";
import { ChapterRowItem } from "@/components/celestin/chapter-row";
import { KIND_LABEL } from "@/lib/tutor/labels";
import type { ChapterRow } from "@/lib/tutor/types";
import { Scrub } from "../lib/Scrub";
import { Sheet } from "../lib/Sheet";
import { OUT, rise } from "../lib/ease";
import { CHAPTER, ROW } from "../lib/data";

const NOOP = () => {};

const STEPS = [
  { at: 6, title: "Tu déposes ton cours", sub: "Un PDF, ou des photos de tes pages." },
  { at: 100, title: "Célestin le lit", sub: "Page par page : texte, écriture, schémas." },
  { at: 196, title: "Il en fait un parcours", sub: "Leçons, exercices, synthèse — dans l'ordre de ton prof." },
];

const Step: React.FC<{ index: number; at: number; next: number; title: string; sub: string }> = ({
  index,
  at,
  next,
  title,
  sub,
}) => {
  const frame = useCurrentFrame();
  const p = rise(frame, at, at + 22, OUT);
  const current = frame >= at && frame < next;
  const dim = frame >= next ? 0.55 : 1;
  return (
    <div
      style={{
        display: "flex",
        gap: 28,
        alignItems: "flex-start",
        opacity: p * dim,
        transform: `translateX(${(1 - p) * -40}px)`,
        marginBottom: 54,
      }}
    >
      <div
        style={{
          width: 72,
          height: 72,
          flex: "none",
          borderRadius: 36,
          background: current ? "oklch(0.55 0.09 183)" : "oklch(0.58 0.11 155)",
          color: "white",
          fontSize: 38,
          fontWeight: 900,
          display: "grid",
          placeItems: "center",
        }}
      >
        {current ? index : <Check size={38} strokeWidth={3.5} />}
      </div>
      <div>
        <div style={{ fontSize: 56, fontWeight: 900, lineHeight: 1.1, letterSpacing: -1 }}>{title}</div>
        <div style={{ fontSize: 31, marginTop: 8, color: "oklch(0.45 0.02 250)", lineHeight: 1.3, maxWidth: 740 }}>
          {sub}
        </div>
      </div>
    </div>
  );
};

/** Pages fall into the drop zone one after the other. */
const Dropzone: React.FC = () => {
  const frame = useCurrentFrame();
  const enter = rise(frame, 0, 20);
  const leave = rise(frame, 84, 104);
  const pages = [0, 1, 2, 3];
  return (
    <div
      style={{
        position: "absolute",
        left: 1020,
        top: 230,
        width: 780,
        height: 560,
        opacity: enter * (1 - leave),
        transform: `scale(${1 - leave * 0.06})`,
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          borderRadius: 28,
          border: "4px dashed oklch(0.55 0.09 183 / 0.55)",
          background: "oklch(0.955 0.02 183 / 0.6)",
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 36,
          left: 0,
          right: 0,
          textAlign: "center",
          fontSize: 30,
          fontWeight: 700,
          color: "oklch(0.4 0.07 183)",
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          gap: 12,
        }}
      >
        <FileText size={34} /> Dépose ton cours ici
      </div>
      {pages.map((i) => {
        const start = 14 + i * 12;
        const drop = rise(frame, start, start + 22, OUT);
        const x = 36 + i * 170;
        const rot = [-6, 3, -3, 5][i]!;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: x,
              top: 110 + (1 - drop) * -520 + (i % 2) * 14,
              width: 224,
              height: 288,
              opacity: drop,
              transform: `rotate(${rot}deg)`,
              boxShadow: "0 12px 30px rgba(6,50,60,0.22)",
              overflow: "hidden",
              borderRadius: 4,
              background: "white",
            }}
          >
            <div style={{ transform: "scale(0.32)", transformOrigin: "top left", width: 700, height: 900 }}>
              <Sheet compact />
            </div>
          </div>
        );
      })}
      <div
        style={{
          position: "absolute",
          bottom: 30,
          left: 0,
          right: 0,
          textAlign: "center",
          fontSize: 28,
          fontWeight: 700,
          color: "oklch(0.4 0.07 183)",
          opacity: rise(frame, 62, 76),
        }}
      >
        4 pages · cours de maths
      </div>
    </div>
  );
};

/** The same two dots the chapter map draws: open for the next section, a lock for the rest. */
const SECTION_DOT = (open: boolean) =>
  open ? (
    <span
      style={{
        width: 36,
        height: 36,
        borderRadius: 18,
        flex: "none",
        border: "3px solid oklch(0.55 0.09 183 / 0.5)",
        background: "white",
      }}
    />
  ) : (
    <span
      style={{
        width: 36,
        height: 36,
        borderRadius: 18,
        flex: "none",
        display: "grid",
        placeItems: "center",
        border: "2px solid oklch(0.912 0.006 250)",
        color: "oklch(0.53 0.018 250)",
      }}
    >
      <Lock size={16} />
    </span>
  );

/** Pages being read: a scan line sweeps each one, then it is ticked. */
const Reading: React.FC = () => {
  const frame = useCurrentFrame();
  const show = rise(frame, 112, 128) * (1 - rise(frame, 192, 206));
  return (
    <div
      style={{
        position: "absolute",
        left: 1020,
        top: 560,
        width: 784,
        display: "flex",
        justifyContent: "space-between",
        opacity: show,
      }}
    >
      {[0, 1, 2, 3].map((i) => {
        const start = 108 + i * 14;
        const scan = rise(frame, start, start + 14, (t) => t);
        const done = frame >= start + 14;
        return (
          <div
            key={i}
            style={{
              position: "relative",
              width: 180,
              height: 232,
              overflow: "hidden",
              borderRadius: 4,
              boxShadow: "0 10px 24px rgba(6,50,60,0.18)",
              background: "white",
            }}
          >
            <div style={{ transform: "scale(0.257)", transformOrigin: "top left", width: 700, height: 900 }}>
              <Sheet compact />
            </div>
            {!done && scan > 0 && (
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  right: 0,
                  top: `${scan * 100}%`,
                  height: 4,
                  background: "oklch(0.55 0.09 183)",
                  boxShadow: "0 0 18px 6px oklch(0.55 0.09 183 / 0.45)",
                }}
              />
            )}
            {done && (
              <span
                style={{
                  position: "absolute",
                  right: 10,
                  top: 10,
                  width: 34,
                  height: 34,
                  borderRadius: 17,
                  background: "oklch(0.58 0.11 155)",
                  color: "white",
                  display: "grid",
                  placeItems: "center",
                }}
              >
                <Check size={20} strokeWidth={3.5} />
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
};

const rowAt = (frame: number): ChapterRow => {
  if (frame < 196) {
    const stage = frame < 168 ? "transcription" : frame < 182 ? "pack" : "curriculum";
    const pages = Math.min(4, Math.max(0, Math.floor((frame - 108) / 14)));
    return { ...ROW, authoring_stage: stage, pages_done: pages };
  }
  return {
    ...ROW,
    ready: true,
    authoring_state: "idle",
    authoring_stage: null,
    section_count: CHAPTER.sections.length,
    state: "not_started",
    pages_done: 4,
  };
};

export const Deposit: React.FC = () => {
  const frame = useCurrentFrame();
  const rowIn = rise(frame, 96, 120, OUT);
  const rowTop = interpolate(frame, [214, 250], [330, 150], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: OUT,
  });
  return (
    <AbsoluteFill className="bg-paper" style={{ color: "oklch(0.24 0.015 250)" }}>
      <div style={{ position: "absolute", left: 120, top: 190, width: 880 }}>
        {STEPS.map((step, i) => (
          <Step key={i} index={i + 1} next={STEPS[i + 1]?.at ?? 9999} {...step} />
        ))}
      </div>

      <Dropzone />

      <div
        style={{
          position: "absolute",
          left: 1020,
          top: rowTop,
          width: 560,
          opacity: rowIn,
          transform: `translateY(${(1 - rowIn) * 30}px) scale(1.4)`,
          transformOrigin: "top left",
        }}
      >
        <Scrub>
          <ul>
            <ChapterRowItem
              courseId="c1"
              row={rowAt(frame)}
              index={4}
              onRetry={NOOP}
              onDelete={NOOP}
              busy={false}
            />
          </ul>
        </Scrub>
      </div>

      <Reading />

      {CHAPTER.sections.map((section, i) => {
        const at = 232 + i * 9;
        const p = rise(frame, at, at + 18, OUT);
        return (
          <div
            key={section.id}
            style={{
              position: "absolute",
              left: 1020,
              top: 460 + i * 100,
              width: 784,
              height: 84,
              display: "flex",
              alignItems: "center",
              gap: 20,
              padding: "0 26px",
              borderRadius: 16,
              background: "white",
              border: "1px solid oklch(0.912 0.006 250)",
              boxShadow: "0 1px 2px oklch(0.26 0.015 250 / 0.06), 0 4px 14px oklch(0.26 0.015 250 / 0.05)",
              opacity: p,
              transform: `translateY(${(1 - p) * 24}px)`,
            }}
          >
            {SECTION_DOT(i === 0)}
            <span
              style={{
                fontSize: 17,
                fontWeight: 700,
                letterSpacing: 2.4,
                textTransform: "uppercase",
                color: "oklch(0.55 0.09 183)",
                width: 190,
                whiteSpace: "nowrap",
              }}
            >
              {i + 1} · {KIND_LABEL[section.kind]()}
            </span>
            <span style={{ fontSize: 27, fontWeight: 700, whiteSpace: "nowrap" }}>{section.title}</span>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
