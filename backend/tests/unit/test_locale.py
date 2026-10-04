"""Spec 010 §3.2, §7.4: the interface languages and the Accept-Language reading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.locale import DEFAULT_LOCALE, LOCALES, is_locale, parse_accept_language

FIXTURES = Path(__file__).parent.parent / "fixtures"
CASES = json.loads((FIXTURES / "accept_language_cases.json").read_text(encoding="utf-8"))
FRONTEND_COPY = (
    Path(__file__).parents[3] / "frontend" / "src" / "lib" / "__tests__" / "accept_language_cases.json"
)


@pytest.mark.parametrize("case", CASES, ids=lambda case: repr(case["header"]))
def test_the_shared_case_table(case: dict) -> None:
    assert parse_accept_language(case["header"]) == case["expected"]


def test_the_table_is_byte_identical_to_the_frontends() -> None:
    assert (FIXTURES / "accept_language_cases.json").read_bytes() == FRONTEND_COPY.read_bytes()


def test_the_supported_list() -> None:
    assert LOCALES == ("fr", "en")
    assert DEFAULT_LOCALE == "fr"
    assert is_locale("en") and not is_locale("de") and not is_locale(None)
