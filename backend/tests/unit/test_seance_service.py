"""Stored séances (spec 018): the split rule, what the model reads, the rollover, the
notebook and the rows' lifetime, against a real database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.api.schemas.seance import NotebookResponse
from app.api.schemas.chat import LearnerEntry, ToolEntry, TutorEntry
from app.config import Settings
from app.db.repositories import Repositories
from app.domain.chapter import LessonChapter
from app.domain.errors import ConversationBusy, EmptyTurnExpected, SeanceBusy, SeanceStarted
from app.domain.progress import Progress
from app.services.discussion import DiscussionService
from app.services.seance import SeanceService, earlier_cards, split
from tests.fixtures.curricula import curriculum

CARD_A = {"kind": "explanation", "title": "Définition", "blocks": [{"type": "text", "text": "Une suite…"}]}
CARD_B = {"kind": "check_question", "question": "Quel est u₂ ?", "options": [{"id": "a", "text": "1"}, {"id": "b", "text": "2"}],
          "correct_option_id": "a", "feedback": "Oui."}
CARD_C = {"kind": "recap", "acquired": ["La définition"], "next": "Les exercices"}


def _chapter(repos: Repositories, user_id: str, version: int = 1) -> LessonChapter:
    course = repos.courses.create(user_id, "Maths", "mathematics", max_courses=30)
    row = repos.chapters.create(course.id, "texte", max_chapters=40)
    cur = curriculum()
    return LessonChapter(id=row.id, subject="mathematics", title=cur.title, pack="# Pack", curriculum=cur, version=version)


def _at(chapter: LessonChapter, version: int) -> LessonChapter:
    return LessonChapter(
        id=chapter.id, subject=chapter.subject, title=chapter.title, pack=chapter.pack,
        curriculum=chapter.curriculum, version=version,
    )


def _student(repos: Repositories, email: str = "a@b.be") -> str:
    return repos.users.create(email, "Léa", "hash").id


def _service(repos: Repositories, settings: Settings, **overrides) -> SeanceService:
    return SeanceService(repos, settings.model_copy(update=overrides) if overrides else settings)


def start(section: str, review: bool = False) -> ToolEntry:
    return ToolEntry(kind="tool", name="start_section", arguments={"section_id": section}, review=review)


def done(section: str) -> ToolEntry:
    return ToolEntry(kind="tool", name="complete_section", arguments={"section_id": section})


def board(card: dict) -> ToolEntry:
    return ToolEntry(kind="tool", name="display_board", arguments={"card": card})


def say(text: str) -> TutorEntry:
    return TutorEntry(kind="tutor", text=text)


def ask(text: str) -> LearnerEntry:
    return LearnerEntry(kind="learner", text=text)


def _rows(repos: Repositories, user: str, chapter: LessonChapter):
    return repos.conversations.seances(user, chapter.id, chapter.version)


def _turn(service: SeanceService, user: str, chapter: LessonChapter, message: str | None, produced: list, progress=Progress()):
    turn, _ = service.open_turn(user, chapter, progress, message)
    return turn, service.store(turn, [*turn.added, *produced])


# --- the split rule (D3), every branch ------------------------------------------------


def test_a_fresh_row_adopts_the_first_section_it_starts(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings)
    _turn(service, user, chapter, None, [say("Bonjour !")])
    live = service.live(user, chapter)
    assert live is not None and live.section_id is None and live.entry_count == 1

    _turn(service, user, chapter, "on commence", [start("intro"), board(CARD_A)])
    (row,) = _rows(repos, user, chapter)
    assert row.id == live.id and row.section_id == "intro" and row.live
    assert [e["kind"] for e in row.entries] == ["tutor", "learner", "tool", "tool"]
    assert row.card_count == 1


def test_the_first_stored_turn_creates_the_row(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings)
    assert service.live(user, chapter) is None
    _turn(service, user, chapter, None, [say("Salut."), start("intro")])
    (row,) = _rows(repos, user, chapter)
    assert row.live and row.section_id == "intro" and row.entry_count == 2


def test_starting_the_same_section_again_appends(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings)
    _turn(service, user, chapter, None, [start("intro"), board(CARD_A)])
    _turn(service, user, chapter, "je reviens", [start("intro"), say("On reprend.")])
    (row,) = _rows(repos, user, chapter)
    assert row.live and row.section_id == "intro" and row.entry_count == 5


def test_another_section_closes_the_row_done_when_it_was_completed(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings)
    _turn(service, user, chapter, None, [start("intro"), board(CARD_A)])
    _turn(service, user, chapter, "j'ai compris", [done("intro"), board(CARD_C)])  # the recap stays with intro
    _turn(service, user, chapter, "suivant", [say("Allons-y."), start("exos"), board(CARD_B)])

    first, second = _rows(repos, user, chapter)
    assert (first.section_id, first.state, first.closed_reason) == ("intro", "closed", "done")
    # The learner's message and the text said before the start stay with the section they were said in.
    assert [e.get("text") for e in first.entries[-2:]] == ["suivant", "Allons-y."]
    assert first.card_count == 2
    assert (second.section_id, second.live) == ("exos", True)
    assert [e["name"] for e in second.entries] == ["start_section", "display_board"]
    assert second.card_count == 1


def test_another_section_closes_the_row_left_when_it_was_not_completed(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings)
    _turn(service, user, chapter, None, [start("exos"), board(CARD_A)])
    _turn(service, user, chapter, "je veux revoir l'intro", [start("intro", review=True)])
    first, second = _rows(repos, user, chapter)
    assert (first.section_id, first.closed_reason) == ("exos", "left")
    assert first.entries[-1] == {"kind": "learner", "text": "je veux revoir l'intro"}
    assert second.section_id == "intro" and second.entries[0]["review"] is True


def test_completion_and_the_next_start_in_one_turn(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings)
    _turn(service, user, chapter, None, [start("intro")])
    _turn(service, user, chapter, "fini", [done("intro"), say("Bravo."), start("exos"), say("Exercice 1.")])
    first, second = _rows(repos, user, chapter)
    assert first.closed_reason == "done" and [e.get("text") for e in first.entries[-2:]] == [None, "Bravo."]
    assert second.live and second.entries[-1]["text"] == "Exercice 1."


def test_a_refused_start_does_not_split(repos: Repositories, settings: Settings) -> None:
    """A refused call never reaches the entries of a text turn; a reported one marked
    not ok must not cut the séance either."""
    refused = ToolEntry(kind="tool", name="start_section", arguments={"section_id": "bilan"}, ok=False, error="non")
    segments = split(None, [start("intro"), refused, say("Pas encore.")])
    assert len(segments) == 1 and segments[0].section_id == "intro"


def test_the_split_of_a_turn_without_a_row(repos: Repositories, settings: Settings) -> None:
    segments = split(None, [say("Salut"), start("intro"), done("intro"), start("exos")])
    assert [(s.section_id, s.closed_reason, len(s.entries)) for s in segments] == [
        ("intro", "done", 3),
        ("exos", None, 1),
    ]


# --- what the model reads (D4) and the opening turn ------------------------------------


def test_the_model_reads_the_live_row_and_the_message_only(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings)
    _turn(service, user, chapter, None, [start("intro"), say("ancienne section")])
    _turn(service, user, chapter, "fini", [done("intro"), start("exos"), say("Exercice 1.")])

    turn, read = service.open_turn(user, chapter, Progress(done=frozenset({"intro"}), active="exos"), "je cherche")
    assert read == [start("exos"), say("Exercice 1."), ask("je cherche")]
    assert turn.added == [ask("je cherche")]


def test_an_opening_turn_is_refused_once_the_seance_holds_something(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings)
    opening, read = service.open_turn(user, chapter, Progress(), None)
    assert read == [] and opening.live_id is None
    service.store(opening, [say("Bonjour.")])
    with pytest.raises(SeanceStarted) as caught:
        service.open_turn(user, chapter, Progress(), None)
    # The wire keeps the discussion's code; the words are the séance's.
    assert isinstance(caught.value, EmptyTurnExpected)
    assert caught.value.code == "empty_conversation_expected" and caught.value.status == 422
    assert "séance" in caught.value.message("fr")


def test_a_second_tab_storing_first_is_busy(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings)
    service.store(service.open_turn(user, chapter, Progress(), None)[0], [say("Bonjour.")])
    one, _ = service.open_turn(user, chapter, Progress(), "un")
    two, _ = service.open_turn(user, chapter, Progress(), "deux")
    service.store(one, [*one.added, say("ok")])
    with pytest.raises(SeanceBusy) as caught:
        service.store(two, [*two.added, say("ok")])
    assert isinstance(caught.value, ConversationBusy) and caught.value.code == "conversation_busy"
    assert _rows(repos, user, chapter)[0].entry_count == 3


def test_two_first_turns_at_once_cannot_make_two_live_rows(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings)
    one, _ = service.open_turn(user, chapter, Progress(), None)
    two, _ = service.open_turn(user, chapter, Progress(), None)
    service.store(one, [say("Bonjour.")])
    with pytest.raises(SeanceBusy):
        service.store(two, [say("Bonjour.")])
    assert len(_rows(repos, user, chapter)) == 1


def test_a_turn_that_produced_nothing_stores_nothing(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings)
    assert service.store(service.open_turn(user, chapter, Progress(), None)[0], []) == []
    assert _rows(repos, user, chapter) == []


# --- the cap (D10) ---------------------------------------------------------------------


def test_a_full_seance_rolls_over_with_a_synthetic_start(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings, discussion_max_entries=3)
    _turn(service, user, chapter, None, [start("intro"), board(CARD_A), say("Tu suis ?")])
    full = service.live(user, chapter)
    assert full is not None and full.live and full.entry_count == 3  # not closed when it filled up

    _, read = service.open_turn(user, chapter, Progress(active="intro"), "oui")
    first, second = _rows(repos, user, chapter)
    assert (first.id, first.closed_reason) == (full.id, "capped")
    assert second.live and second.section_id == "intro"
    assert second.entries == [{"kind": "tool", "name": "start_section", "arguments": {"section_id": "intro"},
                               "ok": True, "error": None, "review": False}]
    # The brief is in front of the model again.
    assert read == [start("intro"), ask("oui")]


def test_the_character_cap_rolls_over_too(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings, discussion_max_chars=1000)
    _turn(service, user, chapter, None, [start("intro"), say("x" * 1200)])
    service.open_turn(user, chapter, Progress(active="intro"), "oui")
    assert [r.closed_reason for r in _rows(repos, user, chapter)] == ["capped", None]


# --- the reprise note's cards (D5) -----------------------------------------------------


def test_earlier_cards_come_from_closed_non_review_seances_of_the_section(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings)
    _turn(service, user, chapter, None, [start("intro"), board(CARD_A), board(CARD_B)])
    assert earlier_cards(repos, user, chapter.id, chapter.version, "intro") == []  # live: restored, not noted

    _turn(service, user, chapter, "autre chose", [start("exos")])  # intro closed `left`
    assert earlier_cards(repos, user, chapter.id, chapter.version, "intro") == [CARD_A, CARD_B]
    assert earlier_cards(repos, user, chapter.id, chapter.version, "exos") == []
    # Another content version holds nothing.
    assert earlier_cards(repos, user, chapter.id, chapter.version + 1, "intro") == []


def test_a_review_seance_gives_no_cards_to_the_note(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings)
    _turn(service, user, chapter, None, [start("intro", review=True), board(CARD_A)])
    _turn(service, user, chapter, "suite", [start("exos")])
    assert earlier_cards(repos, user, chapter.id, chapter.version, "intro") == []


def test_earlier_cards_read_the_transcripts_once_per_set_of_rows(repos: Repositories, settings: Settings, monkeypatch) -> None:
    """Closed rows are final, so the note's cards are parsed once, not on every turn that
    replays the brief: a light query of ids, then a cache keyed by them."""
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings)
    _turn(service, user, chapter, None, [start("intro"), board(CARD_A)])
    _turn(service, user, chapter, "ailleurs", [start("exos")])  # intro closed `left`
    reads: list[list[str]] = []
    real = repos.conversations.seances_by_id

    def spy(user_id: str, ids: list[str]):
        reads.append(list(ids))
        return real(user_id, ids)

    monkeypatch.setattr(repos.conversations, "seances_by_id", spy)
    for _ in range(3):
        assert earlier_cards(repos, user, chapter.id, chapter.version, "intro") == [CARD_A]
    assert len(reads) == 1
    # A row without a card is not even read; a new closed row with one is a new set.
    _turn(service, user, chapter, "retour", [start("intro")])  # exos closed `left`, no card
    _turn(service, user, chapter, "encore", [board(CARD_B)])
    _turn(service, user, chapter, "exos", [start("exos")])  # intro's second row closed
    assert earlier_cards(repos, user, chapter.id, chapter.version, "intro") == [CARD_A, CARD_B]
    assert earlier_cards(repos, user, chapter.id, chapter.version, "exos") == []
    assert len(reads) == 2 and len(reads[1]) == 2
    # What the caller does with the list never reaches the cache.
    earlier_cards(repos, user, chapter.id, chapter.version, "intro").clear()
    assert earlier_cards(repos, user, chapter.id, chapter.version, "intro") == [CARD_A, CARD_B]


def test_the_card_cache_is_bounded() -> None:
    from app.services.seance import _CardCache

    cache = _CardCache(max_entries=2)
    cache.put(("a",), ({"k": 1},))
    cache.put(("b",), ())
    assert cache.get(("a",)) == ({"k": 1},)  # now the most recent
    cache.put(("c",), ())
    assert cache.get(("b",)) is None and cache.get(("a",)) is not None and cache.get(("c",)) == ()


# --- a reported turn (D7, D10) ------------------------------------------------------------


def test_a_reported_turn_is_checked_against_the_chapter(repos: Repositories, settings: Settings) -> None:
    from app.domain.errors import SeanceFull, SeanceReportInvalid

    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings, seance_max_rows=2)
    with pytest.raises(SeanceReportInvalid):
        service.store_reported(user, chapter, Progress(), [ask("ok"), start("zz-nope")])
    with pytest.raises(SeanceReportInvalid):
        service.store_reported(user, chapter, Progress(), [ToolEntry(kind="tool", name="reveal", arguments={})])
    assert _rows(repos, user, chapter) == []
    # A start without its review gets it from the progress; one with it keeps it.
    bare = ToolEntry(kind="tool", name="start_section", arguments={"section_id": "intro"})
    service.store_reported(user, chapter, Progress(done=frozenset({"intro"})), [bare])
    assert _rows(repos, user, chapter)[0].entries[0]["review"] is True
    service.store_reported(user, chapter, Progress(), [start("exos")])  # intro closed: two rows
    with pytest.raises(SeanceFull):
        service.store_reported(user, chapter, Progress(), [ask("encore")])
    # The cap counts rows, not turns: a model turn is not refused.
    _turn(service, user, chapter, "toujours là", [say("Oui.")])
    assert len(_rows(repos, user, chapter)) == 2


# --- the notebook (D8) and the chapter view ---------------------------------------------


def test_the_notebook_groups_by_section_in_path_order_oldest_first(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings)
    _turn(service, user, chapter, None, [say("Bonjour."), start("exos"), board(CARD_B)])  # exos first
    _turn(service, user, chapter, "revoir l'intro", [start("intro", review=True), board(CARD_A), say("Voilà.")])
    _turn(service, user, chapter, "retour", [start("exos"), say("On reprend."), board(CARD_C)])

    sections = service.notebook(user, chapter)
    assert [s.section_id for s in sections] == ["intro", "exos"]  # the path's order, not the séances'
    # What the route sends: the service's dataclasses read into the response DTO in one step.
    wire = NotebookResponse.model_validate({"sections": sections}).model_dump()["sections"]
    intro, exos = (section["items"] for section in wire)
    # A message said before a start stays with the séance it was said in: « retour » with intro's, « revoir
    # l'intro » with exos' first one.
    assert intro == [
        {"kind": "card", "card": CARD_A},
        {"kind": "tutor", "text": "Voilà."},
        {"kind": "learner", "text": "retour"},
    ]
    assert exos == [
        {"kind": "tutor", "text": "Bonjour."},
        {"kind": "card", "card": CARD_B},
        {"kind": "learner", "text": "revoir l'intro"},
        {"kind": "tutor", "text": "On reprend."},
        {"kind": "card", "card": CARD_C},
    ]


def test_the_notebook_reads_the_current_content_version_only(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings)
    _turn(service, user, chapter, None, [start("intro"), board(CARD_A)])
    edited = _at(chapter, chapter.version + 1)
    assert service.notebook(user, edited) == []
    assert service.card_counts(user, edited) == {}
    # The old live séance is closed lazily, and the next turn starts a fresh one.
    assert service.live(user, edited) is None
    assert repos.conversations.seances(user, chapter.id, chapter.version)[0].closed_reason == "content_changed"
    _turn(service, user, edited, None, [start("intro")])
    assert [s.section_id for s in service.notebook(user, edited)] == []  # a start alone is no item
    assert service.card_counts(user, edited) == {"intro": 0}


def test_card_counts_sum_a_sections_seances(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings)
    _turn(service, user, chapter, None, [say("Bonjour.")])  # no section: no key
    _turn(service, user, chapter, "go", [start("intro"), board(CARD_A), board(CARD_B)])
    _turn(service, user, chapter, "exos", [start("exos")])
    _turn(service, user, chapter, "intro encore", [start("intro"), board(CARD_C)])
    assert service.card_counts(user, chapter) == {"intro": 3, "exos": 0}


# --- lifetime and coexistence ------------------------------------------------------------


def test_reset_deletes_the_seances_and_leaves_the_discussions(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings)
    _turn(service, user, chapter, None, [start("intro")])
    _turn(service, user, chapter, "suite", [start("exos")])
    discussion = DiscussionService(repos, settings).start(user, chapter)
    repos.progress.save(user, chapter.id, Progress(active="exos"))

    assert repos.progress.reset(user, chapter.id) == 2
    assert _rows(repos, user, chapter) == [] and repos.progress.load(user, chapter.id) is None
    assert repos.conversations.live(user, chapter.id, mode="discussion") == discussion


def test_a_discussion_and_a_seance_are_live_together_and_never_see_each_other(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    seances = _service(repos, settings)
    discussions = DiscussionService(repos, settings)
    conversation = discussions.start(user, chapter)
    _turn(seances, user, chapter, None, [start("intro")])

    seance = seances.live(user, chapter)
    assert seance is not None and repos.conversations.live(user, chapter.id, mode="parcours") == seance
    assert discussions.live(user, chapter) == conversation
    assert repos.conversations.get_owned(user, chapter.id, seance.id, mode="discussion") is None
    assert repos.conversations.get_owned(user, chapter.id, conversation.id, mode="parcours") is None
    # Starting a new discussion replaces the discussion only.
    discussions.start(user, chapter)
    assert seances.live(user, chapter) == seance


def test_the_quota_counts_discussions_only(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    seances = _service(repos, settings)
    for section in ("intro", "exos", "bilan"):
        _turn(seances, user, chapter, "go", [start(section)])
    since = datetime.now(UTC) - timedelta(days=1)
    assert repos.conversations.started_since(user, since, mode="discussion") == 0
    assert repos.conversations.started_since(user, since, mode="parcours") == 3
    DiscussionService(repos, settings.model_copy(update={"discussion_conversations_per_day": 1})).start(user, chapter)


def test_seances_are_per_student(repos: Repositories, settings: Settings) -> None:
    a, b = _student(repos), _student(repos, "b@b.be")
    chapter = _chapter(repos, a)
    service = _service(repos, settings)
    _turn(service, a, chapter, None, [start("intro"), board(CARD_A)])
    assert service.live(b, chapter) is None and service.notebook(b, chapter) == []
    assert earlier_cards(repos, b, chapter.id, chapter.version, "intro") == []
