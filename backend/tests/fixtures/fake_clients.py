"""A client factory for the provider hub that builds scripted fakes and remembers what it was asked
(spec 014)."""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.domain.ai_config import AiConfig
from app.providers.base import Completed, CompletionResult, TextDelta
from app.providers.hub import Clients
from tests.fixtures.fake_llm import FakeLLM
from tests.fixtures.fake_transcriber import FakeTranscriber
from tests.fixtures.fake_realtime import FakeRealtime


class FixedAiConfig:
    """An `AiConfigSource` that never changes."""

    def __init__(self, config: AiConfig | None) -> None:
        self.config = config


class TaggedCompletion:
    """A completion client that answers with its role and model, to tell the roles apart."""

    def __init__(self, role: str, model: str) -> None:
        self.role, self.model = role, model
        self.calls: list[dict[str, Any]] = []

    async def complete(self, **kwargs: Any) -> CompletionResult:
        self.calls.append(kwargs)
        return CompletionResult(text=f"{self.role}:{self.model}")


class Factory:
    """`Factory()(settings, config)`: builds fakes tagged with the models in the configuration."""

    def __init__(self, fail: Exception | None = None) -> None:
        self.configs: list[AiConfig] = []
        self.fail = fail

    def __call__(self, settings: Settings, config: AiConfig) -> Clients:
        if self.fail:
            raise self.fail
        self.configs.append(config)
        tutor = FakeLLM([[TextDelta(f"from {config.tutor.model}"), Completed()]])
        tutor.model = config.tutor.model  # type: ignore[misc]
        return Clients(
            config=config,
            tutor=tutor,
            authoring=TaggedCompletion("authoring", config.authoring.model),
            transcription=TaggedCompletion("transcription", config.transcription.model),
            realtime=FakeRealtime(secret=f"secret-{config.voice.model}") if config.voice else None,
            transcriber=FakeTranscriber() if config.dictation else None,
        )


class PassingFactory:
    """Clients whose every live check passes: a board call, a schema answer, an image read, a secret."""

    def __init__(self, **broken: Exception | list) -> None:
        self.broken = broken
        self.configs: list[AiConfig] = []

    def __call__(self, settings: Settings, config: AiConfig) -> Clients:
        from tests.conftest import CARD, tool_call
        from tests.fixtures.fake_completion import FakeCompletion, data, text

        self.configs.append(config)
        tutor_script = self.broken.get("tutor") or [[tool_call("display_board", {"card": CARD}), Completed()]] * 4
        return Clients(
            config=config,
            tutor=FakeLLM(tutor_script),  # type: ignore[arg-type]
            authoring=FakeCompletion(self.broken.get("authoring") or [data({"ok": True, "word": "bonjour"})] * 4),  # type: ignore[arg-type]
            transcription=FakeCompletion(self.broken.get("transcription") or [text("42")] * 4),  # type: ignore[arg-type]
            realtime=FakeRealtime(secret="ek_live_check") if config.voice else None,
        )
