"""Spec 016 §3.10: the agent reports progress through `LiveProgress` and tells a timeout from other failures."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.domain.errors import CallDiagnostics, ProviderRateLimited, ProviderTimeout, ProviderUnavailable
from app.services.authoring.agent import AuthoringFailed
from app.services.authoring.progress import LiveProgress
from tests.fixtures.fake_completion import data, streamed, text
from tests.unit.test_authoring_agent import CHAPTER_ID, CURRICULUM, PACK, agent, document, page_text, run, run_document
from tests.fixtures.fake_chapters import EXTRA, Chapters


def live(chapters: Chapters) -> LiveProgress:
    return LiveProgress(chapters, "ch1", Settings(openai_api_key="k", _env_file=None), EXTRA)  # type: ignore[arg-type]


async def test_the_output_is_byte_identical_with_and_without_progress() -> None:
    plain, _ = agent([text(PACK), data(CURRICULUM)])
    reported, _ = agent([streamed(text(PACK), 100, 5000), streamed(data(CURRICULUM), 40)])
    without = await run(plain)
    chapters = Chapters()
    with_progress = await reported.run(
        chapter_id=CHAPTER_ID, subject="mathematics", source_text="Le cours collé.", progress=live(chapters)
    )
    assert with_progress.content.pack == without.content.pack
    assert with_progress.content.curriculum.model_dump() == without.content.curriculum.model_dump()
    assert with_progress.content.index == without.content.index
    assert with_progress.usage.input_tokens == without.usage.input_tokens


async def test_the_count_restarts_for_a_repair_attempt() -> None:
    broken = PACK.replace("## 5. Vocabulaire", "## 5. Lexique")
    a, _ = agent([streamed(text(broken), 100, 200), streamed(text(PACK), 300), streamed(data(CURRICULUM), 50)])
    chapters = Chapters()
    await a.run(chapter_id=CHAPTER_ID, subject="mathematics", source_text="x", progress=live(chapters))
    stored = [chars for _, chars in chapters.writes]
    assert stored.count(0) == 1 and stored.index(0) > 0  # only the pack's second attempt restarts it (a stage's start
    assert stored[-1] == 50 and 300 in stored  # is the runner's, through `set_progress`)


async def test_page_batches_only_mark_the_run_alive_and_the_pack_counts() -> None:
    a, _ = agent([streamed(text(page_text(1, 2)), 700), streamed(text(PACK), 900), streamed(data(CURRICULUM), 30)])
    chapters = Chapters()
    await run_document(a, document(2), progress=live(chapters))
    stored = [chars for _, chars in chapters.writes]
    assert 700 not in stored  # the batch's characters are not shown: its progress is the page count
    assert stored[0] is None and 900 in stored and stored[-1] == 30


async def test_a_provider_that_went_quiet_is_a_timeout_and_keeps_its_diagnostics() -> None:
    error = ProviderTimeout()
    error.diagnostics = CallDiagnostics("StreamTimeout", "idle_timeout", None, 61_000, 60_000, 4200)
    a, _ = agent([error])
    with pytest.raises(AuthoringFailed) as raised:
        await run(a)
    assert raised.value.code == "timeout" and raised.value.stage == "pack"
    assert raised.value.diagnostics is error.diagnostics and raised.value.diagnostics.reason == "idle_timeout"  # type: ignore[union-attr]


@pytest.mark.parametrize("error", [ProviderUnavailable(), ProviderRateLimited()])
async def test_any_other_provider_failure_is_provider(error: Exception) -> None:
    a, _ = agent([error])
    with pytest.raises(AuthoringFailed) as raised:
        await run(a)
    assert raised.value.code == "provider"


async def test_a_page_batch_that_times_out_is_a_timeout_at_the_transcription() -> None:
    a, _ = agent([ProviderTimeout()])
    with pytest.raises(AuthoringFailed) as raised:
        await run_document(a, document(1))
    assert (raised.value.code, raised.value.stage) == ("timeout", "transcription")


async def test_repairs_still_count_their_calls() -> None:
    broken = PACK.replace("## 5. Vocabulaire", "## 5. Lexique")
    a, _ = agent([streamed(text(broken), 10), streamed(text(PACK), 20), streamed(data(CURRICULUM), 5)])
    out = await a.run(chapter_id=CHAPTER_ID, subject="mathematics", source_text="x", progress=live(Chapters()))
    assert (out.usage.attempts_pack, out.usage.attempts_curriculum) == (2, 1)
