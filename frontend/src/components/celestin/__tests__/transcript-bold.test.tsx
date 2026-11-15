// @vitest-environment jsdom
/** Célestin's `**…**` is bold in the transcript, as on a phone's caption; her own words stay
 *  literal; `$…$` stays maths in both. */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/celestin/math", () => ({
  Math: ({ tex }: { tex: string }) => <span data-math>{tex}</span>,
}));

import { Entry } from "../transcript";

afterEach(cleanup);

describe("the transcript's text", () => {
  it("renders the tutor's **bold** as bold, with its maths", () => {
    const { container } = render(
      <Entry
        entry={{ id: "t", role: "tutor", text: "La **raison** vaut $q = 2$.", blockId: 0 }}
        onShowBoard={vi.fn()}
      />,
    );
    expect(container.textContent).not.toContain("**");
    expect(container.querySelector("strong")?.textContent).toBe("raison");
    expect(container.querySelector("[data-math]")?.textContent).toBe("q = 2");
  });

  it("keeps the learner's asterisks as she typed them", () => {
    const { container } = render(
      <Entry
        entry={{ id: "l", role: "learner", text: "c'est **ça** ? $x^2$" }}
        onShowBoard={vi.fn()}
      />,
    );
    expect(container.textContent).toContain("**ça**");
    expect(container.querySelector("strong")).toBeNull();
    expect(container.querySelector("[data-math]")?.textContent).toBe("x^2");
  });
});
