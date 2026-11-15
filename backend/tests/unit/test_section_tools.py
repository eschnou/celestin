from __future__ import annotations

import json

import pytest

from app.domain.errors import ToolValidationError
from app.domain.progress import Progress
from app.api.schemas.chat import ToolEntry
from app.services.tools import registry
from app.services.tools.context import TurnContext
from app.services.tools.section import SectionCompleted, SectionSkipped, SectionStarted
from tests.fixtures.curricula import ctx_for


def start(section_id: str, progress: Progress | None = None, ctx=None):
    ctx = ctx or ctx_for(progress)
    return registry.execute("start_section", json.dumps({"section_id": section_id}), ctx)


def complete(section_id: str, progress: Progress | None = None, summary: str = "Fait.", ctx=None):
    ctx = ctx or ctx_for(progress)
    return registry.execute(
        "complete_section", json.dumps({"section_id": section_id, "summary": summary}), ctx
    )


def test_start_available_section_and_apply_the_transition() -> None:
    ctx = ctx_for()
    out = start("intro", ctx=ctx)
    assert isinstance(out, SectionStarted)
    assert (out.section.index, out.review) == (1, False)
    assert out.marker == "section commencée · 1. Introduction"
    assert "Objectif : Comprendre" in out.output
    assert ctx.progress.active == "intro"


def test_start_done_section_is_a_review_and_moves_nothing() -> None:
    ctx = ctx_for(Progress(done=frozenset({"intro"}), active="exos"))
    out = start("intro", ctx=ctx)
    assert out.review is True
    assert out.marker == "révision · 1. Introduction"
    assert "Révision" in out.output
    assert ctx.progress.active == "exos"


def test_start_any_section_in_any_order() -> None:
    """Spec 019 D1: a later section opens without the ones before it."""
    ctx = ctx_for()
    out = start("bilan", ctx=ctx)
    assert (out.section.id, out.review) == ("bilan", False)
    assert ctx.progress == Progress(active="bilan")


def test_start_another_section_parks_the_active_one() -> None:
    """Spec 019 D4: the section left is neither done nor skipped."""
    ctx = ctx_for(Progress(done=frozenset({"intro"}), active="exos"))
    start("bilan", ctx=ctx)
    assert ctx.progress == Progress(done=frozenset({"intro"}), active="bilan")


def test_start_a_skipped_section_un_skips_it() -> None:
    ctx = ctx_for(Progress(skipped=frozenset({"intro", "exos"})))
    out = start("exos", ctx=ctx)
    assert out.review is False and out.marker == "section commencée · 2. Exercices"
    assert ctx.progress == Progress(active="exos", skipped=frozenset({"intro"}))


def skip(section_id: str, progress: Progress | None = None, ctx=None):
    ctx = ctx or ctx_for(progress)
    return registry.execute("skip_section", json.dumps({"section_id": section_id}), ctx)


def test_start_unknown_section() -> None:
    with pytest.raises(ToolValidationError, match="n'existe pas"):
        start("nope")


def test_complete_active_section_names_the_next_and_moves_it_to_done() -> None:
    ctx = ctx_for(Progress(active="intro"))
    out = complete("intro", summary="Définition vue.", ctx=ctx)
    assert isinstance(out, SectionCompleted)
    assert out.next.id == "exos"
    assert out.summary == "Définition vue."
    assert out.marker == "section terminée · 1. Introduction"
    assert "id : exos" in out.output
    assert ctx.progress == Progress(done=frozenset({"intro"}), active=None)


def test_complete_last_section_ends_the_chapter() -> None:
    out = complete("bilan", Progress(done=frozenset({"intro", "exos"}), active="bilan"))
    assert out.next is None
    assert "Chapitre terminé" in out.output


def test_complete_requires_the_active_section() -> None:
    with pytest.raises(ToolValidationError, match="Aucune section"):
        complete("intro")
    with pytest.raises(ToolValidationError, match="id : intro"):
        complete("exos", Progress(active="intro"))


@pytest.mark.parametrize("summary", ["", "x" * 301])
def test_summary_bounds(summary: str) -> None:
    with pytest.raises(ToolValidationError, match="summary"):
        complete("intro", Progress(active="intro"), summary=summary)


def test_extra_arguments_are_rejected() -> None:
    with pytest.raises(ToolValidationError):
        registry.execute("start_section", json.dumps({"section_id": "intro", "x": 1}), ctx_for())


