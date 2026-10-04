"""Spec 010 R5.2, R6.1: the French of every student-facing error is what the code said
before the catalog existed (`tests/fixtures/error_messages_fr.json`, recorded from the
old classes), and the English sits next to it with the same parameters."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain import errors
from app.domain.errors import TutorError
from app.domain.messages import CATALOGS, render
from app.domain.messages.en import MESSAGES as EN

ROWS = json.loads((Path(__file__).parent.parent / "fixtures" / "error_messages_fr.json").read_text("utf-8"))


def build(row: dict) -> TutorError:
    name, args, kwargs = row["make"]
    return getattr(errors, name)(*args, **kwargs)


def ids(row: dict) -> str:
    name, args, kwargs = row["make"]
    return f"{name}({', '.join(map(repr, args))}{', ' if args and kwargs else ''}{kwargs or ''})"


@pytest.mark.parametrize("row", ROWS, ids=ids)
def test_the_french_is_what_the_code_always_said(row: dict) -> None:
    error = build(row)
    assert error.message("fr") == row["fr"]
    assert str(error) == row["fr"]  # the logs and the tests read the French
    assert error.message() == row["fr"]  # French is the default
    assert render(row["key"], "fr", **row["params"]) == row["fr"]
    assert error.body("fr")["message"] == row["fr"]


@pytest.mark.parametrize("row", ROWS, ids=ids)
def test_the_error_names_its_catalog_entry(row: dict) -> None:
    error = build(row)
    assert error.message_key == row["key"]
    for key in (f"{row['key']}.one", f"{row['key']}.other") if "count" in error.params else (row["key"],):
        assert key in CATALOGS["fr"] and key in CATALOGS["en"], key


@pytest.mark.parametrize("row", ROWS, ids=ids)
def test_the_english_renders_with_the_same_parameters(row: dict) -> None:
    english = build(row).message("en")
    assert english and english != row["fr"]
    assert "{" not in english, english  # every field was filled


def test_english_reads_naturally_for_a_few_cases() -> None:
    assert errors.NotAuthenticated().message("en") == "Sign in to continue."
    assert errors.AuthoringBusy(1).message("en") == "A chapter is already being prepared. Wait until it's ready."
    assert errors.AuthoringBusy(3).message("en") == "3 chapters are already being prepared. Wait until they're ready."
    assert errors.DocumentTooLarge(25 * 1048576).message("en") == "The document is over 25 MB."
    assert EN["too_many_pages"].format(maximum=5) == "At most 5 pages per chapter. Split the document."


def _concrete_subclasses(cls: type) -> list[type]:
    found: list[type] = []
    for sub in cls.__subclasses__():
        found.append(sub)
        found.extend(_concrete_subclasses(sub))
    return found


def test_every_error_class_is_covered_in_both_languages() -> None:
    covered = {row["make"][0] for row in ROWS}
    for cls in _concrete_subclasses(TutorError):
        assert cls.__name__ in covered, f"{cls.__name__} has no row in error_messages_fr.json"


def test_the_wire_shape_keeps_its_code() -> None:
    body = errors.SourceLength(3, 9).body("en")
    assert body == {"code": "source_length", "message": "The text must be between 3 and 9 characters long."}
