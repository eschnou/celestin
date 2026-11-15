"""Spec 019: what the model reads about skipped sections, in the three course languages.

The overview says the order is a proposal; the state message counts done and skipped apart and
names the skipped sections; a finished chapter with skipped sections says so; a skip answers with
what comes next, as a completion does. Snapshots are `fixtures/render/<name>[_en|_nl].txt`,
generated once, read by a person, and pinned (delete one and rerun to regenerate it).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.progress import Progress
from app.services import curriculum_render as render
from tests.fixtures.curricula import curriculum

SNAPSHOTS = Path(__file__).parent.parent / "fixtures" / "render"
CURRICULA = {"fr": curriculum(), "en": curriculum("valid_en.yaml"), "nl": curriculum("valid_nl.yaml")}
SUFFIX = {"fr": "", "en": "_en", "nl": "_nl"}
LANGUAGES = list(CURRICULA)


def check(name: str, language: str, text: str) -> None:
    path = SNAPSHOTS / f"{name}{SUFFIX[language]}.txt"
    if not path.exists():
        path.write_text(text, encoding="utf-8")
    assert text == path.read_text(encoding="utf-8")


SKIPPED_BETWEEN = Progress(done=frozenset({"intro"}), skipped=frozenset({"exos"}))
SKIPPED_ACTIVE = Progress(active="exos", skipped=frozenset({"intro"}))
FINISHED_SKIPPED = Progress(done=frozenset({"intro", "bilan"}), skipped=frozenset({"exos"}))

# What each language says, so a snapshot cannot pin a wrong text unread.
WORDS = {
    "fr": {
        "count": "1 section(s) faite(s) et 1 passée(s) sur 3.",
        "named": "Sections passées : « 2. ",
        "next": 'start_section("bilan")',
        "finished": "toutes les sections sont faites ou passées",
        "lead": "Sections dans l'ordre que tu proposes.",
        "skip_head": "Section passée.",
        "still": "Section toujours en cours : « 2. ",
    },
    "en": {
        "count": "1 section(s) done and 1 skipped out of 3.",
        "named": "Skipped sections: “2. ",
        "next": 'start_section("bilan")',
        "finished": "every section is done or skipped",
        "lead": "Sections in the order you propose.",
        "skip_head": "Section skipped.",
        "still": "Section still in progress: “2. ",
    },
    "nl": {
        "count": "1 van de 3 sectie(s) afgerond en 1 overgeslagen.",
        "named": "Overgeslagen secties: “2. ",
        "next": 'start_section("bilan")',
        "finished": "alle secties zijn afgerond of overgeslagen",
        "lead": "Secties in de volgorde die jij voorstelt.",
        "skip_head": "Sectie overgeslagen.",
        "still": "Sectie nog bezig: “2. ",
    },
}


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_parcours_overview_says_the_order_is_a_proposal_and_names_no_tool(language: str) -> None:
    """The lead sits in the cached prefix: a neutral description. The tools' contract is the
    mode layer's and the declarations' to state, not restated here."""
    text = render.overview(CURRICULA[language], "parcours", language)  # type: ignore[arg-type]
    assert WORDS[language]["lead"] in text
    assert not any(tool in text for tool in ("start_section", "complete_section", "skip_section"))
    discussion = render.overview(CURRICULA[language], "discussion", language)  # type: ignore[arg-type]
    assert "skip_section" not in discussion


@pytest.mark.parametrize("language", LANGUAGES)
def test_between_sections_with_one_skipped(language: str) -> None:
    w = WORDS[language]
    text = render.state_message(CURRICULA[language], SKIPPED_BETWEEN, None, "parcours", language)  # type: ignore[arg-type]
    assert w["count"] in text and w["named"] in text and w["next"] in text
    check("state_skipped_between", language, text)


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_section_active_after_a_skipped_one(language: str) -> None:
    text = render.state_message(CURRICULA[language], SKIPPED_ACTIVE, None, "parcours", language)  # type: ignore[arg-type]
    assert 'start_section("exos")' in text and WORDS[language]["named"].replace("2. ", "1. ") in text
    check("state_skipped_active", language, text)


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_chapter_finished_with_a_skipped_section(language: str) -> None:
    w = WORDS[language]
    text = render.state_message(CURRICULA[language], FINISHED_SKIPPED, None, "parcours", language)  # type: ignore[arg-type]
    assert w["finished"] in text and w["named"] in text
    assert "start_section" not in text
    check("state_finished_skipped", language, text)


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_discussion_counts_the_skipped_sections_and_names_no_tool(language: str) -> None:
    w = WORDS[language]
    between = render.state_message(CURRICULA[language], SKIPPED_BETWEEN, None, "discussion", language)  # type: ignore[arg-type]
    finished = render.state_message(CURRICULA[language], FINISHED_SKIPPED, None, "discussion", language)  # type: ignore[arg-type]
    for text in (between, finished):
        assert w["count"] in text or "2" in text
        assert w["named"] in text
        assert "start_section" not in text and "skip_section" not in text
    assert w["finished"] in finished
    check("state_discussion_skipped", language, f"{between}\n---\n{finished}")


@pytest.mark.parametrize("language", LANGUAGES)
def test_without_skipped_sections_the_state_message_is_what_it_was(language: str) -> None:
    """Nothing skipped: the texts pinned before spec 019 (`state_*.txt`) are unchanged."""
    cur = CURRICULA[language]
    for progress, name in (
        (Progress(), "state_empty"),
        (Progress(done=frozenset({"intro"})), "state_between"),
        (Progress(done=frozenset({"intro", "exos", "bilan"})), "state_complete"),
    ):
        check(name, language, render.state_message(cur, progress, None, "parcours", language))  # type: ignore[arg-type]


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_skip_answers_with_what_comes_next(language: str) -> None:
    """From sections, never from a progress: a stored skip replays from what it recorded."""
    w, cur = WORDS[language], CURRICULA[language]
    lang = language  # type: ignore[assignment]
    next_one = render.skipped(None, cur.get("bilan"), lang)  # type: ignore[arg-type]
    assert next_one.startswith(w["skip_head"]) and "id: bilan" in next_one.replace("id : ", "id: ")
    still = render.skipped(cur.get("exos"), None, lang)  # type: ignore[arg-type]
    assert still.startswith(w["skip_head"]) and still[len(w["skip_head"]) + 1 :].startswith(w["still"])
    last = render.skipped(None, None, lang)  # type: ignore[arg-type]
    assert w["finished"] in last and w["named"] not in last  # the state message names them, every turn
    check("skip_outputs", language, "\n".join((next_one, still, last)))


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_completion_that_ends_the_chapter_is_what_it_always_was(language: str) -> None:
    """A completion records only where the page turned (spec 019): « chapter finished » is
    said as before spec 019, skipped sections or not; the state message names them."""
    assert render.completion(None, None, language).endswith(  # type: ignore[arg-type]
        {"fr": "Chapitre terminé.", "en": "Chapter finished.", "nl": "Hoofdstuk afgerond."}[language]
    )


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_finished_sentence_is_one_text_in_the_state_message_and_the_skip(language: str) -> None:
    w = render.WORDS[language]  # type: ignore[index]
    parcours = render.state_message(CURRICULA[language], FINISHED_SKIPPED, None, "parcours", language)  # type: ignore[arg-type]
    discussion = render.state_message(CURRICULA[language], FINISHED_SKIPPED, None, "discussion", language)  # type: ignore[arg-type]
    assert f"{w.finished_all} {w.finished_skipped_offer}" in parcours
    assert discussion.endswith(w.finished_all) and w.finished_skipped_offer not in discussion
    assert render.skipped(None, None, language).endswith(w.finished_all)  # type: ignore[arg-type]
