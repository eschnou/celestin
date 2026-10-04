/**
 * The pack as the student reads it (005 design 3.16). Markdown from pasted material
 * and from the model, so: no raw HTML, no links, no images, and every formula
 * through `Math` (KaTeX, `trust: false`), the single math entry point.
 */

import type { Element } from "hast";
import type { ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { Math } from "@/components/celestin/math";
import { useCourseLanguage } from "@/lib/course-language";

function classesOf(node: Element | undefined): string[] {
  const value = node?.properties?.["className"];
  return Array.isArray(value) ? value.map(String) : [];
}

function textOf(children: ReactNode): string {
  if (typeof children === "string") return children;
  if (Array.isArray(children)) return children.map(textOf).join("");
  return "";
}

const components: Components = {
  // One level down: the page that shows the pack has its own h1.
  h1: ({ children }) => <h2 className="mt-2 text-2xl font-bold">{children}</h2>,
  h2: ({ children }) => (
    <h3 className="mt-8 border-b border-border pb-1 text-xl font-bold">{children}</h3>
  ),
  h3: ({ children }) => <h4 className="mt-6 text-lg font-semibold">{children}</h4>,
  h4: ({ children }) => <h5 className="mt-5 text-base font-semibold">{children}</h5>,
  p: ({ children }) => <p className="mt-3 leading-relaxed">{children}</p>,
  ul: ({ children }) => <ul className="mt-3 list-disc space-y-1 pl-6">{children}</ul>,
  ol: ({ children }) => <ol className="mt-3 list-decimal space-y-1 pl-6">{children}</ol>,
  blockquote: ({ children }) => <blockquote className="course-quote mt-3">{children}</blockquote>,
  table: ({ children }) => (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-border bg-secondary px-2 py-1 text-left">{children}</th>
  ),
  td: ({ children }) => <td className="border border-border px-2 py-1 align-top">{children}</td>,
  hr: () => <hr className="my-6 border-border" />,
  // No navigation out of the student's material: a link is its text.
  a: ({ children }) => <span>{children}</span>,
  img: () => null,
  pre: ({ node, children }) => {
    const code = node?.children[0] as Element | undefined;
    if (classesOf(code).includes("language-math")) return <>{children}</>;
    return (
      <pre className="mt-3 overflow-x-auto rounded-md bg-secondary p-3 text-xs">{children}</pre>
    );
  },
  code: ({ node, children }) => {
    const classes = classesOf(node);
    if (classes.includes("language-math")) {
      return <Math tex={textOf(children)} block={classes.includes("math-display")} />;
    }
    return <code className="rounded bg-secondary px-1 text-[0.9em]">{children}</code>;
  },
};

export function PackView({ markdown }: { markdown: string }) {
  const language = useCourseLanguage();
  return (
    <article lang={language} className="text-sm text-foreground">
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} components={components} skipHtml>
        {markdown}
      </ReactMarkdown>
    </article>
  );
}
