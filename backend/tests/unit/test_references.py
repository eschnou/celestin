from app.domain.curriculum import Curriculum, check_curriculum
from app.domain.pack import PackIndex
from app.domain.references import reference_issues

INDEX = PackIndex(title="T", sections=frozenset({"§1", "§4", "§4.2", "§6", "§6.1"}), exercises=frozenset({"6.1.1", "6.1.2"}))


def curriculum(pack: list[str], exercises: list[str]) -> Curriculum:
    return Curriculum.model_validate(
        {
            "id": "c1",
            "title": "T",
            "sections": [
                {"id": "lecon", "kind": "teach", "title": "L", "goal": "g", "beats": ["b"], "done_when": "d", "pack": pack},
                {"id": "exos", "kind": "practise", "title": "E", "goal": "g", "exercises": exercises, "count": 1, "done_when": "d"},
            ],
        }
    )


def test_valid_references_with_free_text():
    assert reference_issues(curriculum(["§4.2 propriété 1", "§4"], ["6.1.1 (sans la somme)", "6.1.2"]), INDEX) == []


def test_unknown_section_is_named():
    issues = reference_issues(curriculum(["§4.3 définition"], ["6.1.1"]), INDEX)
    assert [(i.where, i.message) for i in issues] == [("section « lecon »", "la section §4.3 n'existe pas dans le contenu")]


def test_unknown_exercise_is_named():
    issues = reference_issues(curriculum([], ["6.2.1"]), INDEX)
    assert issues[0].where == "section « exos »" and "6.2.1" in issues[0].message


def test_exercise_pool_may_name_a_pack_section():
    assert reference_issues(curriculum([], ["§4.2 : le tableau d'applications", "§6.1 : un au choix"]), INDEX) == []
    issues = reference_issues(curriculum([], ["§5 : définitions"]), INDEX)
    assert issues[0].message == "la section §5 n'existe pas dans le contenu"


def test_entries_without_an_id_are_refused():
    issues = reference_issues(curriculum(["définition"], ["l'exercice du cours"]), INDEX)
    assert len(issues) == 2
    assert all("doit commencer" in i.message for i in issues)


def test_check_curriculum_name_the_section_in_french():
    data = {
        "id": "c1",
        "title": "T",
        "sections": [{"id": "lecon", "kind": "teach", "title": "L", "goal": "g", "done_when": "d"}],
    }
    _, issues = check_curriculum(data)
    assert issues[0].where == "section « lecon »"
    assert issues[0].message == "une section « teach » doit avoir des beats"
    assert check_curriculum({"id": "c1", "title": "T", "sections": data["sections"] * 1})[1] != []


def test_check_curriculum_empty_for_valid_data():
    curriculum_, issues = check_curriculum(curriculum([], ["6.1.1"]).model_dump())
    assert curriculum_ is not None and issues == []
