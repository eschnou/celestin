// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// Real KaTeX, unless a test makes it give up.
const katexFails = vi.hoisted(() => ({ now: false }));

vi.mock("katex", async (importOriginal) => {
  const actual = (await importOriginal<typeof import("katex")>()).default;
  return {
    default: {
      ...actual,
      renderToString: (...args: Parameters<typeof actual.renderToString>) => {
        if (katexFails.now) throw new Error("boom");
        return actual.renderToString(...args);
      },
    },
  };
});

import { Math } from "../math";

afterEach(() => {
  katexFails.now = false;
  cleanup();
});

it("escapes the TeX when KaTeX gives up, so pasted material never becomes HTML", () => {
  katexFails.now = true;
  const { container } = render(<Math tex={'<img src=x onerror="alert(1)">'} />);
  expect(container.querySelector("img")).toBeNull();
  expect(container.textContent).toBe('<img src=x onerror="alert(1)">');
});

describe("output", () => {
  it("renders KaTeX's html by default, which screen readers skip", () => {
    const { container } = render(<Math tex="u_n = 2n" />);
    expect(container.querySelector(".katex-html")).not.toBeNull();
    expect(container.querySelector("math")).toBeNull();
  });

  it('renders MathML only with output="mathml", for text a screen reader reads', () => {
    const { container } = render(<Math tex="u_n = 2n" output="mathml" />);
    const math = container.querySelector("math");
    expect(math).not.toBeNull();
    expect(math?.textContent).toContain("u");
    expect(container.querySelector(".katex-html")).toBeNull();
  });

  it("escapes the TeX in either output when KaTeX gives up", () => {
    katexFails.now = true;
    const { container } = render(<Math tex="<b>x</b>" output="mathml" />);
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toBe("<b>x</b>");
  });
});
