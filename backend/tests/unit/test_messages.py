"""Spec 010 §3.3: the message catalog and its two languages."""

from __future__ import annotations

import logging
from string import Formatter

import pytest

from app.domain import messages
from app.domain.messages import CATALOGS, plural_category, render
from app.domain.messages.en import MESSAGES as EN
from app.domain.messages.fr import MESSAGES as FR


def fields(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name}


def test_both_languages_have_the_same_keys() -> None:
    assert set(FR) == set(EN), sorted(set(FR) ^ set(EN))


@pytest.mark.parametrize("key", sorted(FR))
def test_each_message_takes_the_same_parameters_in_both_languages(key: str) -> None:
    assert fields(FR[key]) == fields(EN[key]), key


def test_every_plural_has_both_forms() -> None:
    for catalog in CATALOGS.values():
        ones = {key[: -len(".one")] for key in catalog if key.endswith(".one")}
        others = {key[: -len(".other")] for key in catalog if key.endswith(".other")}
        assert ones == others
        assert not ones & set(catalog), "a plural key must not also exist whole"


def test_no_message_is_empty_or_untranslated() -> None:
    for key, text in EN.items():
        assert text.strip(), key
    # The English text is not the French text left in place. (`{msg}` alone is a
    # passthrough of a message that has no language of its own.)
    same = [key for key in FR if FR[key] == EN[key] and FR[key] != "{msg}"]
    assert same == [], same


@pytest.mark.parametrize(
    ("locale", "count", "expected"),
    [("fr", 0, "one"), ("fr", 1, "one"), ("fr", 2, "other"), ("en", 0, "other"), ("en", 1, "one"), ("en", 2, "other")],
)
def test_plural_categories(locale: str, count: int, expected: str) -> None:
    assert plural_category(locale, count) == expected  # type: ignore[arg-type]


def test_render_fills_parameters_and_picks_the_plural() -> None:
    assert render("source_length", "fr", minimum=3, maximum=9) == "Le texte doit faire entre 3 et 9 caractères."
    assert render("source_length", "en", minimum=3, maximum=9) == "The text must be between 3 and 9 characters long."
    assert render("authoring_busy", "en", limit=1, count=1).startswith("A chapter")
    assert render("authoring_busy", "en", limit=3, count=3).startswith("3 chapters")
    assert render("authoring_busy", "fr", limit=3, count=3).startswith("3 chapitres")


def test_the_default_language_is_french() -> None:
    assert render("not_found") == FR["not_found"]


def test_a_key_missing_in_english_falls_back_to_french_and_is_logged_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setitem(FR, "only_in_french", "Seulement en français.")
    messages._fallbacks_logged.discard("only_in_french")
    with caplog.at_level(logging.WARNING):
        assert render("only_in_french", "en") == "Seulement en français."
        assert render("only_in_french", "en") == "Seulement en français."
    records = [r for r in caplog.records if r.message == "i18n_fallback"]
    assert len(records) == 1 and records[0].key == "only_in_french"  # type: ignore[attr-defined]


def test_an_unknown_key_renders_the_generic_error_in_the_requests_language() -> None:
    assert render("no.such.key", "fr") == FR["internal"]
    assert render("no.such.key", "en") == EN["internal"]


def test_a_document_refusal_with_no_specific_key_still_has_its_words() -> None:
    """`DocumentInvalid()` defaults to the reason `unreadable`; it must not fall to the generic error."""
    from app.domain.errors import DocumentInvalid

    assert DocumentInvalid().message("fr") == "Ce document est illisible."
    assert DocumentInvalid("unreadable").message("en") == "This document can't be read."


def test_a_missing_parameter_does_not_raise() -> None:
    assert "{minimum}" in render("source_length", "fr", maximum=9)