def test_output_of_carries_the_brief() -> None:
    out = registry.output_of(start("intro"))
    assert out["ok"] is True and "Déroulé" in out["result"]


def test_commit_persists_through_save() -> None:
    """004 R6.2: the transition reaches the store in the same call."""
    from app.domain.progress import Progress
    from app.services.tools import registry
    from tests.fixtures.curricula import curriculum

    saved: list[Progress] = []
    ctx = TurnContext.from_progress(curriculum(), [], None, save=saved.append)
    registry.execute("start_section", '{"section_id":"intro"}', ctx)
    assert saved == [Progress(active="intro")] and ctx.progress.active == "intro"


def test_failing_save_is_a_tool_error_and_changes_nothing() -> None:
    from app.domain.errors import ToolValidationError
    from app.services.tools import registry
    from tests.fixtures.curricula import curriculum

    def boom(_: object) -> None:
        raise RuntimeError("disk full")

    ctx = TurnContext.from_progress(curriculum(), [], None, save=boom)
    with pytest.raises(ToolValidationError, match="enregistrer"):
        registry.execute("start_section", '{"section_id":"intro"}', ctx)
    assert ctx.progress.active is None


def test_review_commits_nothing() -> None:
    from app.services.tools import registry
    from tests.fixtures.curricula import curriculum

    saved: list[object] = []
    ctx = TurnContext.from_progress(curriculum(), ["intro"], None, save=saved.append)
    registry.execute("start_section", '{"section_id":"intro"}', ctx)
    assert saved == []


# --- spec 019: skip_section ------------------------------------------------------------


def test_skip_a_section_not_started_turns_to_the_next_one() -> None:
    ctx = ctx_for()
    out = skip("intro", ctx=ctx)
    assert isinstance(out, SectionSkipped)
    assert out.section.id == "intro" and out.next.id == "exos"
    assert out.marker == "section passée · 1. Introduction"
    assert out.output == "Section passée. Prochaine section : « 2. Exercices » (exercices), id : exos."
    assert ctx.progress == Progress(skipped=frozenset({"intro"}))


def test_skip_the_active_section_clears_it() -> None:
    ctx = ctx_for(Progress(active="exos"))
    out = skip("exos", ctx=ctx)
    assert ctx.progress == Progress(skipped=frozenset({"exos"}))
    assert out.next.id == "intro"  # the first neither done, skipped nor active


def test_skip_another_section_leaves_the_active_one_and_turns_no_page() -> None:
    ctx = ctx_for(Progress(active="intro"))
    out = skip("exos", ctx=ctx)
    assert ctx.progress == Progress(active="intro", skipped=frozenset({"exos"}))
    assert out.next is None
    assert out.output == "Section passée. Section toujours en cours : « 1. Introduction » (cours), id : intro."


def test_skip_is_idempotent_and_writes_nothing_the_second_time() -> None:
    from tests.fixtures.curricula import curriculum

    saved: list[Progress] = []
    ctx = TurnContext.from_progress(curriculum(), [], None, save=saved.append)
    first = skip("intro", ctx=ctx)
    second = skip("intro", ctx=ctx)
    assert saved == [Progress(skipped=frozenset({"intro"}))]
    assert (second.output, second.next, second.marker) == (first.output, first.next, first.marker)
    assert ctx.progress == Progress(skipped=frozenset({"intro"}))


def test_skip_the_last_open_section_finishes_the_chapter() -> None:
    """The skipped sections are named by the state message on every turn, not here: a stored
    skip replays from what it recorded, and the skipped set may have changed since."""
    ctx = ctx_for(Progress(done=frozenset({"intro", "exos"}), active="bilan"))
    out = skip("bilan", ctx=ctx)
    assert (out.next, out.active) == (None, None)
    assert out.output == "Section passée. Chapitre terminé : toutes les sections sont faites ou passées."


def _stored(outcome) -> ToolEntry:
    """A live call as a later turn reads it: its event, recorded, stored, parsed back."""
    from pydantic import TypeAdapter

    from app.api.schemas.chat import Entry, stored_form
    from app.services.conversations import entries_from_events
    from app.services.tool_events import event_of

    (entry,) = entries_from_events([event_of(outcome)])
    stored = TypeAdapter(Entry).validate_python(json.loads(json.dumps(stored_form(entry))))
    assert isinstance(stored, ToolEntry)
    return stored


