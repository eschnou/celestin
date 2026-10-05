"""Specs 013 §3.6, 014 §3.5: proxies over clients that a new configuration replaces."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.domain.ai_config import OPENAI_BASE_URL, AiConfig, Connection, RoleConfig
from app.domain.errors import AiNotConfigured, InvalidAiSettings, VoiceDisabled
from app.providers.base import TextDelta
from app.providers.hub import ProviderHub, build_clients
from app.providers.openai_chat import OpenAIChatClient
from app.providers.openai_realtime import OpenAIRealtimeClient
from app.providers.openai_responses import OpenAIResponsesClient
from tests.fixtures.fake_clients import Factory, TaggedCompletion

OPENAI = Connection(OPENAI_BASE_URL, "sk-very-secret")
GROQ = Connection("https://api.groq.com/openai/v1", "gsk-very-secret")


def config(tag: str = "one", *, voice: bool = True, transcription: Connection = OPENAI) -> AiConfig:
    def role(name: str, model: str, connection: Connection = OPENAI) -> RoleConfig:
        return RoleConfig(name, f"{model}-{tag}", None, connection)  # type: ignore[arg-type]

    return AiConfig(
        tutor=role("tutor", "tutor"),
        authoring=role("authoring", "authoring"),
        transcription=role("transcription", "transcription", transcription),
        voice=role("voice", "voice") if voice else None,
    )


@pytest.fixture
def factory() -> Factory:
    return Factory()


@pytest.fixture
def hub(settings: Settings, factory: Factory) -> ProviderHub:
    return ProviderHub(settings, factory)


async def drain(context) -> str:
    async with context as events:
        return "".join([e.text async for e in events if isinstance(e, TextDelta)])


async def complete(hub: ProviderHub, role: str = "authoring") -> str:
    return (await hub.authoring_llm.complete(role=role, instructions=[], input=[], max_output_tokens=10)).text  # type: ignore[arg-type]


async def test_without_a_configuration_every_proxy_raises(hub: ProviderHub) -> None:
    assert hub.configured is False and hub.config is None and hub.voice_available is False
    with pytest.raises(AiNotConfigured):
        hub.llm.stream(input=[], tools=[])
    with pytest.raises(AiNotConfigured):
        await complete(hub)
    with pytest.raises(AiNotConfigured):
        await hub.realtime.create_client_secret(session={}, ttl_s=60)
    assert hub.llm.model == ""


async def test_a_configuration_configures_all_proxies(hub: ProviderHub, factory: Factory) -> None:
    cfg = config()
    hub.apply(cfg)
    assert hub.configured and hub.config is cfg and hub.voice_available and factory.configs == [cfg]
    assert await drain(hub.llm.stream(input=[], tools=[])) == "from tutor-one"
    assert hub.llm.model == "tutor-one"
    assert (await hub.realtime.create_client_secret(session={}, ttl_s=60)).value == "secret-voice-one"


async def test_the_completion_proxy_routes_by_role(hub: ProviderHub) -> None:
    hub.apply(config())
    assert await complete(hub, "authoring") == "authoring:authoring-one"
    assert await complete(hub, "transcription") == "transcription:transcription-one"


async def test_a_new_configuration_swaps_everything(hub: ProviderHub) -> None:
    hub.apply(config("one"))
    hub.apply(config("two"))
    assert await drain(hub.llm.stream(input=[], tools=[])) == "from tutor-two"
    assert await complete(hub, "transcription") == "transcription:transcription-two"
    assert (await hub.realtime.create_client_secret(session={}, ttl_s=60)).value == "secret-voice-two"


async def test_a_call_that_resolved_its_client_finishes_on_it(hub: ProviderHub) -> None:
    hub.apply(config("old"))
    in_flight = hub.llm.stream(input=[], tools=[])  # resolved now, entered later
    old = hub.current().tutor
    hub.apply(config("new"))
    assert await drain(in_flight) == "from tutor-old"
    assert await drain(hub.llm.stream(input=[], tools=[])) == "from tutor-new"
    assert len(old.calls) == 1 and len(hub.current().tutor.calls) == 1  # type: ignore[attr-defined]


async def test_none_unconfigures_again(hub: ProviderHub) -> None:
    hub.apply(config())
    hub.apply(None)
    assert hub.configured is False
    with pytest.raises(AiNotConfigured):
        hub.llm.stream(input=[], tools=[])


async def test_voice_off_means_the_realtime_proxy_refuses(hub: ProviderHub) -> None:
    hub.apply(config(voice=False))
    assert hub.configured and not hub.voice_available
    with pytest.raises(VoiceDisabled):
        await hub.realtime.create_client_secret(session={}, ttl_s=60)


def test_none_builds_nothing(hub: ProviderHub, factory: Factory) -> None:
    hub.apply(None)
    assert factory.configs == []


def test_a_configuration_that_cannot_be_built_leaves_the_previous_one(settings: Settings) -> None:
    factory = Factory()
    hub = ProviderHub(settings, factory)
    first = config("one")
    hub.apply(first)
    factory.fail = InvalidAiSettings(["tutor.api_style"])
    with pytest.raises(InvalidAiSettings):
        hub.apply(config("two"))
    assert hub.config is first
    with pytest.raises(InvalidAiSettings):
        hub.build(config("three"))
    assert hub.config is first  # building is not installing


def test_the_key_is_not_in_the_representations(hub: ProviderHub) -> None:
    cfg = config()
    hub.apply(cfg)
    shown = repr(hub) + repr(hub.current()) + repr(hub.llm) + repr(cfg) + repr(OPENAI) + repr(cfg.tutor)
    assert "sk-very-secret" not in shown and OPENAI.api_key is not None


def test_the_real_factory_builds_a_client_per_role_with_its_own_connection(settings: Settings) -> None:
    cfg = config(transcription=GROQ)
    clients = build_clients(settings, cfg)
    assert isinstance(clients.tutor, OpenAIResponsesClient) and clients.tutor.model == "tutor-one"
    assert isinstance(clients.authoring, OpenAIResponsesClient) and clients.authoring.model == "authoring-one"
    assert isinstance(clients.transcription, OpenAIResponsesClient)
    assert clients.transcription.model == "transcription-one"
    assert clients.transcription._connection is GROQ and clients.authoring._connection is OPENAI  # type: ignore[attr-defined]
    assert isinstance(clients.realtime, OpenAIRealtimeClient) and clients.config is cfg


def test_the_real_factory_builds_no_realtime_client_without_voice(settings: Settings) -> None:
    assert build_clients(settings, config(voice=False)).realtime is None


def test_the_real_factory_picks_the_adapter_of_each_roles_api_style(settings: Settings) -> None:
    chat = Connection("http://localhost:11434/v1", None, "chat")
    base = config()
    cfg = AiConfig(
        RoleConfig("tutor", "m", None, chat), base.authoring, RoleConfig("transcription", "v", "low", chat), base.voice
    )
    clients = build_clients(settings, cfg)
    assert isinstance(clients.tutor, OpenAIChatClient) and clients.tutor.model == "m"
    assert isinstance(clients.transcription, OpenAIChatClient) and clients.transcription._effort == "low"  # type: ignore[attr-defined]
    assert isinstance(clients.authoring, OpenAIResponsesClient)  # the others keep their own style


def test_tagged_completion_is_exported() -> None:
    assert TaggedCompletion("r", "m").role == "r"


# --- the usage ledger (spec 015 §3.2) ------------------------------------------


class _Sink:
    def __init__(self) -> None:
        self.entries: list = []

    def record(self, entry) -> None:  # noqa: ANN001
        self.entries.append(entry)


@pytest.fixture
def recorded(settings: Settings, factory: Factory):
    sink = _Sink()
    return ProviderHub(settings, factory, sink), sink


async def test_a_hub_with_a_sink_records_every_role(recorded) -> None:
    from app.domain.usage import UsageScope, usage_scope

    hub, sink = recorded
    cfg = config("one")
    hub.apply(cfg)
    with usage_scope(UsageScope("u1", "authoring", correlation_id="run1")):
        await drain(hub.llm.stream(input=[], tools=[]))
        await complete(hub, "authoring")
        await complete(hub, "transcription")
    assert [(e.role, e.feature, e.model, e.provider) for e in sink.entries] == [
        ("tutor", "authoring", "tutor-one", "api.openai.com"),
        ("authoring", "authoring", "authoring-one", "api.openai.com"),
        ("transcription", "document_reading", "transcription-one", "api.openai.com"),
    ]


async def test_the_clients_the_live_test_uses_directly_record_too(recorded) -> None:
    from app.domain.usage import UsageScope, usage_scope

    hub, sink = recorded
    hub.apply(config())
    with usage_scope(UsageScope("admin", "ai_test")):
        async with hub.current().tutor.stream(input=[], tools=[]) as events:
            [e async for e in events]
        await hub.current().authoring.complete(role="authoring", instructions=[], input=[], max_output_tokens=1)
    assert [(e.user_id, e.feature) for e in sink.entries] == [("admin", "ai_test")] * 2


async def test_without_a_sink_the_clients_are_the_factorys(hub: ProviderHub, factory: Factory) -> None:
    from app.providers.recording import RecordingLLM

    hub.apply(config())
    assert not isinstance(hub.current().tutor, RecordingLLM)


async def test_a_swap_records_the_new_model_and_a_call_in_flight_the_old_one(recorded) -> None:
    from app.domain.usage import UsageScope, usage_scope

    hub, sink = recorded
    hub.apply(config("old"))
    with usage_scope(UsageScope("u1", "tutor_turn")):
        in_flight = hub.llm.stream(input=[], tools=[])
        hub.apply(config("new"))
        await drain(in_flight)
        await drain(hub.llm.stream(input=[], tools=[]))
    assert [e.model for e in sink.entries] == ["tutor-old", "tutor-new"]


async def test_the_realtime_client_is_not_wrapped(recorded) -> None:
    hub, sink = recorded
    hub.apply(config())
    assert (await hub.realtime.create_client_secret(session={}, ttl_s=60)).value == "secret-voice-one"
    assert sink.entries == []


async def test_dictation_is_wrapped_only_when_it_is_on(settings: Settings, factory: Factory) -> None:
    from dataclasses import replace

    from app.domain.ai_config import DictationConfig
    from app.providers.recording import RecordingTranscriber

    hub = ProviderHub(settings, factory, _Sink())
    hub.apply(config())
    assert hub.current().transcriber is None
    hub.apply(replace(config(), dictation=DictationConfig("stt-model", OPENAI)))
    assert isinstance(hub.current().transcriber, RecordingTranscriber)
