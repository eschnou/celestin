import { Easing, interpolate } from "remotion";

export const OUT = Easing.bezier(0.16, 1, 0.3, 1);
export const INOUT = Easing.bezier(0.65, 0, 0.35, 1);

/** 0 → 1 between two frames, strong ease-out. */
export const rise = (frame: number, from: number, to: number, easing = OUT) =>
  interpolate(frame, [from, to], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing,
  });
