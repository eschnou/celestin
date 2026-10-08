"""Spec 017 R2.4, task 5.5: the wall around the model, with three course languages.

`test_model_input_wall.py` pins the French and the English halves; this adds Dutch: a Dutch course hands the provider the
same input whatever the account's interface language, and a French, an English and a Dutch course hand it three
different inputs, each equal to its own pinned rendering."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.domain.locale import LOCALES
from tests.unit.test_model_input_wall import _developer_text, _run

RENDER = Path(__file__).parents[1] / "fixtures" / "render"


def _dump(calls: list) -> str:
    return json.dumps(calls, ensure_ascii=False, sort_keys=True)


async def test_the_provider_gets_the_same_input_whatever_the_interface_language_of_a_dutch_course(make_client) -> None:
    runs = [_dump(await _run(make_client, locale, language="nl")) for locale in LOCALES]
    assert len(set(runs)) == 1


async def test_three_courses_hand_the_provider_three_different_inputs_each_equal_to_its_pin(make_client) -> None:
    french = await _run(make_client, "nl", language="fr")  # a Dutch interface on each course
    english = await _run(make_client, "nl", language="en")
    dutch = await _run(make_client, "nl", language="nl")
    assert len({_dump(french), _dump(english), _dump(dutch)}) == 3
    sha = lambda text: hashlib.sha256(text.encode("utf-8")).hexdigest()  # noqa: E731
    assert sha(_developer_text(french)) == (RENDER / "system_text_sha.txt").read_text().strip()
    assert sha(_developer_text(english)) == (RENDER / "system_text_sha_en.txt").read_text().strip()
    assert sha(_developer_text(dutch)) == (RENDER / "system_text_sha_nl.txt").read_text().strip()
    assert "Traject van het hoofdstuk" in _developer_text(dutch)
    assert "Stand van het traject" in dutch[0]["input"][-1]["content"][0]["text"]
    assert "Parcours du chapitre" not in _developer_text(dutch) and "Chapter path" not in _developer_text(dutch)
