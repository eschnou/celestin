import React, { useEffect, useRef } from "react";
import { AbsoluteFill, Sequence, continueRender, delayRender, useCurrentFrame } from "remotion";
import { BookOpen, EyeOff, ShieldCheck } from "lucide-react";
import { CardView } from "@/components/celestin/whiteboard";
import { Scrub } from "../lib/Scrub";
import { OUT, rise } from "../lib/ease";
import { CHECK, EXERCISE_STATS, EXPLANATION } from "../lib/data";
import { AppWindow, Headline, Marker } from "../lib/ui";

const CARD = { width: 760, height: 540 };
const SCALE = 1.34;
export const GUARANTEES_FRAMES = 420;

const PROMISES = [
  {
    at: 30,
    to: 150,
    icon: BookOpen,
    title: "Ton cours, rien que ton cours",
    sub: "Définitions, formules, notation : celles de ta feuille.",
  },
  {
    at: 150,
    to: 270,
    icon: EyeOff,
    title: "Pas de réponse pendant l'exercice",
    sub: "Il explique, questionne, donne des indices.",
  },
  {
    at: 270,
    to: 999,
    icon: ShieldCheck,
    title: "Chaque réponse est vérifiée",
    sub: "Un vérificateur tranche, pas une impression.",
  },
];

/** Plays a learner's clicks on the real card, at given frames, whatever frame we land on. */
const ClickScript: React.FC<{
  children: React.ReactNode;
  steps: { frame: number; text: string }[];
}> = ({ children, steps }) => {
  const frame = useCurrentFrame();
  const ref = useRef<HTMLDivElement>(null);
  const passed = steps.filter((s) => frame >= s.frame).length;
  useEffect(() => {
    const handle = delayRender("clicks");
    for (const step of steps.slice(0, passed)) {
      const button = [...(ref.current?.querySelectorAll("button") ?? [])].find((b) =>
        b.textContent?.includes(step.text),
      );
      button?.click();
    }
    const id = requestAnimationFrame(() => requestAnimationFrame(() => continueRender(handle)));
    return () => {
      cancelAnimationFrame(id);
      continueRender(handle);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [passed]);
  return <div ref={ref} className="h-full w-full">{children}</div>;
};

const Stage: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const frame = useCurrentFrame();
  const p = rise(frame, 0, 14);
  return (
    <AbsoluteFill style={{ opacity: p }}>
      <Scrub>
        <div className="h-full w-full bg-paper p-4">{children}</div>
      </Scrub>
    </AbsoluteFill>
  );
};

export const Guarantees: React.FC = () => {
  const frame = useCurrentFrame();
  const enter = rise(frame, 8, 40, OUT);
  return (
    <AbsoluteFill className="bg-paper" style={{ color: "oklch(0.24 0.015 250)" }}>
      <div style={{ position: "absolute", left: 120, top: 130, width: 700 }}>
        <Headline
          size={76}
          start={2}
          lines={[
            "Fidèle à ton cours.",
            <span key="b">
              <Marker start={26} duration={22} color="oklch(0.9 0.08 350)">
                Honnête
              </Marker>{" "}
              avec toi.
            </span>,
          ]}
        />
      </div>

      <div style={{ position: "absolute", left: 120, top: 470, width: 650 }}>
        {PROMISES.map((promise, i) => {
          const p = rise(frame, promise.at - 8, promise.at + 14, OUT);
          const active = frame >= promise.at - 8 && frame < promise.to;
          const Icon = promise.icon;
          return (
            <div
              key={i}
              style={{
                display: "flex",
                gap: 24,
                marginBottom: 36,
                opacity: p * (active ? 1 : 0.5),
                transform: `translateX(${(1 - p) * -34}px)`,
              }}
            >
              <div
                style={{
                  width: 76,
                  height: 76,
                  flex: "none",
                  borderRadius: 20,
                  display: "grid",
                  placeItems: "center",
                  background: active ? "oklch(0.55 0.09 183)" : "oklch(0.955 0.02 183)",
                  color: active ? "white" : "oklch(0.4 0.07 183)",
                }}
              >
                <Icon size={38} />
              </div>
              <div>
                <div style={{ fontSize: 35, fontWeight: 900, lineHeight: 1.15 }}>{promise.title}</div>
                <div style={{ fontSize: 25, marginTop: 6, lineHeight: 1.3, color: "oklch(0.45 0.02 250)" }}>
                  {promise.sub}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <AppWindow
        left={1920 - 96 - CARD.width * SCALE}
        top={(1080 - CARD.height * SCALE) / 2}
        {...CARD}
        scale={SCALE}
        enter={enter}
      >
        <div className="relative h-full w-full bg-paper">
          <Sequence from={14} durationInFrames={136}>
            <Stage>
              <CardView card={EXPLANATION} />
            </Stage>
          </Sequence>
          <Sequence from={150} durationInFrames={120}>
            <Stage>
              <CardView card={EXERCISE_STATS} />
            </Stage>
          </Sequence>
          <Sequence from={270} durationInFrames={GUARANTEES_FRAMES - 270}>
            <Stage>
              <ClickScript
                steps={[
                  { frame: 50, text: "toujours être grand" },
                  { frame: 96, text: "serait nul" },
                ]}
              >
                <CardView card={CHECK} />
              </ClickScript>
            </Stage>
          </Sequence>
        </div>
      </AppWindow>
    </AbsoluteFill>
  );
};
