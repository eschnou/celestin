import pytest

from app.domain.errors import InvalidSubject
from app.domain.subject import SUBJECT_IDS, SUBJECTS, available_subjects, require_available


def test_four_broad_subjects_with_french_labels():
    """Grouped by how a subject is taught and answered, not by school discipline (spec: more subjects)."""
    assert set(SUBJECTS) == set(SUBJECT_IDS)
    assert list(SUBJECTS) == ["mathematics", "sciences", "languages", "general"]
    assert [SUBJECTS[s].label("fr") for s in SUBJECTS] == ["Mathématiques", "Sciences", "Langues", "Cours généraux"]


def test_every_subject_is_available_in_french_english_and_dutch():
    assert [s.id for s in available_subjects()] == ["mathematics", "sciences", "languages", "general"]
    assert all(s.languages == ("fr", "en", "nl") for s in available_subjects())


def test_require_available_accepts_available_subjects():
    assert require_available("sciences") == "sciences"


@pytest.mark.parametrize("value", ["history", "astrologie", ""])
def test_require_available_refuses_unknown_or_unavailable(value):
    with pytest.raises(InvalidSubject):
        require_available(value)


def test_content_invalid_body_carries_issues():
    from dataclasses import dataclass

    from app.domain.errors import ContentInvalid

    @dataclass
    class Issue:
        where: str
        message: str

    body = ContentInvalid([Issue("§ 4.2", "titre manquant")]).body()
    assert body["code"] == "content_invalid"
    assert body["issues"] == [{"where": "§ 4.2", "message": "titre manquant"}]
