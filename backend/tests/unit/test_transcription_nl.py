"""Spec 017 R4.1, R4.3: the transcription's marks in a Dutch course. French and English stay in
`test_transcription.py` and `test_transcription_en.py`, untouched."""

from __future__ import annotations

from app.domain.pack import chapter_title
from app.domain.transcription import (
    MARKERS,
    apply_uncertain,
    count_markers,
    handwritten_numbers,
    validate_batch,
)

NL_BATCH = "--- page 3 ---\nGetypte regel\n[handgeschreven: 330]\n--- page 4 ---\n[lege pagina]"


def test_the_dutch_marks() -> None:
    nl = MARKERS["nl"]
    assert (nl.handwritten, nl.uncertain, nl.illegible, nl.empty_page) == (
        "[handgeschreven", "[onzeker", "[onleesbaar]", "[lege pagina]",
    )
    assert nl.nothing == "[niets leesbaar]"


def test_a_dutch_batch_is_validated_with_the_page_markers_only() -> None:
    text, issues = validate_batch(NL_BATCH, [3, 4], "nl")
    assert issues == [] and text is not None
    assert text.startswith("--- page 3 ---\n\nGetypte regel") and "--- page 4 ---\n\n[lege pagina]" in text


def test_the_issues_are_worded_in_dutch() -> None:
    assert validate_batch("--- page 3 ---\nx", [3, 4], "nl")[1][0].message == "ontbrekende markering voor pagina 4"
    assert validate_batch("--- page 3 ---\nx\n--- page 5 ---\ny", [3], "nl")[1][0].message == "onverwachte pagina 5"
    assert "verkeerde volgorde" in validate_batch("--- page 4 ---\nx\n--- page 3 ---\ny", [3, 4], "nl")[1][0].message
    assert validate_batch("--- page 1 ---\n\n--- page 2 ---\nx", [1, 2], "nl")[1][0].message == (
        "lege pagina zonder “[lege pagina]”"
    )


def test_marks_are_counted_and_rewritten_in_dutch() -> None:
    text = "voor [handgeschreven: 12] en [onzeker: 4 | 9] en [onleesbaar]\n[handgeschreven: 330 m]"
    counts = count_markers(text, "nl")
    assert (counts.handwritten, counts.uncertain, counts.illegible) == (2, 1, 1)
    page = "--- page 1 ---\nGetypte regel 7\n[handgeschreven] $33 \\cdot 10 = $ 330"
    candidates = handwritten_numbers(page, "nl")
    assert [line for _, line in candidates] == ["[handgeschreven] $33 \\cdot 10 = $ 330"]
    index, line = candidates[0]
    rewritten = apply_uncertain(page, [(index, line, "[handgeschreven] $33 \\cdot 10 = $ [onzeker: 330 | 350]")], "nl")
    assert "[onzeker: 330 | 350]" in rewritten
    # Only a rewrite that marks a doubt, in this language, is applied.
    assert apply_uncertain(page, [(index, line, "[handgeschreven] 999")], "nl") == page
    assert apply_uncertain(page, [(index, line, "[incertain: x]")], "nl") == page
    assert handwritten_numbers(page) == []  # French marks are not looked for in Dutch text


def test_a_french_mark_is_not_counted_in_a_dutch_course() -> None:
    assert count_markers("[manuscrit : 12] [illisible]", "nl").handwritten == 0


def test_chapter_numbering_words_are_stripped_in_dutch() -> None:
    assert chapter_title("Hoofdstuk 3: Rijen", "nl") == "Rijen"
    assert chapter_title("Les 2 – De eenparige beweging", "nl") == "De eenparige beweging"
    assert chapter_title("Thema 4) Statistiek", "nl") == "Statistiek"
    assert chapter_title("Module IV. Meetkunde", "nl") == "Meetkunde"
    assert chapter_title("Hfst. 5 Functies", "nl") == "Functies"
    assert chapter_title("4) Verhoudingen", "nl") == "Verhoudingen"
    assert chapter_title("Hoofdstuk nr. 3: Rijen", "nl") == "Rijen"
    assert chapter_title("Les nr 2 Rijen", "nl") == "Rijen"
    assert chapter_title("Hoofdstuk n° 3 – Rijen", "nl") == "Rijen"
    # not a numbering: a number glued to a word, a letter before a hyphen, a title that is only words
    assert chapter_title("X-stralen", "nl") == "X-stralen"
    assert chapter_title("Lessenreeks over rijen", "nl") == "Lessenreeks over rijen"
    # the French and English words are not Dutch numbering
    assert chapter_title("Chapitre 3 : Suites", "nl").startswith("Chapitre")
