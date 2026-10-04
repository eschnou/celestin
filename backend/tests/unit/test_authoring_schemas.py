from app.domain.curriculum import check_curriculum
from app.services.authoring.schemas import CurriculumDraft, draft_to_data

SECTION = {
    "id": "lecon", "kind": "teach", "title": "L", "goal": "g", "done_when": "d",
    "pack": ["§4.1"], "beats": ["b"], "exercises": [], "count": None,
}


def test_draft_to_data_drops_empty_lists_and_null_count_and_sets_the_id():
    data = draft_to_data({"title": "T", "sections": [SECTION]}, "a" * 32)
    assert data["id"] == "a" * 32
    assert data["sections"][0] == {"id": "lecon", "kind": "teach", "title": "L", "goal": "g", "done_when": "d", "pack": ["§4.1"], "beats": ["b"]}
    assert check_curriculum(data)[1] == []


def test_kind_mismatch_reads_as_such():
    practise = {**SECTION, "kind": "practise", "beats": ["b"], "exercises": [], "count": None}
    _, issues = check_curriculum(draft_to_data({"title": "T", "sections": [practise]}, "a" * 32))
    assert issues[0].message == "une section « practise » doit lister des exercises"


def test_draft_validates_model_output_shape():
    draft = CurriculumDraft.model_validate({"title": "T", "sections": [SECTION]})
    assert draft.sections[0].count is None
