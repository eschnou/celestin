import katex from "katex";
import { useMemo } from "react";
import { cn } from "@/lib/utils";

type MathProps = {
  tex: string;
  block?: boolean;
  className?: string;
  /** "mathml" for text only a screen reader reads: KaTeX's html output is aria-hidden. */
  output?: "html" | "mathml";
};

/** Renders TeX with KaTeX. Same typesetting for tutor content and learner input. */
export function Math({ tex, block = false, className, output = "html" }: MathProps) {
  const html = useMemo(() => {
    try {
      return katex.renderToString(tex, {
        displayMode: block,
        throwOnError: false,
        output,
        strict: false,
        trust: false,
      });
    } catch {
      // Never hand unescaped input to innerHTML: the TeX may come from pasted material.
      return tex.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
    }
  }, [tex, block, output]);

  return (
    <span
      className={cn(block && "block text-center", className)}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
