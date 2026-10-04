"""Spec 014 §3.1: the pure parts of the AI configuration."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.domain.ai_config import (
    OPENAI_BASE_URL,
    AiConfig,
    Connection,
    RoleConfig,
    calls_url,
    normalise_base_url,
    priced,
)
from app.domain.errors import InvalidAiSettings

GROQ = "https://api.groq.com/openai/v1"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("https://api.openai.com/v1", "https://api.openai.com/v1"),
        ("  https://api.groq.com/openai/v1/  ", GROQ),
        ("http://localhost:11434/v1", "http://localhost:11434/v1"),
        ("http://192.168.1.20:8000/v1///", "http://192.168.1.20:8000/v1"),
        ("http://host.docker.internal:11434", "http://host.docker.internal:11434"),
        ("https://gateway.example/v1?api-version=2", "https://gateway.example/v1?api-version=2"),
        ("HTTPS://Api.Example.COM/V1", "https://Api.Example.COM/V1"),
    ],
)
def test_addresses_are_normalised(raw: str, expected: str) -> None:
    assert normalise_base_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "ftp://x.test/v1", "file:///etc/passwd", "javascript:alert(1)", "api.groq.com/openai/v1", "http://",
     "https://user@x.test/v1", "https://user:pw@x.test/v1", "https://x.test/v1#frag", "https://x.test:99999/v1",
     "https://" + "a" * 2050],
)
def test_unusable_addresses_are_refused_with_the_field_named(raw: str) -> None:
    with pytest.raises(InvalidAiSettings) as raised:
        normalise_base_url(raw, "tutor.base_url")
    assert raised.value.fields == ["tutor.base_url"]


def test_a_connection_knows_its_host_and_whether_it_is_openai() -> None:
    assert Connection(OPENAI_BASE_URL).is_openai and Connection(OPENAI_BASE_URL).host == "api.openai.com"
    assert not Connection(GROQ).is_openai and Connection(GROQ).host == "api.groq.com"
    assert not Connection("https://api.openai.com.evil.test/v1").is_openai
    assert not Connection("https://evil.test/api.openai.com").is_openai


def test_a_connection_is_usable_with_a_key_or_when_it_is_not_openai() -> None:
    assert not Connection(OPENAI_BASE_URL).usable and Connection(OPENAI_BASE_URL, "k").usable
    assert Connection("http://localhost:11434/v1").usable


def test_the_representations_never_show_a_key() -> None:
    connection = Connection(GROQ, "gsk-very-secret")
    role = RoleConfig("tutor", "m", None, connection)
    config = AiConfig(role, role, role, None)
    shown = repr(connection) + repr(role) + repr(config) + str(config.describe())
    assert "gsk-very-secret" not in shown and "api.groq.com" in shown


def test_describe_gives_host_model_and_style_per_role() -> None:
    tutor = RoleConfig("tutor", "oss", None, Connection(GROQ, "k"))
    voice = RoleConfig("voice", "rt", None, Connection(OPENAI_BASE_URL, "k"))
    config = AiConfig(tutor, tutor, tutor, voice)
    assert config.describe()["voice"] == {"host": "api.openai.com", "model": "rt", "style": "responses"}
    assert [r.role for r in config.roles()] == ["tutor", "tutor", "tutor", "voice"]
    assert AiConfig(tutor, tutor, tutor, None).role("voice") is None


def test_the_calls_url_is_the_voice_servers_realtime_route() -> None:
    assert calls_url(Connection(OPENAI_BASE_URL)) == "https://api.openai.com/v1/realtime/calls"
    assert calls_url(Connection("https://rt.example/v1")) == "https://rt.example/v1/realtime/calls"
    assert calls_url(Connection("http://localhost:8000/v1")) == "http://localhost:8000/v1/realtime/calls"
    assert calls_url(Connection("http://10.0.0.5:8000/v1")) == "http://10.0.0.5:8000/v1/realtime/calls"
    assert calls_url(Connection("http://gpu-box:8000/v1")) == "http://gpu-box:8000/v1/realtime/calls"


def test_a_public_http_host_cannot_be_a_voice_server() -> None:
    with pytest.raises(InvalidAiSettings):
        calls_url(Connection("http://rt.example.com/v1"))


def test_prices_apply_to_openai_or_when_set_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    default = Settings(_env_file=None)
    assert priced(default, Connection(OPENAI_BASE_URL), "authoring_price_in")
    assert not priced(default, Connection(GROQ), "authoring_price_in")
    assert not priced(default, None, "authoring_price_in")
    monkeypatch.setenv("AUTHORING_PRICE_IN", "0.15")
    explicit = Settings(_env_file=None)
    assert priced(explicit, Connection(GROQ), "authoring_price_in", "authoring_price_out")
    assert not priced(explicit, Connection(GROQ), "transcription_price_in")
    assert priced(explicit, None, "authoring_price_in")