@pytest.mark.parametrize(
    ("before", "section_id", "later"),
    [
        # The student skips the intro, then changes their mind and starts it in the same séance.
        (Progress(active="intro"), "intro", Progress(active="intro")),
        # Skipping another section while one is worked, which is completed afterwards.
        (Progress(active="intro"), "exos", Progress(done=frozenset({"intro"}), skipped=frozenset({"exos"}))),
        # The skip that finished the chapter, then a skipped section taken up again.
        (Progress(done=frozenset({"intro", "exos"}), active="bilan"), "bilan", Progress(done=frozenset({"intro", "exos"}), active="bilan")),
    ],
    ids=["un-skipped", "active-then-done", "finished-then-reopened"],
)
def test_a_stored_skip_replays_what_it_answered_whatever_the_progress_became(
    before: Progress, section_id: str, later: Progress
) -> None:
    """Spec 019: the replay is built from what the call recorded, not from the progress now,
    so it never contradicts what the student heard (and the cached history does not move)."""
    live = skip(section_id, ctx=ctx_for(before))
    stored = _stored(live)
    assert stored.recorded("next_section_id") and stored.recorded("active_section_id")
    assert registry.replay_output(stored, ctx_for(later)) == {"ok": True, "result": live.output}


def test_a_stored_completion_replays_what_it_answered_whatever_the_progress_became() -> None:
    live = complete("intro", Progress(active="intro"))
    stored = _stored(live)
    assert stored.next_section_id == "exos"
    later = ctx_for(Progress(done=frozenset({"intro"}), active="exos"))  # the next section, started since
    assert registry.replay_output(stored, later) == {"ok": True, "result": live.output}
    assert "Prochaine section : « 2. Exercices »" in live.output


def test_a_call_stored_before_spec_019_is_replayed_from_the_progress_now() -> None:
    """No recorded field (an entry of spec 018): what the replay always said."""
    bare = ToolEntry(kind="tool", name="complete_section", arguments={"section_id": "intro"})
    working = ctx_for(Progress(done=frozenset({"intro"}), active="exos"))
    assert registry.replay_output(bare, working)["result"] == (
        "Section terminée. Section toujours en cours : « 2. Exercices » (exercices), id : exos."
    )
    gone = bare.model_copy(update={"next_section_id": "removed"})  # a section the curriculum no longer has
    assert registry.replay_output(gone, working) == registry.replay_output(bare, working)


@pytest.mark.parametrize(
    ("language", "refusal"),
    [
        ("fr", "La section « 1. Introduction » est déjà faite : elle ne peut pas être passée."),
        ("en", "Section “1. Introduction” is already done: it cannot be skipped."),
        ("nl", "Sectie “1. Introduction” is al afgerond: ze kan niet overgeslagen worden."),
    ],
)
def test_skip_a_done_section_is_refused_in_the_courses_language(language: str, refusal: str) -> None:
    from tests.fixtures.curricula import curriculum

    saved: list[Progress] = []
    ctx = TurnContext.from_progress(curriculum(), ["intro"], None, save=saved.append, language=language)  # type: ignore[arg-type]
    with pytest.raises(ToolValidationError) as exc:
        registry.execute("skip_section", '{"section_id":"intro"}', ctx)
    assert exc.value.message == refusal
    assert saved == [] and ctx.progress == Progress(done=frozenset({"intro"}))


def test_skip_an_unknown_section_is_refused_with_the_list() -> None:
    with pytest.raises(ToolValidationError, match="n'existe pas"):
        skip("nope")


def test_skip_takes_only_a_section_id() -> None:
    with pytest.raises(ToolValidationError):
        registry.execute("skip_section", json.dumps({"section_id": "intro", "why": "vu"}), ctx_for())
    with pytest.raises(ToolValidationError):
        registry.execute("skip_section", "{}", ctx_for())


def test_a_failing_save_on_skip_is_a_tool_error_and_changes_nothing() -> None:
    from tests.fixtures.curricula import curriculum

    def boom(_: object) -> None:
        raise RuntimeError("disk full")

    ctx = TurnContext.from_progress(curriculum(), [], "intro", save=boom)
    with pytest.raises(ToolValidationError, match="enregistrer"):
        registry.execute("skip_section", '{"section_id":"intro"}', ctx)
    assert ctx.progress == Progress(active="intro")


def test_from_progress_reads_the_stored_skipped() -> None:
    from tests.fixtures.curricula import curriculum

    ctx = TurnContext.from_progress(curriculum(), ["intro"], "exos", skipped=["bilan", "intro", "ghost"])
    assert ctx.progress == Progress(done=frozenset({"intro"}), active="exos", skipped=frozenset({"bilan"}))
