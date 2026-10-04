"""Spec 013 R4: the generated secrets."""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

import pytest

from app.config import MissingSessionSecret, Settings
from app.secret_files import SecretFileError, load_secrets


def settings_for(directory: Path | None, **extra: object) -> Settings:
    return Settings(secrets_dir=directory, _env_file=None, **extra)  # type: ignore[arg-type]


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_without_a_directory_it_is_the_old_behaviour() -> None:
    with pytest.raises(MissingSessionSecret):
        load_secrets(settings_for(None))
    got = load_secrets(settings_for(None, session_secret="0123456789abcdef"))
    assert got.session_secret == "0123456789abcdef" and got.encryption_key is None


def test_both_files_are_generated_private(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    directory = tmp_path / "secrets"
    with caplog.at_level(logging.INFO):
        got = load_secrets(settings_for(directory))
    assert mode(directory) == 0o700
    for name in ("session_secret", "encryption_key"):
        assert mode(directory / name) == 0o600
        assert len((directory / name).read_text().strip()) == 64
    assert got.encryption_key is not None and len(got.encryption_key) == 32
    assert got.session_secret == (directory / "session_secret").read_text().strip()
    record = next(r for r in caplog.records if r.message == "secrets_generated")
    assert record.files == ["session_secret", "encryption_key"]  # type: ignore[attr-defined]
    assert got.session_secret not in caplog.text and got.session_secret not in repr(got)


def test_a_second_load_reads_the_same_values_and_writes_nothing(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    first = load_secrets(settings_for(tmp_path))
    before = {p.name: p.stat().st_mtime_ns for p in tmp_path.iterdir()}
    caplog.clear()  # the first load logged: only the second is under test
    with caplog.at_level(logging.INFO):
        second = load_secrets(settings_for(tmp_path))
    assert (second.session_secret, second.encryption_key) == (first.session_secret, first.encryption_key)
    assert {p.name: p.stat().st_mtime_ns for p in tmp_path.iterdir()} == before
    assert not [r for r in caplog.records if r.message == "secrets_generated"]


def test_the_environment_session_secret_wins_and_creates_no_file(tmp_path: Path) -> None:
    got = load_secrets(settings_for(tmp_path, session_secret="from-the-environment-0123"))
    assert got.session_secret == "from-the-environment-0123"
    assert not (tmp_path / "session_secret").exists()
    assert (tmp_path / "encryption_key").exists() and got.encryption_key is not None


def test_a_short_session_secret_in_the_environment_is_not_used(tmp_path: Path) -> None:
    got = load_secrets(settings_for(tmp_path, session_secret="short"))
    assert got.session_secret == (tmp_path / "session_secret").read_text().strip()


@pytest.mark.parametrize("name, content", [("session_secret", "tooshort"), ("encryption_key", "abc"), ("encryption_key", "z" * 64)])
def test_a_bad_file_stops_the_start_and_is_not_replaced(tmp_path: Path, name: str, content: str) -> None:
    (tmp_path / name).write_text(content)
    with pytest.raises(SecretFileError) as exc:
        load_secrets(settings_for(tmp_path))
    assert str(tmp_path / name) in str(exc.value)
    assert (tmp_path / name).read_text() == content


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads anything")
def test_an_unreadable_file_stops_the_start(tmp_path: Path) -> None:
    load_secrets(settings_for(tmp_path))
    (tmp_path / "encryption_key").chmod(0)
    try:
        with pytest.raises(SecretFileError, match="encryption_key"):
            load_secrets(settings_for(tmp_path))
    finally:
        (tmp_path / "encryption_key").chmod(0o600)


def test_the_two_files_are_independent(tmp_path: Path) -> None:
    first = load_secrets(settings_for(tmp_path))
    (tmp_path / "session_secret").unlink()
    second = load_secrets(settings_for(tmp_path))
    assert second.encryption_key == first.encryption_key and second.session_secret != first.session_secret
    (tmp_path / "encryption_key").unlink()
    third = load_secrets(settings_for(tmp_path))
    assert third.session_secret == second.session_secret and third.encryption_key != first.encryption_key
