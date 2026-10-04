from __future__ import annotations

from pathlib import Path

import pytest

from app.config import REPO_ROOT
from app.domain.curriculum import parse_curriculum
from app.domain.errors import CurriculumInvalid

CURRICULA = Path(__file__).parent.parent / "fixtures" / "curricula"


def load(name: str):
    return parse_curriculum((CURRICULA / name).read_text(encoding="utf-8"), name)


def test_real_curriculum_loads_with_thirteen_sections() -> None:
    real = REPO_ROOT / "courses" / "chapitre_1" / "curriculum.yaml"
    cur = parse_curriculum(real.read_text(encoding="utf-8"), real)
    assert cur.id == "suites"
    assert len(cur.sections) == 13
    assert cur.sections[0].kind == "teach"
    assert cur.sections[-1].id == "test-blanc"


def test_fixture_loads() -> None:
    cur = load("valid.yaml")
    assert [s.id for s in cur.sections] == ["intro", "exos", "bilan"]
    assert [s.index for s in cur.sections] == [1, 2, 3]
    assert cur.get("exos").label == "2. Exercices"
    assert cur.get("nope") is None
    assert cur.get("bilan").kind == "synthesis"


@pytest.mark.parametrize(
    ("name", "section", "phrase"),
    [
        ("duplicate_id.yaml", "intro", "double"),
        ("teach_no_beats.yaml", "intro", "beats"),
        ("practise_no_count.yaml", "exos", "count"),
        ("unknown_key.yaml", "intro", "colour"),
    ],
)
def test_invalid_files_name_the_section(name: str, section: str, phrase: str) -> None:
    with pytest.raises(CurriculumInvalid) as exc:
        load(name)
    assert name in exc.value.path
    assert phrase in exc.value.detail
    assert section in exc.value.detail


def test_unparseable_yaml_is_invalid() -> None:
    with pytest.raises(CurriculumInvalid, match="YAML"):
        parse_curriculum("sections: [unclosed", "x.yaml")


def test_non_mapping_document_is_invalid() -> None:
    with pytest.raises(CurriculumInvalid):
        parse_curriculum("- just\n- a list\n", "x.yaml")
