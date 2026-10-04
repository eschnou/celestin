import { ChartView } from "./charts/chart-view";
import { FigureView } from "./figure/figure-view";
import { FlowchartView } from "./flowchart/flowchart-view";
import { PlotView } from "./plot/plot-view";
import { Math } from "./math";
import { cn } from "@/lib/utils";
import type { Block } from "@/lib/tutor/types";
import { m } from "@/paraglide/messages";
import { getLocale } from "@/paraglide/runtime";

/**
 * Renders tutor-written content.
 *
 * Nothing the model writes is ever turned into HTML. Prose becomes React text
 * nodes and maths goes through KaTeX, which runs with `trust: false`. That is
 * the whole reason the board takes typed blocks rather than Markdown.
 */

export type MathPart = { math: boolean; value: string; display?: boolean; strong?: boolean };

const isSpace = (c: string | undefined) => c === undefined || /\s/.test(c);
const isDigit = (c: string | undefined) => c !== undefined && c >= "0" && c <= "9";

/**
 * Splits prose into text and maths.
 *
 * Handles both delimiters the model emits: `$$…$$` for a formula on its own line
 * and `$…$` inline.
 *
 * A bare `$` is ambiguous in this course — prices appear throughout the
 * depreciation exercises — so it opens maths only when it hugs its content and
 * does not follow a figure. In "Le prix est 30$ et $x^2$ vaut 4", the dollar after
 * 30 fails both tests, which leaves `$x^2$` to pair correctly. Pairing greedily
 * instead typeset " et " as maths and spilled the rest out as raw LaTeX.
 */
export function splitInlineMath(text: string): MathPart[] {
  const parts: MathPart[] = [];
  let plain = "";
  let i = 0;

  const flush = () => {
    if (plain) parts.push({ math: false, value: plain });
    plain = "";
  };

  while (i < text.length) {
    if (text[i] !== "$") {
      plain += text[i];
      i += 1;
      continue;
    }

    const display = text.startsWith("$$", i);
    const delimiter = display ? "$$" : "$";
    const contentStart = i + delimiter.length;
    const close = findClose(text, contentStart, delimiter);

    if (close === -1) {
      plain += delimiter;
      i = contentStart;
      continue;
    }

    flush();
    parts.push({ math: true, value: text.slice(contentStart, close), display });
    i = close + delimiter.length;
  }

  flush();
  return parts.length > 0 ? parts : [{ math: false, value: text }];
}

/** Index of the closing delimiter, or -1 if this `$` does not open maths. */
function findClose(text: string, contentStart: number, delimiter: string): number {
  if (delimiter === "$") {
    // Inline maths must not begin with whitespace, so "30$ et" cannot open …
    if (isSpace(text[contentStart])) return -1;
    // … and a dollar straight after a figure is a price, so "20$," cannot either.
    if (isDigit(text[contentStart - 2])) return -1;
  }

  let from = contentStart;
  while (from < text.length) {
    const close = text.indexOf(delimiter, from);
    if (close === -1 || close === contentStart) return -1;
    // …and must not end with whitespace, so "$q$ et 30$" cannot close on the price.
    if (delimiter === "$$" || !isSpace(text[close - 1])) return close;
    from = close + 1;
  }
  return -1;
}

const escapeRegExp = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * Marks the first occurrence of `term` in the prose parts as strong.
 *
 * Case and runs of whitespace are ignored, as the backend does when it checks that
 * a definition contains its term; a term only found inside maths stays unmarked.
 */
export function markTerm(parts: MathPart[], term: string): MathPart[] {
  const words = term.trim().split(/\s+/).filter(Boolean).map(escapeRegExp);
  if (words.length === 0) return parts;
  const pattern = new RegExp(words.join("\\s+"), "iu");

  const at = parts.findIndex((part) => !part.math && pattern.test(part.value));
  const part = parts[at];
  const match = part && pattern.exec(part.value);
  if (!part || !match) return parts;

  const end = match.index + match[0].length;
  const split: MathPart[] = [
    { math: false, value: part.value.slice(0, match.index) },
    { math: false, value: match[0], strong: true },
    { math: false, value: part.value.slice(end) },
  ].filter((p) => p.value);
  return [...parts.slice(0, at), ...split, ...parts.slice(at + 1)];
}

