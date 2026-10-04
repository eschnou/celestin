from pathlib import Path

import pytest

from app.domain.errors import PromptInvalid
from app.domain.pack import chapter_title, index_pack, parse_template

BACKEND = Path(__file__).resolve().parents[2]
TEMPLATES = BACKEND / "prompts" / "templates"
PACKS = Path(__file__).resolve().parents[1] / "fixtures" / "packs"
REPO = BACKEND.parent


def template(subject: str):
    path = TEMPLATES / f"{subject}.pack.fr.md"
    return parse_template(path.read_text(encoding="utf-8"), path)


def maths() -> str:
    return (PACKS / "maths_valid.md").read_text(encoding="utf-8")


def test_templates_parse_with_seven_sections():
    for subject in ("mathematics", "sciences"):
        tpl = template(subject)
        assert tpl.subject == subject
        assert [n for n, _ in tpl.headings] == [1, 2, 3, 4, 5, 6, 7]
        assert tpl.exercises_section == 6
        assert tpl.headings[-1] == (7, "Points à vérifier")
    assert template("sciences").headings[2] == (3, "Notations, grandeurs et unités")


def test_maths_headings_are_unchanged_by_the_chart_guidance():
    """008 D3: charts live in the comments of § 3 and § 4, never in a new required
    heading, so every stored pack keeps validating."""
    assert [text for _, text in template("mathematics").headings] == [
        "Objectif du chapitre",
        "Prérequis",
        "Conventions de notation",
        "Notions, dans l'ordre d'enseignement",
        "Vocabulaire",
        "Exercices types",
        "Points à vérifier",
    ]
    assert "Représentation graphique" in template("mathematics").text


@pytest.mark.parametrize(
    "text, detail",
    [
        ("# pas d'en-tête\n## 1. A\n", "en-tête"),
        ("---\nsubject: astrologie\nexercises_section: 1\n---\n## 1. A\n", "matière"),
        ("---\nsubject: sciences\nexercises_section: 1\n---\nrien\n", "aucun titre"),
        ("---\nsubject: sciences\nexercises_section: 9\n---\n## 1. A\n", "exercises_section"),
    ],
)
def test_broken_templates_are_refused(text, detail):
    with pytest.raises(PromptInvalid, match=detail):
        parse_template(text, "t.md")


def test_valid_maths_pack_is_indexed():
    index, issues = index_pack(maths(), template("mathematics"))
    assert issues == []
    assert index is not None
    assert index.title == "Les fonctions du premier degré"
    assert {"§1", "§4", "§4.1", "§4.2", "§6.1", "§7"} <= index.sections
    assert index.exercises == {"6.1.1", "6.1.2"}
    assert "9.9.9" not in index.exercises  # inside a fenced block


def test_points_to_verify_are_counted_in_the_last_section_only():
    index, _ = index_pack(maths(), template("mathematics"))
    assert index is not None and index.to_verify == 0  # « Aucun. »
    text = maths().replace("## 7. Points à vérifier\n\nAucun.", "## 7. Points à vérifier\n\n1. doute\n2. autre\n\n```\n3. dans un bloc\n```")
    index, issues = index_pack(text, template("mathematics"))
    assert issues == [] and index is not None and index.to_verify == 2


def test_valid_physics_pack_is_indexed():
    text = (PACKS / "sciences_valid.md").read_text(encoding="utf-8")
    index, issues = index_pack(text, template("sciences"))
    assert issues == [] and index is not None
    assert index.exercises == {"6.1.1"}


def test_maths_pack_is_not_a_physics_pack():
    index, issues = index_pack(maths(), template("sciences"))
    assert index is None
    assert any(i.where == "§ 3" for i in issues)


