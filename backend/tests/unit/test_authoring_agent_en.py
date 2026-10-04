"""Spec 011 R4, tasks 7.5/7.7: the authoring agent on an English course, against the scripted
provider. The French runs are `test_authoring_agent.py`, untouched."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.fake_clients import FixedAiConfig
from app.services.ai_settings import load_ai_config
from app.config import Settings
from app.domain.errors import ProviderOutputTruncated
from app.services.authoring.agent import (
    AuthoringAgent,
    AuthoringFailed,
    VerifyDraft,
    _repair_message,  # type: ignore[attr-defined]
    wrap_source,
)
from app.services.authoring.schemas import CurriculumDraft
from app.services.authoring.words import AGENT_WORDS
from app.services.documents import Document, PageImage
from app.services.prompts import PromptLibrary
from tests.fixtures.fake_completion import FakeCompletion, data, text

BACKEND = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
PROMPTS = PromptLibrary(BACKEND / "prompts")
PACK = (FIXTURES / "packs" / "maths_valid_en.md").read_text(encoding="utf-8")
FRENCH_PACK = (FIXTURES / "packs" / "maths_valid.md").read_text(encoding="utf-8")
CHAPTER_ID = "a" * 32

CURRICULUM = {
    "title": "Chapter 2: Linear functions",
    "sections": [
        {"id": "definition", "kind": "teach", "title": "Definition", "goal": "g", "done_when": "d",
         "pack": ["§4.1"], "beats": ["State the definition.", "Check question."], "exercises": [], "count": None},
        {"id": "graphs", "kind": "practise", "title": "Graphs", "goal": "g", "done_when": "d",
         "pack": [], "beats": [], "exercises": [], "count": 1},
    ],
}


def agent(script, **overrides) -> tuple[AuthoringAgent, FakeCompletion]:
    fake = FakeCompletion(script)
    settings = Settings(openai_api_key="k", _env_file=None, **overrides)
    return AuthoringAgent(fake, PROMPTS, settings, FixedAiConfig(load_ai_config(settings))), fake  # type: ignore[arg-type]


def curriculum_for(pack: str) -> dict:
    """The curriculum above, with the first exercise ids of `pack`."""
    from app.domain.pack import index_pack

    index, _ = index_pack(pack, PROMPTS.template("mathematics", "en"))
    assert index is not None
    exercises = sorted(index.exercises)
    graphs = {**CURRICULUM["sections"][1], "exercises": exercises[:2], "count": 1}
    return {**CURRICULUM, "sections": [CURRICULUM["sections"][0], graphs]}


async def run(a: AuthoringAgent, source: str = "The pasted course."):
    return await a.run(chapter_id=CHAPTER_ID, subject="mathematics", language="en", source_text=source)


async def test_an_english_text_becomes_an_english_chapter() -> None:
    a, fake = agent([text(PACK), data(curriculum_for(PACK))])
    out = await run(a)
    assert out.content.pack == PACK and out.content.title == "Linear functions"
    assert out.content.curriculum.title == "Linear functions"  # « Chapter 2: » is dropped in English
    assert [c["schema"] for c in fake.calls] == [None, CurriculumDraft]


async def test_the_instructions_are_the_english_files() -> None:
    a, fake = agent([text(PACK), data(curriculum_for(PACK))])
    await run(a)
    assert fake.calls[0]["instructions"] == [
        PROMPTS.authoring_pack("en"),
        PROMPTS.template("mathematics", "en").text,
        PROMPTS.subject("mathematics", "en"),
    ]
    assert fake.calls[1]["instructions"] == [PROMPTS.authoring_curriculum("en"), PROMPTS.subject("mathematics", "en")]
    assert PROMPTS.authoring_pack("en") != PROMPTS.authoring_pack("fr")


async def test_the_material_is_framed_in_english() -> None:
    a, fake = agent([text(PACK), data(curriculum_for(PACK))])
    await run(a, "Special material 4242")
    pack_input = fake.calls[0]["input"][0]["content"]
    assert pack_input.startswith("Here is the course material pasted by the student, between tags.")
    assert "<materiel>\nSpecial material 4242" in pack_input
    assert fake.calls[1]["input"][0]["content"].startswith("Chapter content, between tags:\n<chapitre>")
    assert wrap_source("x").startswith("Voici le matériel de cours")  # French by default


async def test_a_french_pack_is_sent_back_with_the_mismatch_in_english() -> None:
    a, fake = agent([text(FRENCH_PACK), text(PACK), data(curriculum_for(PACK))])
    out = await run(a)
    assert out.usage.attempts_pack == 2
    repair = fake.calls[1]["input"][-1]["content"]
    assert repair.startswith("The document does not follow the rules:\n- document: ")
    assert "the document follows the French template, but this course is in English" in repair
    assert repair.endswith("Return the complete, corrected document.")
    assert "ne respecte pas" not in repair


async def test_an_english_curriculum_repair_is_in_english() -> None:
    broken = {**curriculum_for(PACK), "sections": [{**CURRICULUM["sections"][0], "beats": []}]}
    a, fake = agent([text(PACK), data(broken), data(curriculum_for(PACK))])
    out = await run(a)
    assert out.usage.attempts_curriculum == 2
    repair = fake.calls[2]["input"][-1]["content"]
    assert repair.startswith("The path does not follow the rules:\n")
    assert "- section « definition »: a “teach” section must have beats" in repair
    assert repair.endswith("Return the complete, corrected path.")
    assert "Renvoie" not in repair


async def test_an_unreadable_curriculum_answer_is_reported_in_english() -> None:
    from app.domain.errors import ProviderOutputInvalid

    a, fake = agent([text(PACK), ProviderOutputInvalid("bad"), data(curriculum_for(PACK))])
    await run(a)
    assert "unreadable JSON answer" in fake.calls[2]["input"][-1]["content"]


def test_the_repair_request_is_the_old_french_one_by_default() -> None:
    from app.domain.pack import ContentIssue

    issues = [ContentIssue("§ 4.2", "titre manquant", "pack.title_missing")]
    assert _repair_message("Le document", issues) == (
        "Le document ne respecte pas les règles :\n- § 4.2 : titre manquant\nRenvoie le document complet, corrigé."
    )
    assert _repair_message(AGENT_WORDS["en"].the_document, issues, "en") == (
        "The document does not follow the rules:\n"
        "- § 4.2: the document must start with a title, “# Chapter title”\n"
        "Return the complete, corrected document."
    )


# --- a document ----------------------------------------------------------------------


def document(pages: int, hint_on: int | None = None) -> Document:
    return Document(
        kind="images",
        pages=[
            PageImage(n, b"\xff\xd8jpeg-%d" % n, "text layer " * 30 if n == hint_on else None)
            for n in range(1, pages + 1)
        ],
        bytes_in=100,
    )


def page_text(*numbers: int, body: str = "typed text") -> str:
    return "\n".join(f"--- page {n} ---\n{body} {n}" for n in numbers)


async def run_document(a, doc, **kwargs):
    return await a.run(chapter_id=CHAPTER_ID, subject="mathematics", language="en", document=doc, **kwargs)


async def test_an_english_document_is_transcribed_with_the_english_prompt() -> None:
    a, fake = agent([text(page_text(1, 2)), text(page_text(3)), text(PACK), data(curriculum_for(PACK))])
    await run_document(a, document(3, hint_on=2))
    assert all(c["instructions"] == [PROMPTS.transcribe("en")] for c in fake.calls[:2])
    parts = fake.calls[0]["input"][0]["content"]
    assert parts[0]["text"] == "Pages 1 to 2, in order."
    assert parts[1]["text"] == "Page 1:" and parts[3]["text"].startswith("Page 2:\nPDF text layer, an unreliable hint:")


async def test_the_page_markers_are_validated_with_english_wording() -> None:
    a, fake = agent([text("--- page 1 ---\nonly"), text(page_text(1, 2)), text(PACK), data(curriculum_for(PACK))])
    out = await run_document(a, document(2))
    assert out.usage.attempts_transcription == 2

    a, _ = agent([text("nothing"), text("still nothing")])
    with pytest.raises(AuthoringFailed) as exc:
        await run_document(a, document(2))
    assert exc.value.code == "transcription_failed"


async def test_a_truncated_batch_is_read_page_by_page_in_english() -> None:
    a, fake = agent(
        [ProviderOutputTruncated("max"), text(page_text(1)), text(page_text(2)), text(PACK), data(curriculum_for(PACK))]
    )
    out = await run_document(a, document(2))
    assert out.usage.attempts_transcription == 3
    assert fake.calls[1]["input"][0]["content"][0]["text"] == "Pages 1 to 1, in order."


async def test_the_handwriting_check_uses_the_english_marks() -> None:
    transcribed = "--- page 1 ---\n# Exercise\n[handwritten] $33 \\cdot 10 = 330$\n[handwritten] well done"
    verdict = {"items": [{"n": 1, "sure": False, "line": "[handwritten] $33 \\cdot 10 = $ [uncertain: 330 | 350]"}]}
    a, fake = agent(
        [text(transcribed), data(verdict), text(PACK), data(curriculum_for(PACK))],
        transcription_verify_handwriting=True,
    )
    stored: list[str] = []

    async def on_transcribed(text_, counts):
        stored.append(text_)
        assert (counts.handwritten, counts.uncertain) == (2, 1)

    await run_document(a, document(1), on_transcribed=on_transcribed)
    assert "[uncertain: 330 | 350]" in stored[0] and "well done" in stored[0]
    check = fake.calls[1]
    assert check["schema"] is VerifyDraft and check["instructions"] == [PROMPTS.verify("en")]
    assert check["input"][0]["content"][0]["text"].startswith("Page 1. Lines to re-read:\n<lignes>\n1. [handwritten] $33")


async def test_french_marks_in_an_english_transcription_are_not_counted() -> None:
    a, _ = agent([text("--- page 1 ---\n[manuscrit] 12 [incertain: 1 | 7]"), text(PACK), data(curriculum_for(PACK))])
    counts: list = []

    async def on_transcribed(text_, c):
        counts.append(c)

    await run_document(a, document(1), on_transcribed=on_transcribed)
    assert (counts[0].handwritten, counts[0].uncertain) == (0, 0)


# --- physics ---------------------------------------------------------------------------


async def test_an_english_physics_chapter_is_authored_from_its_own_template() -> None:
    from app.domain.curriculum import parse_curriculum

    directory = FIXTURES / "chapters" / "uniform_motion_en"
    pack = (directory / "pack.md").read_text(encoding="utf-8")
    parsed = parse_curriculum((directory / "curriculum.yaml").read_text(encoding="utf-8"), directory, "en")
    draft = {k: v for k, v in parsed.model_dump(mode="json").items() if k != "id"}
    a, fake = agent([text(pack), data(draft)])
    out = await a.run(chapter_id=CHAPTER_ID, subject="sciences", language="en", source_text="The pasted lesson.")
    assert out.content.title == parsed.title
    assert fake.calls[0]["instructions"][1] == PROMPTS.template("sciences", "en").text
    assert fake.calls[0]["instructions"][2] == PROMPTS.subject("sciences", "en")
