import re
from pathlib import Path

from app.domain.mode import MODES
from app.domain.subject import available_subjects
from app.services.prompt_service import VOICE_END, VOICE_START

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"


def _neutral(text: str, where: str) -> None:
    lowered = text.lower()
    for word in ("mathématique", "physique", "suite arithmétique", "u₁", "5e secondaire"):
        assert word not in lowered, f"{where}: {word}"
    assert not re.search(r"\belle\b", lowered), where


def test_tutor_prompt_is_subject_neutral_and_gender_neutral():
    text = (PROMPTS / "tutor.fr.md").read_text(encoding="utf-8")
    markers = (
        "<!-- SUBJECT -->",
        "<!-- COURSE_PACK -->",
        "<!-- CURRICULUM -->",
        "<!-- MODE -->",
        "<!-- MODE_OPENING -->",
    )
    for marker in markers:
        assert text.count(marker) == 1
    positions = [text.index(marker) for marker in markers]
    assert positions == sorted(positions)
    _neutral(text, "tutor.fr.md")
    assert "Points à vérifier" in text and "Points à faire valider" not in text


def test_every_mode_has_both_layers_neutral_and_marker_free():
    """The mode files are the tutor prompt's continuation: same neutrality rules,
    and no marker of their own (the substitution is a single pass, 007 §3.2)."""
    for mode in MODES:
        for name in (f"{mode}.fr.md", f"{mode}.opening.fr.md"):
            text = (PROMPTS / "modes" / name).read_text(encoding="utf-8")
            assert text.strip(), name
            _neutral(text, name)
            for marker in ("<!-- SUBJECT -->", "<!-- COURSE_PACK -->", "<!-- CURRICULUM -->", "<!-- MODE -->"):
                assert marker not in text, f"{name}: {marker}"
    parcours = (PROMPTS / "modes" / "parcours.fr.md").read_text(encoding="utf-8")
    assert "**Leçon.**" in parcours
    discussion = (PROMPTS / "modes" / "discussion.fr.md").read_text(encoding="utf-8")
    assert "start_section" not in discussion and "complete_section" not in discussion


def test_every_available_subject_prompt_has_one_voice_block_at_the_end():
    for info in available_subjects():
        text = (PROMPTS / "subjects" / f"{info.id}.fr.md").read_text(encoding="utf-8")
        assert text.count(VOICE_START) == 1 and text.count(VOICE_END) == 1
        assert text.index(VOICE_START) < text.index(VOICE_END)
        assert "Hors sujet" in text


def test_transcription_prompt_demands_doubt_and_page_markers():
    text = (PROMPTS / "transcription" / "transcribe.fr.md").read_text(encoding="utf-8")
    for convention in ("--- page N ---", "[manuscrit]", "[incertain:", "[illisible]", "[figure :", "[barré:", "[page vide]"):
        assert convention in text, convention
    pack = (PROMPTS / "authoring" / "pack.fr.md").read_text(encoding="utf-8")
    assert "Si le matériel est une transcription de pages" in pack and "p. 5" in pack
