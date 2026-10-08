from __future__ import annotations

import pytest

from app.config import REPO_ROOT, Settings


def test_defaults_applied() -> None:
    s = Settings(openai_api_key="k", _env_file=None)
    assert s.openai_model == "gpt-6.1-sol"
    assert s.max_tool_rounds == 6
    assert s.max_message_chars == 4000
    assert s.max_history_entries == 400
    assert s.history_token_budget == 30_000
    assert s.debug_log_prompts is False


def test_ai_defaults_are_the_openai_ones() -> None:
    s = Settings(_env_file=None)
    assert s.openai_base_url == "https://api.openai.com/v1"
    assert (s.ai_api_style, s.ai_structured_outputs) == ("responses", "schema")
    assert (s.openai_model, s.authoring_model, s.transcription_model, s.voice_model) == (
        "gpt-6.1-sol", "gpt-6.1-sol", "gpt-6.1-sol", "gpt-realtime-2.1",
    )
    assert (s.tutor_reasoning_effort, s.authoring_reasoning_effort) == ("", "medium")
    assert (s.transcription_reasoning_effort, s.voice_reasoning_effort) == ("low", "low")
    for role in ("tutor", "authoring", "transcription", "voice"):
        assert getattr(s, f"{role}_base_url") == "" and getattr(s, f"{role}_api_key") == ""


def test_the_environment_is_told_from_a_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("AUTHORING_REASONING_EFFORT", "")
    s = Settings(_env_file=None)
    assert "openai_base_url" in s.model_fields_set
    assert "authoring_reasoning_effort" in s.model_fields_set and s.authoring_reasoning_effort == ""
    assert "openai_model" not in s.model_fields_set


def test_a_dotenv_value_counts_as_the_environment(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("OPENAI_MODEL=openai/gpt-oss-120b\nVOICE_BASE_URL=https://api.openai.com/v1\n")
    s = Settings(_env_file=env)
    assert {"openai_model", "voice_base_url"} <= s.model_fields_set


def test_an_unknown_style_or_effort_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import ValidationError

    monkeypatch.setenv("AI_API_STYLE", "grpc")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    monkeypatch.setenv("AI_API_STYLE", "chat")
    monkeypatch.setenv("TUTOR_REASONING_EFFORT", "extreme")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_env_override_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "gpt-6-astra")
    monkeypatch.setenv("MAX_TOOL_ROUNDS", "2")
    s = Settings(openai_api_key="k", _env_file=None)
    assert s.openai_model == "gpt-6-astra"
    assert s.max_tool_rounds == 2


def test_paths_are_absolute() -> None:
    s = Settings(openai_api_key="k", _env_file=None)
    assert s.prompts_dir.is_absolute()
    assert s.prompts_dir.is_dir()
    assert s.timezone == "Europe/Brussels"


def test_relative_path_resolved_against_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMPTS_DIR", "backend/other")
    s = Settings(openai_api_key="k", _env_file=None)
    assert s.prompts_dir == (REPO_ROOT / "backend" / "other").resolve()


def test_document_defaults() -> None:
    s = Settings(openai_api_key="k", _env_file=None)
    assert (s.document_max_bytes, s.document_max_pages, s.document_min_pixels) == (26_214_400, 50, 800)
    assert (s.transcription_dpi, s.transcription_max_side_px, s.transcription_batch_pages) == (150, 1800, 2)
    assert s.transcription_detail == "high" and s.authoring_timeout_s == 1800


def test_content_limits_defaults() -> None:
    s = Settings(openai_api_key="k", _env_file=None)
    assert (s.chapter_text_min_chars, s.chapter_text_max_chars, s.pack_max_chars) == (300, 100_000, 60_000)
    assert (s.max_courses_per_student, s.max_chapters_per_course) == (30, 40)
    assert s.max_body_bytes == 1_048_576


def test_cors_origins_from_comma_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    s = Settings(openai_api_key="k", _env_file=None)
    assert s.cors_origins == ["http://a.test", "http://b.test"]


def test_voice_defaults() -> None:
    s = Settings(openai_api_key="k", _env_file=None)
    assert s.voice_enabled is True
    assert s.voice_model == "gpt-realtime-2.1"
    assert s.voice_name == "marin"
    assert s.voice_turn_detection == "semantic_vad"
    assert s.voice_secret_ttl_s == 90
    assert s.voice_session_max_s == 1500
    assert s.voice_idle_s == 180
    assert s.voice_sessions_per_hour == 6


