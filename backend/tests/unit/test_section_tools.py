from __future__ import annotations

import json

import pytest

from app.domain.errors import ToolValidationError
from app.domain.progress import Progress
from app.services.tools import registry
from app.services.tools.context import TurnContext
from app.services.tools.section import SectionCompleted, SectionStarted
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


def test_start_locked_section_names_the_startable_one() -> None:
    with pytest.raises(ToolValidationError) as exc:
        start("bilan")
    assert "3. Synthèse" in exc.value.message
    assert "id : intro" in exc.value.message


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
