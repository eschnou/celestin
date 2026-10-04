"""Spec 014 R11.2: an estimate is priced only where the price means something."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.domain.ai_config import OPENAI_BASE_URL, AiConfig, Connection, RoleConfig
from app.domain.chapter import RunUsage
from app.services.authoring.agent import estimate_cost

GROQ = Connection("https://api.groq.com/openai/v1", "k")
OPENAI = Connection(OPENAI_BASE_URL, "k")


def config(authoring: Connection, transcription: Connection) -> AiConfig:
    def role(name: str, connection: Connection) -> RoleConfig:
        return RoleConfig(name, "m", None, connection)  # type: ignore[arg-type]

    return AiConfig(role("tutor", OPENAI), role("authoring", authoring), role("transcription", transcription), None)


def usage() -> RunUsage:
    run = RunUsage()
    run.input_tokens, run.output_tokens = 2_000_000, 1_000_000
    run.transcription_input_tokens, run.transcription_output_tokens = 1_000_000, 500_000
    return run


def share(price_in: float, price_out: float) -> float:
    """One share of `usage()`: a million tokens in and half a million out."""
    return price_in * 1 + price_out * 0.5


def test_openai_is_priced_with_the_configured_prices() -> None:
    settings = Settings(_env_file=None)
    run = usage()
    cost = estimate_cost(run, settings, config(OPENAI, OPENAI))
    transcription = share(settings.transcription_price_in, settings.transcription_price_out)
    authoring = share(settings.authoring_price_in, settings.authoring_price_out)
    assert cost == pytest.approx(transcription + authoring)
    assert run.transcription_cost_usd == pytest.approx(transcription)


def test_another_provider_is_not_priced_with_openais_prices() -> None:
    run = usage()
    assert estimate_cost(run, Settings(_env_file=None), config(GROQ, GROQ)) == 0.0
    assert run.transcription_cost_usd == 0.0


def test_each_share_follows_its_own_roles_connection() -> None:
    settings = Settings(_env_file=None)
    run = usage()
    cost = estimate_cost(run, settings, config(GROQ, OPENAI))
    expected = share(settings.transcription_price_in, settings.transcription_price_out)
    assert cost == pytest.approx(run.transcription_cost_usd) and cost == pytest.approx(expected)


def test_explicit_prices_apply_anywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTHORING_PRICE_IN", "0.1")
    monkeypatch.setenv("AUTHORING_PRICE_OUT", "0.2")
    run = usage()
    cost = estimate_cost(run, Settings(_env_file=None), config(GROQ, GROQ))
    assert cost == pytest.approx(0.1 * 1 + 0.2 * 0.5) and run.transcription_cost_usd == 0.0


def test_without_a_configuration_only_explicit_prices_count() -> None:
    assert estimate_cost(usage(), Settings(_env_file=None)) == 0.0
