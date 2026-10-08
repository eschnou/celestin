/** Plural messages in Dutch (spec 017 R1.2): like English, only 1 is singular (0 is « 0 secties »). */
import { describe, expect, it } from "vitest";
import { m } from "@/paraglide/messages";

const nl = { locale: "nl" } as const;

describe("Dutch plurals", () => {
  it("chapter sections", () => {
    expect(m.chapter_status_sections({ count: 0 }, nl)).toBe("0 secties");
    expect(m.chapter_status_sections({ count: 1 }, nl)).toBe("1 sectie");
    expect(m.chapter_status_sections({ count: 2 }, nl)).toBe("2 secties");
  });

  it("characters received (shown is the formatted number)", () => {
    expect(m.chapter_received_chars({ count: 1, shown: "1" }, nl)).toBe("1 teken ontvangen");
    expect(m.chapter_received_chars({ count: 12400, shown: "12.400" }, nl)).toBe(
      "12.400 tekens ontvangen",
    );
  });

  it("course deletion and document pages", () => {
    expect(m.course_delete_description({ count: 1 }, nl)).toContain("1 hoofdstuk, de inhoud ervan");
    expect(m.course_delete_description({ count: 3 }, nl)).toContain("3 hoofdstukken, hun inhoud");
    expect(m.content_document_note({ count: 1 }, nl)).toContain("(1 pagina)");
    expect(m.content_document_note({ count: 5 }, nl)).toContain("(5 pagina's)");
  });

  it("the two-way plural of the course card", () => {
    expect(m.course_card_progress({ total: 1, done: 0 }, nl)).toBe("0 / 1 hoofdstuk afgerond");
    expect(m.course_card_progress({ total: 4, done: 2 }, nl)).toBe("2 / 4 hoofdstukken afgerond");
  });

  it("the board's definitions", () => {
    expect(m.board_definitions({ count: 1 }, nl)).toBe("Definitie");
    expect(m.board_definitions({ count: 2 }, nl)).toBe("Definities");
  });
});
