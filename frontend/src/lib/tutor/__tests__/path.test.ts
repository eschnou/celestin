import { describe, expect, it } from "vitest";
import { sectionStates } from "../path";
import type { Progress } from "../types";
import cases from "./path_cases.json";

type Case = { name: string; progress: Progress; states: Record<string, string> };

const sections = (cases.sections as string[]).map((id) => ({ id }));

/** Copied from `backend/tests/fixtures/path_cases.json`: both sides pass the same table. */
describe("sectionStates mirrors the backend path rules", () => {
  for (const c of cases.cases as Case[]) {
    it(c.name, () => {
      expect(sectionStates(sections, c.progress)).toEqual(c.states);
    });
  }
});