@pytest.mark.parametrize(
    "mutate, where, fragment",
    [
        (lambda t: t.replace("# Les fonctions du premier degré\n", "", 1), "titre", "commencer par un titre"),
        (lambda t: t.replace("## 5. Vocabulaire", "## 5. Lexique"), "§ 5", "manquante"),
        (lambda t: t.replace("## 2. Prérequis\n\n- Repère orthonormé.\n", "", 1), "§ 2", "manquante"),
        (lambda t: t.replace("### 4.2 Pente", "### 3.2 Pente"), "§ 3.2", "sous « ## 3. »"),
        (lambda t: t.replace("### 4.2 Pente", "### 4.1 Pente"), "§ 4.1", "double"),
        (lambda t: t.replace("#### 6.1.2 Lecture", "#### 6.1.1 Lecture"), "exercice 6.1.1", "double"),
        (lambda t: t.replace("#### 6.1.2 Lecture", "#### 6.2.2 Lecture"), "exercice 6.2.2", "sous « ### 6.2 »"),
        (lambda t: t.replace("La pente vaut $a$.", "#### 4.2.1\nLa pente vaut $a$."), "exercice 4.2.1", "uniquement sous"),
        (lambda t: t.replace("#### 6.1.1\n", "").replace("#### 6.1.2 Lecture\n", ""), "§ 6", "au moins un exercice"),
        (lambda t: t + "\n# Un second titre\n", "titre", "un seul titre"),
        (lambda t: t.replace("## 7. Points à vérifier", "## Annexe\n\n## 7. Points à vérifier"), "document", "inattendue"),
    ],
)
def test_broken_packs_name_the_problem(mutate, where, fragment):
    index, issues = index_pack(mutate(maths()), template("mathematics"))
    assert index is None
    assert any(i.where == where and fragment in i.message for i in issues), issues


def test_sections_out_of_order():
    text = maths()
    voc = "## 5. Vocabulaire\n\n**Mots du cours, à employer** : pente, ordonnée à l'origine.\n\n"
    swapped = text.replace(voc, "").replace("## 2. Prérequis", voc + "## 2. Prérequis")
    index, issues = index_pack(swapped, template("mathematics"))
    assert index is None
    assert any("ordre" in i.message for i in issues)


def test_titles_compare_ignoring_case_and_spacing():
    text = maths().replace("## 5. Vocabulaire", "##  5.  vocabulaire")
    index, issues = index_pack(text, template("mathematics"))
    assert issues == [] and index is not None


def test_over_length_and_issue_cap():
    index, issues = index_pack(maths(), template("mathematics"), max_chars=100)
    assert index is None
    assert issues[0].where == "document"
    many = maths() + "".join(f"\n## {i}. Extra\n" for i in range(10, 60))
    _, capped = index_pack(many, template("mathematics"))
    assert len(capped) == 20


def test_chapter_one_follows_the_maths_template_and_its_curriculum_references_resolve():
    from app.domain.curriculum import parse_curriculum
    from app.domain.references import reference_issues

    directory = REPO / "courses" / "chapitre_1"
    index, issues = index_pack((directory / "pack.md").read_text(encoding="utf-8"), template("mathematics"))
    assert issues == []
    assert index is not None and index.title == "Les suites numériques"
    assert "6.3.5" in index.exercises
    curriculum = parse_curriculum((directory / "curriculum.yaml").read_text(encoding="utf-8"))
    assert reference_issues(curriculum, index) == []


@pytest.mark.parametrize(
    "heading, expected",
    [
        ("Chapitre 1 : nombres réels et suites", "Nombres réels et suites"),
        ("CHAP. II - Les forces", "Les forces"),
        ("Chapitre 2 Les vecteurs", "Les vecteurs"),
        ("4) Les fonctions", "Les fonctions"),
        ("1. Le MRU", "Le MRU"),
        ("Thème 2 — Énergie", "Énergie"),
        ("Les suites numériques", "Les suites numériques"),  # nothing to strip
        ("1000 façons de compter", "1000 façons de compter"),  # a number that is the title
        ("3 lois de Newton", "3 lois de Newton"),  # no separator: not a chapter number
        ("Chapitre 3", "Chapitre 3"),  # only a number: keep it rather than empty
    ],
)
def test_chapter_title_drops_the_material_numbering(heading: str, expected: str) -> None:
    assert chapter_title(heading) == expected


def test_index_uses_the_title_without_its_numbering() -> None:
    pack = maths().replace("# Les fonctions", "# Chapitre 1 : les fonctions", 1)
    index, issues = index_pack(pack, template("mathematics"), 60_000)
    assert not issues and index is not None and index.title == "Les fonctions du premier degré"