def test_voice_speed_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_SPEED", "2")
    with pytest.raises(ValueError):
        Settings(openai_api_key="k", _env_file=None)


def test_voice_turn_detection_restricted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_TURN_DETECTION", "magic")
    with pytest.raises(ValueError):
        Settings(openai_api_key="k", _env_file=None)


def test_account_defaults() -> None:
    s = Settings(openai_api_key="k", _env_file=None)
    assert s.database_url == "sqlite:///./data/celestin.db"
    assert s.session_idle_days == 30 and s.session_absolute_days == 90
    assert s.cookie_secure is True
    assert (s.argon2_memory_kib, s.argon2_time, s.argon2_parallelism) == (19456, 2, 1)
    assert s.auth_attempts_per_window == 10 and s.auth_window_s == 900


def test_session_secret_required() -> None:
    from app.config import MissingSessionSecret

    with pytest.raises(MissingSessionSecret):
        Settings(openai_api_key="k", session_secret="tiny", _env_file=None).require_session_secret()
    assert Settings(openai_api_key="k", session_secret="x" * 16, _env_file=None).require_session_secret()


def test_discussion_defaults() -> None:
    """007 design 4.4: a stored conversation is capped, and starting them is bounded."""
    s = Settings(_env_file=None)
    assert s.discussion_max_entries == 400
    assert s.discussion_max_chars == 200_000
    assert s.discussion_conversations_per_day == 30


def test_discussion_limits_come_from_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("DISCUSSION_MAX_ENTRIES", "12")
    monkeypatch.setenv("DISCUSSION_CONVERSATIONS_PER_DAY", "3")
    s = Settings(_env_file=None)
    assert s.discussion_max_entries == 12 and s.discussion_conversations_per_day == 3


@pytest.mark.parametrize(
    ("raw", "expected"), [("auto", "auto"), ("true", True), ("false", False), ("1", True), ("0", False)]
)
def test_cookie_secure_accepts_auto_and_booleans(monkeypatch: pytest.MonkeyPatch, raw: str, expected: object) -> None:
    monkeypatch.setenv("COOKIE_SECURE", raw)
    assert Settings(_env_file=None).cookie_secure == expected


def test_cookie_secure_defaults_to_true_and_refuses_nonsense(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings(_env_file=None).cookie_secure is True
    monkeypatch.setenv("COOKIE_SECURE", "sometimes")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_secrets_dir_is_unset_by_default_and_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings(_env_file=None).secrets_dir is None
    monkeypatch.setenv("SECRETS_DIR", "")
    assert Settings(_env_file=None).secrets_dir is None


def test_secrets_dir_is_resolved_like_the_other_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRETS_DIR", "/data/secrets")
    assert str(Settings(_env_file=None).secrets_dir) == "/data/secrets"
    monkeypatch.setenv("SECRETS_DIR", "backend/data/secrets")
    assert Settings(_env_file=None).secrets_dir == (REPO_ROOT / "backend/data/secrets").resolve()


def test_migration_backups_kept_defaults_to_five_and_needs_one(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings(_env_file=None).migration_backups_kept == 5
    monkeypatch.setenv("MIGRATION_BACKUPS_KEPT", "0")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_the_streamed_call_limits_and_their_bounds() -> None:
    """Spec 016 R3."""
    s = Settings(openai_api_key="k", _env_file=None)
    assert (s.authoring_first_event_timeout_s, s.authoring_idle_timeout_s, s.authoring_progress_log_s) == (180, 60, 30)
    assert s.authoring_call_timeout_s is None
    for name, floor in (
        ("authoring_first_event_timeout_s", 10),
        ("authoring_idle_timeout_s", 5),
        ("authoring_progress_log_s", 5),
    ):
        assert getattr(Settings(openai_api_key="k", _env_file=None, **{name: floor}), name) == floor
        with pytest.raises(ValueError):
            Settings(openai_api_key="k", _env_file=None, **{name: floor - 1})


def test_the_old_per_call_timeout_is_still_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTHORING_CALL_TIMEOUT_S", "300")
    assert Settings(openai_api_key="k", _env_file=None).authoring_call_timeout_s == 300
