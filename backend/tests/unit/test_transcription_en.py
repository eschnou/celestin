"""Spec 011 R4.3: the transcription's marks per course language. French stays in
`test_transcription.py`, untouched."""

from __future__ import annotations

from app.domain.language import COURSE_LANGUAGES
from app.domain.transcription import (
    MARKERS,
    apply_uncertain,
    count_markers,
    handwritten_numbers,
    validate_batch,
)

EN_BATCH = "--- page 3 ---\nTyped line\n[handwritten: 330]\n--- page 4 ---\n[empty page]"


def test_every_language_has_its_markers() -> None:
    assert set(MARKERS) == set(COURSE_LANGUAGES)
    assert MARKERS["fr"].handwritten == "[manuscrit" and MARKERS["en"].handwritten == "[handwritten"
    assert MARKERS["en"].uncertain == "[uncertain" and MARKERS["en"].illegible == "[illegible]"
    assert MARKERS["en"].empty_page == "[empty page]"
    assert len({MARKERS[language].empty_page for language in COURSE_LANGUAGES}) == 2


def test_an_english_batch_is_validated_with_the_page_markers_only() -> None:
    text, issues = validate_batch(EN_BATCH, [3, 4], "en")
    assert issues == [] and text is not None
    assert text.startswith("--- page 3 ---\n\nTyped line") and "--- page 4 ---\n\n[empty page]" in text


def test_the_issues_are_worded_in_the_courses_language() -> None:
    assert validate_batch("--- page 3 ---\nx", [3, 4], "en")[1][0].message == "missing marker for page 4"
    assert validate_batch("--- page 3 ---\nx\n--- page 5 ---\ny", [3], "en")[1][0].message == "unexpected page 5"
    assert "out of order" in validate_batch("--- page 4 ---\nx\n--- page 3 ---\ny", [3, 4], "en")[1][0].message
    assert validate_batch("--- page 1 ---\n\n--- page 2 ---\nx", [1, 2], "en")[1][0].message == (
        "empty page without “[empty page]”"
    )
    # French is the default and is what it always said.
    assert validate_batch("--- page 3 ---\nx", [3, 4])[1][0].message == "repère manquant pour la page 4"


def test_markers_are_counted_in_their_own_language() -> None:
    text = "[handwritten] a [handwritten: b] [uncertain: 3 | 5] [illegible] [illegible]"
    counts = count_markers(text, "en")
    assert (counts.handwritten, counts.uncertain, counts.illegible) == (2, 1, 2)
    assert count_markers(text) == count_markers("") and count_markers(text, "fr").handwritten == 0
    assert count_markers("[manuscrit] a [incertain: 3 | 5]", "en").handwritten == 0


def test_handwritten_numbers_and_the_uncertain_rewrite_in_english() -> None:
    page = "--- page 1 ---\nTyped 12\n[handwritten] $33 \\cdot 10 = $ 330\n[handwritten] words only"
    candidates = handwritten_numbers(page, "en")
    assert [line for _, line in candidates] == ["[handwritten] $33 \\cdot 10 = $ 330"]
    index, line = candidates[0]
    rewritten = apply_uncertain(page, [(index, line, "[handwritten] $33 \\cdot 10 = $ [uncertain: 330 | 350]")], "en")
    assert "[uncertain: 330 | 350]" in rewritten
    # Only a rewrite that marks a doubt, in this language, is applied.
    assert apply_uncertain(page, [(index, line, "[handwritten] 999")], "en") == page
    assert apply_uncertain(page, [(index, line, "[incertain: x]")], "en") == page
    assert handwritten_numbers(page) == []  # French marks are not looked for in English text
