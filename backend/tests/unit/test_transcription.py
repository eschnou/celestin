from app.domain.transcription import (
    apply_uncertain,
    count_markers,
    handwritten_numbers,
    join_batches,
    split_pages,
    validate_batch,
)

BATCH = "Voici :\n--- page 3 ---\n# Titre\ntexte\n\n--- Page 4 ---\n[manuscrit] $S = 330$\n"


def test_valid_batch_is_normalised():
    text, issues = validate_batch(BATCH, [3, 4])
    assert issues == []
    assert text.startswith("--- page 3 ---\n\n# Titre") and "--- page 4 ---" in text and "Voici" not in text


def test_missing_extra_and_disordered_markers():
    assert "manquant pour la page 4" in validate_batch("--- page 3 ---\nx", [3, 4])[1][0].message
    assert "inattendue 5" in validate_batch("--- page 3 ---\nx\n--- page 5 ---\ny", [3])[1][0].message
    assert "désordre" in validate_batch("--- page 4 ---\nx\n--- page 3 ---\ny", [3, 4])[1][0].message
    assert "désordre" in validate_batch("--- page 3 ---\nx\n--- page 3 ---\ny", [3])[1][0].message


def test_empty_page_needs_page_vide():
    _, issues = validate_batch("--- page 1 ---\n\n--- page 2 ---\nx", [1, 2])
    assert issues[0].where == "page 1"
    text, issues = validate_batch("--- page 1 ---\n[page vide]\n--- page 2 ---\nx", [1, 2])
    assert issues == [] and "[page vide]" in text


def test_join_in_page_order_and_split_back():
    joined = join_batches({3: "--- page 3 ---\n\nc", 1: "--- page 1 ---\n\na\n\n--- page 2 ---\n\nb"})
    assert joined.index("page 1") < joined.index("page 2") < joined.index("page 3")
    assert split_pages(joined) == {1: "--- page 1 ---\n\na", 2: "--- page 2 ---\n\nb", 3: "--- page 3 ---\n\nc"}


def test_counts():
    counts = count_markers("[manuscrit] a [manuscrit: b] [incertain: 3 | 5] [illisible] [illisible]")
    assert (counts.handwritten, counts.uncertain, counts.illegible) == (2, 1, 2)


def test_handwritten_numbers_and_uncertain_rewrite():
    page = "--- page 5 ---\n\n[manuscrit] $33 \\cdot 10 = 330$\ntapé 12\n[manuscrit] bravo\n[manuscrit] [incertain: 3 | 5]"
    candidates = handwritten_numbers(page)
    assert [i for i, _ in candidates] == [2]
    index, line = candidates[0]
    rewritten = apply_uncertain(page, [(index, line, "[manuscrit] $33 \\cdot 10 = $ [incertain: 330 | 350]")])
    assert "[incertain: 330 | 350]" in rewritten
    # A rewrite without a doubt marker, or against a line that changed, is ignored.
    assert apply_uncertain(page, [(index, line, "[manuscrit] 999")]) == page
    assert apply_uncertain(page, [(index, "autre chose", "[incertain: x]")]) == page
