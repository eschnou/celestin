"""The four subjects (mathematics, sciences, languages, general): what each offers, and that its template and
prompt hold together. The content of a chapter comes from the student's material; a subject only fixes how it is
taught, written and checked, so these tests look at the contract (the headings a pack must follow, the writing
conventions a prompt states), not at pedagogy."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.domain.pack import index_pack
from app.domain.subject import offered
from app.services.prompts import PromptLibrary
from app.services.tools.board import _SCRIPT

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
LIBRARY = PromptLibrary(PROMPTS)


def skeleton(template) -> str:  # noqa: ANN001
    """The smallest pack that follows a template: its headings, one notion, one exercise."""
    lines = ["# A chapter", ""]
    for number, text in template.headings:
        lines += [f"## {number}. {text}", ""]
        if number == 4:
            lines += ["### 4.1 A notion", "", "What the course says.", ""]
        if number == template.exercises_section:
            lines += ["### 6.1 A theme", "", "#### 6.1.1", "**A statement.**", "", "**Answer:** a.", ""]
    return "\n".join(lines)


@pytest.mark.parametrize(("subject", "language"), offered())
def test_a_template_accepts_a_pack_built_from_its_own_headings(subject: str, language: str) -> None:
    template = LIBRARY.template(subject, language)  # type: ignore[arg-type]
    index, issues = index_pack(skeleton(template), template)
    assert issues == [] and index is not None
    assert "6.1.1" in index.exercises and "§4.1" in index.sections


@pytest.mark.parametrize("language", ["fr", "en"])
def test_the_four_templates_are_distinct_documents(language: str) -> None:
    """A pack written for one subject is not accepted as another's: the headings tell them apart."""
    templates = {s: LIBRARY.template(s, language) for s in ("mathematics", "sciences", "languages", "general")}  # type: ignore[arg-type]
    for written_for, template in templates.items():
        pack = skeleton(template)
        for other, candidate in templates.items():
            if other == written_for:
                continue
            _, issues = index_pack(pack, candidate)
            assert issues, (written_for, other)


@pytest.mark.parametrize("language", ["fr", "en"])
@pytest.mark.parametrize("subject", ["mathematics", "sciences", "languages", "general"])
def test_the_exercise_sections_share_the_template_contract(subject: str, language: str) -> None:
    template = LIBRARY.template(subject, language)  # type: ignore[arg-type]
    assert [n for n, _ in template.headings] == [1, 2, 3, 4, 5, 6, 7]
    assert template.exercises_section == 6


def read(subject: str, language: str) -> str:
    return (PROMPTS / "subjects" / f"{subject}.{language}.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("language", ["fr", "en"])
def test_the_language_prompt_spells_out_how_a_foreign_text_is_written(language: str) -> None:
    text = read("languages", language)
    assert "`____`" in text  # a blank to fill in is written the same way everywhere
    assert "LaTeX" in text  # and the prompt says there is none in a language chapter
    # The student writes in the language studied; the tutor does not translate for them and does not write
    # their text.
    assert ("ne traduis pas" if language == "fr" else "do not translate") in text
    assert ("ne rédiges jamais" if language == "fr" else "never write it for") in text


@pytest.mark.parametrize("language", ["fr", "en"])
def test_the_general_prompt_stays_inside_the_course(language: str) -> None:
    text = read("general", language)
    assert ("n'ajoutes aucun fait" if language == "fr" else "add no fact") in text
    # A sensitive subject is taught as the course presents it, without the tutor's own opinion.
    assert ("sans donner le tien" if language == "fr" else "without giving your own") in text


@pytest.mark.parametrize("language", ["fr", "en"])
def test_the_sciences_prompt_covers_quantities_reactions_and_processes(language: str) -> None:
    text = read("sciences", language)
    for needle in (r"\mathrm{H_2O}", r"\mathrm{2\,H_2 + O_2 \rightarrow 2\,H_2O}", r"\vec{v}"):
        assert needle in text
    assert len(re.findall(r"^## ", text, re.MULTILINE)) >= 5


def test_a_blank_to_fill_in_is_not_taken_for_a_bare_subscript() -> None:
    """The board refuses `u_n` written bare; the blank of a language exercise must pass."""
    for text in ("Complète : il ____ (manger) une pomme.", "Tu mang____ ; l'____ est là.", "He ____ (to go) home."):
        assert not _SCRIPT.search(text), text


@pytest.mark.parametrize(("subject", "language"), offered())
def test_every_subject_renders_a_tutor_prompt_with_its_voice_block_only_in_a_call(subject: str, language: str) -> None:
    """The cached text prefix carries the subject prompt without its voice block; a Realtime session carries it."""
    from app.services import prompt_service

    template = LIBRARY.template(subject, language)  # type: ignore[arg-type]

    def render(voice: bool) -> str:
        return prompt_service.render_system_text(
            LIBRARY.tutor(language),  # type: ignore[arg-type]
            LIBRARY.subject(subject, language),  # type: ignore[arg-type]
            skeleton(template),
            "OVERVIEW",
            LIBRARY.mode("parcours", language),  # type: ignore[arg-type]
            LIBRARY.mode_opening("parcours", language),  # type: ignore[arg-type]
            voice=voice,
        )

    text, call = render(False), render(True)
    voice_title = {"fr": "à voix haute", "en": "out loud", "nl": "hardop"}[language]
    subject_text = LIBRARY.subject(subject, language)  # type: ignore[arg-type]
    assert subject_text.split("<!-- VOICE -->")[0].strip() in text
    assert subject_text.split("<!-- VOICE -->")[1].split("<!-- /VOICE -->")[0].strip() not in text
    assert subject_text.split("<!-- VOICE -->")[1].split("<!-- /VOICE -->")[0].strip() in call
    for marker in ("<!-- SUBJECT -->", "<!-- COURSE_PACK -->", "<!-- CURRICULUM -->", "<!-- MODE -->", "<!-- MODE_OPENING -->"):
        assert marker not in text and marker not in call, marker
    assert voice_title in call.lower()
