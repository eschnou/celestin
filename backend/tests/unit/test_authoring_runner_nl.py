"""Spec 017 task 4.4: the runner authors a Dutch course from a document and stores a valid Dutch chapter (the
HTTP end-to-end is `tests/integration/test_dutch_course.py`, once Dutch is offered)."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.db.repositories import Repositories
from app.services.ai_settings import load_ai_config
from app.services.authoring.agent import AuthoringAgent
from app.services.authoring.runner import AuthoringRunner
from tests.fixtures.fake_clients import FixedAiConfig
from tests.fixtures.fake_completion import FakeCompletion, data, text
from tests.unit.test_authoring_agent_nl import PACK, PROMPTS, curriculum_for
from tests.unit.test_authoring_runner import document

READ = text("--- page 1 ---\n" + "De geplakte Nederlandse les over eerstegraadsfuncties. " * 20)


@pytest.fixture
def world(repos: Repositories):
    user = repos.users.create("a@b.be", "Léa", "h")
    course = repos.courses.create(user.id, "Wiskunde", "mathematics", max_courses=30, language="nl")
    return repos, user, course


def runner(repos: Repositories, script) -> tuple[AuthoringRunner, FakeCompletion]:
    fake = FakeCompletion(script)
    settings = Settings(openai_api_key="k", _env_file=None)
    ai = FixedAiConfig(load_ai_config(settings))
    return AuthoringRunner(AuthoringAgent(fake, PROMPTS, settings, ai), repos, settings, ai), fake  # type: ignore[arg-type]


async def test_a_dutch_document_becomes_a_ready_dutch_chapter(world) -> None:
    repos, user, course = world
    r, fake = runner(repos, [READ, text(PACK), data(curriculum_for(PACK))])
    chapter = await r.start_document(user, course, None, document())
    await r.wait_idle()
    owned = repos.chapters.get_owned(user.id, course.id, chapter.id)
    assert owned is not None and owned.course.language == "nl"
    assert owned.chapter.authoring_state == "idle" and owned.chapter.ready
    assert owned.chapter.title == "Eerstegraadsfuncties"
    assert owned.chapter.pack.startswith("# Eerstegraadsfuncties")
    assert fake.calls[0]["instructions"] == [PROMPTS.transcribe("nl")]
    assert fake.calls[1]["instructions"][0] == PROMPTS.authoring_pack("nl")


async def test_a_french_pack_for_a_dutch_course_fails_the_run_after_its_repairs(world) -> None:
    from tests.unit.test_authoring_agent_nl import FRENCH_PACK

    repos, user, course = world
    r, _ = runner(repos, [READ, text(FRENCH_PACK), text(FRENCH_PACK), text(FRENCH_PACK)])
    chapter = await r.start_document(user, course, None, document())
    await r.wait_idle()
    owned = repos.chapters.get_owned(user.id, course.id, chapter.id)
    assert owned is not None and owned.chapter.authoring_state == "failed" and owned.chapter.authoring_error == "unstructured"
