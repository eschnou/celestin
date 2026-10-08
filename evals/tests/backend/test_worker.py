"""The worker's measurement tap, run in the backend's virtualenv against the project's own fake provider:

    uv run --project ../backend --frozen pytest tests/backend -p no:cacheprovider -q
"""

import asyncio

from app.api.schemas.chat import LearnerEntry, ProgressDTO, ToolEntry  # noqa: E402
from app.config import Settings  # noqa: E402
from app.domain.errors import ProviderUnavailable  # noqa: E402
from app.providers.base import Completed, TextDelta  # noqa: E402
from app.services.tutor_service import TutorService  # noqa: E402
from harness import worker  # noqa: E402
from scripts import probe  # noqa: E402
from tests.fixtures.curricula import StubPrompts, lesson_chapter  # noqa: E402
from tests.fixtures.fake_llm import ExplodingLLM, FakeLLM  # noqa: E402

CHAPTER = lesson_chapter("# Course pack — Chapitre 1 : suites\n")
PROMPTS = StubPrompts("prompt <!-- SUBJECT --> <!-- COURSE_PACK --> <!-- CURRICULUM --> <!-- MODE --> <!-- MODE_OPENING -->")


def trial(llm, judge=None, message="bonjour"):
    tutor = TutorService(llm=llm, prompts=PROMPTS, settings=Settings(openai_api_key="k", _env_file=None))
    run = probe.Run("situation", CHAPTER, [], message, ProgressDTO(), judge)
    return asyncio.run(
        worker.run_trial(worker.Tap(tutor), probe, run, set_name="guardrails", mode="parcours", trial=2, timeout_s=5)
    )


def test_a_clean_turn_is_measured():
    usage = {"input_tokens": 100, "output_tokens": 7, "input_tokens_details": {"cached_tokens": 40},
             "output_tokens_details": {"reasoning_tokens": 3}}  # fmt: skip
    record = trial(FakeLLM([[TextDelta("Salut "), TextDelta("!"), Completed(usage=usage)]]))
    assert record["ok"] is True and record["error"] is None and record["end"] == "end"
    assert record["case"] == "guardrails|parcours|situation" and record["trial"] == 2
    assert record["usage"] == {"input": 100, "cached": 40, "output": 7, "reasoning": 3}
    assert record["transcript"] == "Salut !" and record["spoken_chars"] == 7 and record["cards"] == 0
    assert record["ttft_ms"] is not None and record["total_ms"] >= record["ttft_ms"]
    assert record["judged"] is False and record["flags"] == [] and record["flagged"] is False


def test_a_turn_that_says_nothing_is_not_ok():
    record = trial(FakeLLM([[Completed(usage={})]]))
    assert record["ok"] is False and record["error"] is None and record["ttft_ms"] is None


def test_a_provider_that_fails_is_a_result_not_a_crash():
    record = trial(ExplodingLLM(ProviderUnavailable("down")))
    assert record["ok"] is False and (record["error"] or record["error_codes"])


def test_the_probes_mechanical_judges_become_booleans():
    def judge(turn):
        return [f"{probe.ANSWER_LEAK} : 62", f"{probe.FRENCH_LEAK} : « bonjour »"]

    record = trial(FakeLLM([[TextDelta("62"), Completed(usage={})]]), judge=judge)
    assert record["judged"] and record["flagged"] and record["leaked"] and record["french"]
    assert record["out_of_pack"] is False and len(record["flags"]) == 2


def test_a_dutch_courses_language_leak_counts_as_french_in_the_record():
    def judge(turn):
        return [f"{probe.FOREIGN_LEAK} : « bonjour »"]

    record = trial(FakeLLM([[TextDelta("dag"), Completed(usage={})]]), judge=judge)
    assert record["french"] is True and record["leaked"] is False


def test_a_timeout_is_recorded_as_one():
    class Slow:
        model = "slow"

        def stream(self, **_):
            import contextlib

            @contextlib.asynccontextmanager
            async def never():
                await asyncio.sleep(30)
                yield None

            return never()

    tutor = TutorService(llm=Slow(), prompts=PROMPTS, settings=Settings(openai_api_key="k", _env_file=None))
    run = probe.Run("s", CHAPTER, [], "hi", ProgressDTO(), None)
    record = asyncio.run(
        worker.run_trial(worker.Tap(tutor), probe, run, set_name="g", mode="parcours", trial=1, timeout_s=0.05)
    )
    assert record["error"] == "timeout" and record["ok"] is False


def test_the_prior_conversation_is_written_out_for_the_judge():
    prior = [LearnerEntry(kind="learner", text="Pose-moi un exercice."),
             ToolEntry(kind="tool", name="display_board", arguments={"card": {"kind": "exercise"}}, ok=True)]  # fmt: skip
    text = worker.render_prior(prior)
    assert text.startswith("Student: Pose-moi un exercice.") and "[tool display_board" in text


def test_a_suite_is_final_only_when_it_has_finished(tmp_path):
    final = tmp_path / "tutor.json"
    worker.checkpoint(final, {"trials": [1]})
    assert not final.exists() and (tmp_path / "tutor.partial.json").exists()  # an interrupted run leaves no result
    worker.checkpoint(final, {"trials": [1, 2]})
    worker.finish(final, {"trials": [1, 2, 3]})
    assert final.exists() and not (tmp_path / "tutor.partial.json").exists()
    assert worker.json.loads(final.read_text())["trials"] == [1, 2, 3]


def test_a_failure_is_classified_by_what_the_provider_said():
    assert worker.failure_kind("failed to get chunk: code=400, message=tool call validation failed: parameters for tool display_board") == "invalid_tool_call"
    assert worker.failure_kind("Error code: 429 - rate limit reached") == "rate_limited"
    assert worker.failure_kind("Request timed out") == "timeout"
    assert worker.failure_kind("boom") == "provider_error"


def test_a_failed_turn_records_the_providers_reason():
    from app.providers.base import Failed

    llm = FakeLLM([[Failed(code="provider", message="tool call validation failed: /card: expected object, but got string")]])
    record = trial(llm)
    assert record["ok"] is False
    assert record["failure_kind"] == "invalid_tool_call" and "validation failed" in record["failure_detail"]
