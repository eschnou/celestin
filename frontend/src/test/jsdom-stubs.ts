// jsdom has neither `matchMedia` nor `ResizeObserver`. `matches: false` takes the phone
// layout (the board over a caption and the composer), which needs no resizable panels;
// `{ desktop: true }` takes the two columns. Call it from `beforeEach` (vitest unstubs after).
import { vi } from "vitest";

export function stubLayoutApis({ desktop = false }: { desktop?: boolean } = {}): void {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: desktop,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
}