export function RichText({
  text,
  className,
  term,
  mathOutput,
}: {
  text: string;
  className?: string;
  /** Set in bold where it first appears: the word a definition defines. */
  term?: string;
  /** "mathml" inside screen-reader-only text: KaTeX's html output is aria-hidden. */
  mathOutput?: "html" | "mathml";
}) {
  const parts = splitInlineMath(text);
  return (
    <span className={className}>
      {(term ? markTerm(parts, term) : parts).map((part, i) =>
        part.math ? (
          <Math
            key={i}
            tex={part.value}
            block={part.display ?? false}
            output={mathOutput ?? "html"}
          />
        ) : part.strong ? (
          <strong key={i} className="font-semibold whitespace-pre-wrap">
            {part.value}
          </strong>
        ) : (
          <span key={i} className="whitespace-pre-wrap">
            {part.value}
          </span>
        ),
      )}
    </span>
  );
}

export function BlockView({ block }: { block: Block }) {
  switch (block.type) {
    case "text":
      return (
        <p className="text-[15px] leading-relaxed">
          <RichText text={block.text} />
        </p>
      );

    case "quote":
      return (
        <div className={cn("course-quote px-6 py-5", block.tex && "math-display")}>
          {block.tex ? (
            <Math block tex={block.tex} />
          ) : (
            <p className="text-[15px] leading-relaxed">
              <RichText text={block.text ?? ""} />
            </p>
          )}
          <p className="mt-3 text-center text-xs font-semibold tracking-wide">
            <RichText text={block.caption} />
          </p>
        </div>
      );

    case "definition":
      return (
        <div className="course-quote px-6 py-5">
          <p
            lang={getLocale()}
            className="text-xs font-bold tracking-[0.12em] uppercase opacity-70"
          >
            {m.board_definitions({ count: block.entries.length })}
          </p>
          <dl className="mt-3 divide-y divide-quote-foreground/15">
            {block.entries.map((entry, i) => (
              <div
                key={i}
                className="grid gap-x-6 gap-y-1 py-3 first:pt-0 last:pb-0 sm:grid-cols-[9rem_1fr]"
              >
                <dt className="text-[15px] leading-relaxed font-semibold first-letter:uppercase">
                  {entry.term}
                </dt>
                <dd className="text-[15px] leading-relaxed">
                  <RichText text={entry.text} term={entry.term} />
                </dd>
              </div>
            ))}
          </dl>
        </div>
      );

    case "chart":
      return <ChartView block={block} />;

    case "flowchart":
      return <FlowchartView block={block} />;

    case "figure":
      return <FigureView block={block} />;

    case "plot":
      return <PlotView block={block} />;

    case "formula":
      return (
        <div className="math-display rounded-lg border border-border bg-card px-5 py-4">
          <Math block tex={block.tex} />
          {block.caption && (
            <p className="mt-2 text-center text-xs text-muted-foreground">
              <RichText text={block.caption} />
            </p>
          )}
        </div>
      );

    case "note":
      return (
        <div className="rounded-lg border border-border bg-secondary/60 px-5 py-4">
          <p className="text-xs font-bold tracking-[0.12em] text-muted-foreground uppercase">
            {block.label}
          </p>
          <p className="mt-2 text-[15px]">
            <RichText text={block.text} />
          </p>
        </div>
      );

    default:
      return null;
  }
}

export function Blocks({ blocks, className }: { blocks: Block[]; className?: string }) {
  return (
    <div className={cn("space-y-6", className)}>
      {blocks.map((block, i) => (
        <BlockView key={i} block={block} />
      ))}
    </div>
  );
}
