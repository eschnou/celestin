// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/celestin/math", () => ({
  Math: ({ tex, block }: { tex: string; block?: boolean }) => (
    <span data-testid={block ? "math-block" : "math-inline"}>{tex}</span>
  ),
}));

import { PackView } from "../content/pack-view";

afterEach(cleanup);

describe("PackView", () => {
  it("renders headings, lists and GFM tables", () => {
    const { container } = render(
      <PackView
        markdown={"# Titre\n\n## 1. Objectif\n\n- un\n- deux\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"}
      />,
    );
    expect(container.querySelector("h1")).toBeNull(); // the page owns its h1
    expect(container.querySelector("h2")?.textContent).toBe("Titre");
    expect(container.querySelector("h3")?.textContent).toBe("1. Objectif");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.querySelectorAll("td")).toHaveLength(2);
  });

  it("sends inline and display math through Math", () => {
    const { getByTestId } = render(
      <PackView markdown={"La vitesse $v = \\frac{d}{t}$.\n\n$$\nx = x_0 + v t\n$$\n"} />,
    );
    expect(getByTestId("math-inline").textContent).toBe("v = \\frac{d}{t}");
    expect(getByTestId("math-block").textContent).toContain("x = x_0 + v t");
  });

  it("never executes or links anything from the material", () => {
    const hostile =
      '# T\n\n<script>window.__pwned = 1</script>\n\n<img src=x onerror="window.__pwned = 2">\n\n' +
      "[clique](javascript:alert(1)) et ![image](https://example.com/x.png)\n";
    const { container } = render(<PackView markdown={hostile} />);
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).toContain("clique");
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
  });
});
