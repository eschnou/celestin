"""Spec 014 §3.3, §3.4: which configuration is in force, and saving, listing models and testing it."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest
from sqlalchemy import Engine

from app.config import MissingApiKey, Settings
from app.db.repositories import Repositories
from app.domain.errors import (
    AiKeyRejected,
    AiNotConfigured,
    InvalidAiSettings,
    ProviderUnavailable,
    SettingFromEnvironment,
    StorageUnavailable,
)
from app.providers.base import ModelVisibility, ProbeResult
from app.providers.hub import ProviderHub
from app.services.ai_resolution import LEGACY_CONTEXT, LEGACY_SETTING, SETTING, AiConfigError, key_context
from app.services.ai_settings import (
    AiSettingsService,
    ConnectionInput,
    RoleInput,
    SaveRequest,
    load_ai_config,
)
from app.services.cipher import Cipher
from tests.fixtures.fake_clients import Factory, PassingFactory
from tests.fixtures.fake_probe import FakeProbe

KEY = "sk-live-0123456789abcd"
GROQ = "https://api.groq.com/openai/v1"
GROQ_KEY = "gsk_fake_0123456789abcd"
OSS = "openai/gpt-oss-120b"


def settings_with(**env: object) -> Settings:
    """Settings as an operator's environment would make them: only what is passed counts as set."""
    return Settings(session_secret="test-secret-long-enough", database_url="sqlite://", _env_file=None, **env)  # type: ignore[arg-type]


def make(
    repos: Repositories,
    *,
    cipher: Cipher | bool | None = True,
    probe: FakeProbe | None = None,
    factory: Factory | None = None,
    **env: object,
):
    """A service over `repos`. `cipher`: a Cipher to share one between two services (a restart), True for a
    fresh one, False for none."""
    factory = factory or Factory()
    settings = settings_with(**env)
    hub = ProviderHub(settings, factory)
    probe = probe or FakeProbe()
    service = AiSettingsService(
        repos.app_settings,
        cipher if isinstance(cipher, Cipher) else (Cipher(os.urandom(32)) if cipher else None),
        hub,
        probe,
        settings,
    )
    return service, hub, probe, factory


def groq_request(**over: object) -> SaveRequest:
    default = ConnectionInput(GROQ, api_key=GROQ_KEY)
    roles = {
        "tutor": RoleInput(model=OSS),
        "authoring": RoleInput(model=OSS, reasoning_effort="low"),
        "transcription": RoleInput(model="qwen/qwen3.8-27b"),
    }
    return SaveRequest(over.get("default", default), over.get("roles", roles))  # type: ignore[arg-type]


def document(repos: Repositories) -> dict:
    raw = repos.app_settings.get(SETTING)
    assert raw is not None
    return json.loads(raw)


# ------------------------------------------------------------------ what is in force


async def test_nothing_in_force_by_default(repos) -> None:
    service, hub, _, _ = make(repos)
    service.load()
    resolved = service.resolve()
    assert resolved.config is None and not hub.configured and resolved.default.key.source == "none"
    assert resolved.default.base_url.source == "default" and resolved.roles["tutor"].model.value == "gpt-6.1-sol"
    assert "tutor" in " ".join(resolved.missing)


async def test_the_environment_key_configures_every_role_with_todays_defaults(repos) -> None:
    service, hub, _, factory = make(repos, openai_api_key=f"  {KEY}  ")
    service.load()
    config = hub.config
    assert config is not None
    assert config.tutor.connection.base_url == "https://api.openai.com/v1" and config.tutor.connection.api_key == KEY
    assert (config.tutor.model, config.authoring.model, config.transcription.model) == ("gpt-6.1-sol",) * 3
    assert config.voice is not None and config.voice.model == "gpt-realtime-2.1"
    assert config.voice.voice_transcription_model == "gpt-4o-mini-transcribe"
    assert (config.tutor.reasoning_effort, config.authoring.reasoning_effort) == (None, "medium")
    assert (config.transcription.reasoning_effort, config.voice.reasoning_effort) == ("low", "low")
    resolved = service.resolve()
    assert resolved.default.key.source == "environment" and resolved.default.key.last4 == KEY[-4:]
    assert factory.configs == [config]


async def test_the_tuned_reasoning_efforts_are_openais_alone(repos) -> None:
    """`low` and `medium` are values other providers' models may refuse: elsewhere nothing is sent by default."""
    service, hub, _, _ = make(repos, openai_base_url=GROQ, openai_api_key=GROQ_KEY)
    service.load()
    assert hub.config is not None
    assert [hub.config.authoring.reasoning_effort, hub.config.transcription.reasoning_effort] == [None, None]
    view = service.resolve().roles["authoring"].effort
    assert (view.value, view.source) == (None, "default")


async def test_a_role_on_openai_inside_another_default_keeps_the_tuned_effort(repos) -> None:
    service, hub, _, _ = make(
        repos, openai_base_url=GROQ, openai_api_key=GROQ_KEY,
        authoring_base_url="https://api.openai.com/v1", authoring_api_key=KEY,
    )
    service.load()
    assert hub.config is not None
    assert hub.config.authoring.reasoning_effort == "medium" and hub.config.transcription.reasoning_effort is None


async def test_an_efforts_chosen_for_another_provider_is_sent(repos) -> None:
    service, hub, _, _ = make(repos)
    await service.save(groq_request(), "a")  # authoring: reasoning_effort="low" was chosen
    assert hub.config is not None and hub.config.authoring.reasoning_effort == "low"
    assert hub.config.tutor.reasoning_effort is None


async def test_a_blank_environment_key_is_no_key(repos) -> None:
    service, hub, _, _ = make(repos, openai_api_key="   ")
    service.load()
    assert not hub.configured and service.resolve().default.key.source == "none"


async def test_a_keyless_server_that_is_not_openai_is_configured(repos) -> None:
    service, hub, _, _ = make(repos, openai_base_url="http://localhost:11434/v1", openai_model="qwen3:8b",
                              authoring_model="qwen3:8b", transcription_model="qwen3-vl:8b")
    service.load()
    assert hub.config is not None and hub.config.tutor.connection.api_key is None
    assert hub.config.voice is None  # voice does not follow a default connection that is not OpenAI's


async def test_the_environment_wins_field_by_field_over_the_stored_settings(repos) -> None:
    service, _, _, _ = make(repos)
    await service.save(groq_request(), "admin1")
    env, hub, _, _ = make(
        repos, cipher=service._cipher, openai_model="env-model", authoring_reasoning_effort="", ai_api_style="chat"
    )
    env.load()
    resolved = env.resolve()
    assert (resolved.roles["tutor"].model.value, resolved.roles["tutor"].model.source) == ("env-model", "environment")
    assert (resolved.roles["authoring"].model.value, resolved.roles["authoring"].model.source) == (OSS, "stored")
    assert (resolved.roles["authoring"].effort.value, resolved.roles["authoring"].effort.source) == (None, "environment")
    assert resolved.default.api_style.source == "environment" and resolved.default.base_url.source == "stored"
    assert resolved.default.base_url.value == GROQ and resolved.default.key.source == "stored"


async def test_a_stored_configuration_is_in_force_after_a_restart(repos) -> None:
    service, _, _, _ = make(repos)
    await service.save(groq_request(), "admin1")
    again, hub, _, _ = make(repos, cipher=service._cipher)
    again.load()
    assert hub.config is not None
    assert hub.config.tutor.connection.base_url == GROQ and hub.config.tutor.connection.api_key == GROQ_KEY
    assert hub.config.transcription.model == "qwen/qwen3.8-27b"
    assert hub.config.voice is None  # the default connection is not OpenAI's


async def test_a_blank_environment_model_is_not_an_override(repos) -> None:
    service, _, _, _ = make(repos, openai_api_key=KEY, openai_model="  ")
    assert service.resolve().roles["tutor"].model.source == "default"


async def test_an_unusable_environment_address_stops_startup(repos) -> None:
    service, _, _, _ = make(repos, openai_api_key=KEY, openai_base_url="ftp://nope")
    with pytest.raises(AiConfigError):
        service.load()


async def test_a_role_has_its_own_connection_from_the_environment(repos) -> None:
    service, hub, _, _ = make(
        repos, openai_api_key=KEY, transcription_base_url=GROQ + "/", transcription_api_key=GROQ_KEY,
        transcription_api_style="chat", transcription_structured_outputs="json", transcription_model="vision",
    )
    service.load()
    assert hub.config is not None
    own = hub.config.transcription.connection
    assert (own.base_url, own.api_key, own.api_style, own.structured) == (GROQ, GROQ_KEY, "chat", "json")
    assert hub.config.tutor.connection.base_url == "https://api.openai.com/v1"
    resolved = service.resolve()
    assert resolved.roles["transcription"].own is not None and not resolved.roles["tutor"].own


async def test_voice_follows_its_own_connection_or_an_openai_default(repos) -> None:
    service, hub, _, _ = make(repos, openai_base_url=GROQ, openai_api_key=GROQ_KEY, voice_base_url="https://api.openai.com/v1",
                              voice_api_key=KEY)
    service.load()
    assert hub.config is not None and hub.config.voice is not None and hub.config.voice.connection.is_openai
    off, hub2, _, _ = make(repos, openai_api_key=KEY, voice_enabled=False)
    off.load()
    assert hub2.config is not None and hub2.config.voice is None


async def test_dictation_follows_the_speech_model_on_openai_without_needing_realtime(repos) -> None:
    service, hub, _, _ = make(repos, openai_api_key=KEY, voice_enabled=False)
    service.load()
    assert hub.config is not None and hub.config.voice is None  # no Realtime...
    assert hub.config.dictation is not None and hub.config.dictation.model == "gpt-4o-mini-transcribe"
    assert hub.config.dictation.connection.is_openai and hub.dictation_available


async def test_dictation_is_not_guessed_on_a_server_that_is_not_openai(repos) -> None:
    off, hub, _, _ = make(repos, openai_base_url=GROQ, openai_api_key=GROQ_KEY, openai_model="m", authoring_model="m",
                          transcription_model="m")
    off.load()
    assert hub.config is not None and hub.config.dictation is None and not hub.dictation_available
    # ...until somebody names a speech model there, or gives the voice role a connection of its own.
    named, hub2, _, _ = make(repos, openai_base_url=GROQ, openai_api_key=GROQ_KEY, openai_model="m", authoring_model="m",
                             transcription_model="m", voice_transcription_model="whisper-large-v3-turbo")
    named.load()
    assert hub2.config is not None and hub2.config.dictation is not None
    assert (hub2.config.dictation.model, hub2.config.dictation.connection.base_url) == ("whisper-large-v3-turbo", GROQ)


async def test_dictation_can_be_turned_off(repos) -> None:
    service, hub, _, _ = make(repos, openai_api_key=KEY, dictation_enabled=False)
    service.load()
    assert hub.config is not None and hub.config.dictation is None and not hub.dictation_available


async def test_without_a_key_openai_is_not_usable_but_another_host_is(repos) -> None:
    service, hub, _, _ = make(repos, openai_model="m")
    service.load()
    assert not hub.configured


# ---- the legacy key of spec 013


async def test_a_key_stored_by_spec_013_becomes_the_default_key(repos) -> None:
    cipher = Cipher(os.urandom(32))
    repos.app_settings.put(
        LEGACY_SETTING, json.dumps({"v": 1, "ct": cipher.encrypt(KEY, context=LEGACY_CONTEXT), "last4": KEY[-4:]}), None
    )
    service, hub, _, _ = make(repos, cipher=cipher)
    service.load()
    assert hub.config is not None and hub.config.tutor.connection.api_key == KEY
    state = service.resolve().default
    assert (state.key.source, state.key.last4, state.base_url.value) == ("stored", KEY[-4:], "https://api.openai.com/v1")
    assert repos.app_settings.get(SETTING) is None  # nothing was migrated by hand


async def test_a_legacy_key_survives_a_save_that_keeps_it(repos) -> None:
    cipher = Cipher(os.urandom(32))
    repos.app_settings.put(
        LEGACY_SETTING, json.dumps({"v": 1, "ct": cipher.encrypt(KEY, context=LEGACY_CONTEXT), "last4": KEY[-4:]}), None
    )
    service, hub, _, _ = make(repos, cipher=cipher)
    service.load()
    await service.save(SaveRequest(ConnectionInput("https://api.openai.com/v1"), {"tutor": RoleInput(model="other")}), "a")
    assert hub.config is not None and hub.config.tutor.connection.api_key == KEY and hub.config.tutor.model == "other"
    assert cipher.decrypt(document(repos)["default"]["key"]["ct"], context=key_context("default")) == KEY
    assert cipher.decrypt(json.loads(repos.app_settings.get(LEGACY_SETTING))["ct"], context=LEGACY_CONTEXT) == KEY  # type: ignore[arg-type]


async def test_the_legacy_row_follows_the_default_key(repos) -> None:
    service, _, _, _ = make(repos)
    await service.save(SaveRequest(ConnectionInput("https://api.openai.com/v1", api_key=KEY)), "a")
    legacy = json.loads(repos.app_settings.get(LEGACY_SETTING))  # type: ignore[arg-type]
    assert service._cipher.decrypt(legacy["ct"], context=LEGACY_CONTEXT) == KEY  # type: ignore[union-attr]
    await service.save(groq_request(), "a")  # another host: the OpenAI key is gone, so is its mirror
    assert repos.app_settings.get(LEGACY_SETTING) is None


async def test_an_environment_key_leaves_the_legacy_row_alone(repos) -> None:
    cipher = Cipher(os.urandom(32))
    row = json.dumps({"v": 1, "ct": cipher.encrypt(KEY, context=LEGACY_CONTEXT), "last4": KEY[-4:]})
    repos.app_settings.put(LEGACY_SETTING, row, None)
    service, _, _, _ = make(repos, cipher=cipher, openai_api_key="sk-env-9999")
    await service.save(SaveRequest(ConnectionInput("https://api.openai.com/v1"), {"tutor": RoleInput(model="m")}), "a")
    assert repos.app_settings.get(LEGACY_SETTING) == row


# ------------------------------------------------------------------ save


async def test_save_encrypts_applies_and_keeps_only_the_last_four(repos, db_engine: Engine, caplog) -> None:
    service, hub, probe, factory = make(repos)
    with caplog.at_level(logging.INFO):
        resolved = await service.save(groq_request(), "admin1")
    assert resolved.config is not None and hub.config == resolved.config and len(factory.configs) == 1
    assert [(c.host, c.api_key) for c, _ in probe.calls] == [("api.groq.com", GROQ_KEY)]
    doc = document(repos)
    assert doc["v"] == 1 and doc["default"]["key"]["last4"] == GROQ_KEY[-4:] and GROQ_KEY not in json.dumps(doc)
    assert service._cipher.decrypt(doc["default"]["key"]["ct"], context=key_context("default")) == GROQ_KEY  # type: ignore[union-attr]
    assert doc["roles"]["authoring"]["reasoning_effort"] == "low"
    assert GROQ_KEY.encode() not in Path(db_engine.url.database).read_bytes()
    assert GROQ_KEY not in caplog.text and GROQ_KEY[-4:] not in caplog.text
    changed = [r for r in caplog.records if r.message == "ai_settings_changed"]
    assert len(changed) == 1 and changed[0].user_id == "admin1"  # type: ignore[attr-defined]
    assert "default.key" in changed[0].changed and "tutor.model" in changed[0].changed  # type: ignore[attr-defined]
    assert any(r.message == "ai_config_applied" for r in caplog.records)


async def test_a_change_reaches_the_next_call_without_a_restart(repos) -> None:
    service, hub, _, _ = make(repos)
    await service.save(groq_request(), "a")
    first = hub.current().tutor
    await service.save(groq_request(roles={"tutor": RoleInput(model="other-model"), "authoring": RoleInput(model=OSS),
                                           "transcription": RoleInput(model=OSS)}), "a")
    assert first.model == OSS and hub.current().tutor.model == "other-model"  # the old client finished as it was


@pytest.mark.parametrize(
    "url", ["", "   ", "ftp://x.test", "not a url", "http://", "https://user:pw@host.test/v1", "https://h.test/v1#frag",
            "https://" + "a" * 2050 + ".test"],
)
async def test_an_invalid_address_is_refused_before_anything_is_asked(repos, url) -> None:
    service, hub, probe, _ = make(repos)
    with pytest.raises(InvalidAiSettings) as raised:
        await service.save(SaveRequest(ConnectionInput(url)), "a")
    assert raised.value.fields == ["default.base_url"] and probe.calls == [] and not hub.configured
    assert repos.app_settings.get(SETTING) is None


async def test_addresses_are_normalised_and_private_hosts_are_accepted(repos) -> None:
    service, _, _, _ = make(repos)
    await service.save(SaveRequest(ConnectionInput("  http://192.168.1.20:11434/v1/  "), {"tutor": RoleInput(model="m")}), "a")
    assert document(repos)["default"]["base_url"] == "http://192.168.1.20:11434/v1"


async def test_invalid_models_keys_and_efforts_are_named(repos) -> None:
    service, _, _, _ = make(repos)
    request = SaveRequest(
        ConnectionInput(GROQ, api_key="has space"),
        {"tutor": RoleInput(model="x" * 201), "authoring": RoleInput(reasoning_effort="extreme")},
    )
    with pytest.raises(InvalidAiSettings) as raised:
        await service.save(request, "a")
    assert raised.value.fields == ["authoring.reasoning_effort", "default.api_key", "tutor.model"]


async def test_the_environment_fields_cannot_be_changed_but_can_be_echoed(repos) -> None:
    service, _, _, _ = make(repos, openai_api_key=KEY, openai_model="env-model", authoring_reasoning_effort="high")
    echoed = SaveRequest(
        ConnectionInput("https://api.openai.com/v1"),
        {"tutor": RoleInput(model="env-model"), "authoring": RoleInput(model="mine", reasoning_effort="high")},
    )
    await service.save(echoed, "a")
    doc = document(repos)
    assert "model" not in doc["roles"]["tutor"] and doc["roles"]["authoring"]["model"] == "mine"
    assert "reasoning_effort" not in doc["roles"]["authoring"]
    with pytest.raises(SettingFromEnvironment) as raised:
        await service.save(
            SaveRequest(ConnectionInput("https://api.openai.com/v1", api_key="new-key", api_style="chat"),
                        {"tutor": RoleInput(model="another"), "authoring": RoleInput(reasoning_effort="low")}),
            "a",
        )
    assert raised.value.fields == ["authoring.reasoning_effort", "default.api_key", "tutor.model"]


async def test_a_changed_address_drops_the_stored_key_and_an_unchanged_one_keeps_it(repos) -> None:
    service, hub, probe, _ = make(repos)
    await service.save(groq_request(), "a")
    probe.calls.clear()
    await service.save(groq_request(default=ConnectionInput(GROQ)), "a")  # no key sent: the stored one is kept
    assert hub.config is not None and hub.config.tutor.connection.api_key == GROQ_KEY and probe.calls == []
    with pytest.raises(AiKeyRejected):  # a new address, no new key: the key is not carried over (and is refused)
        probe.result = ProbeResult("rejected")
        await service.save(groq_request(default=ConnectionInput("https://other.example/v1")), "a")
    probe.result = ProbeResult("ok")
    await service.save(groq_request(default=ConnectionInput("https://other.example/v1")), "a")
    assert hub.config.tutor.connection.api_key is None and document(repos)["default"]["key"] is None
    assert [c.api_key for c, _ in probe.calls] == [None, None]


async def test_clear_key_removes_it(repos) -> None:
    service, hub, _, _ = make(repos)
    await service.save(groq_request(), "a")
    await service.save(groq_request(default=ConnectionInput(GROQ, clear_key=True)), "a")
    assert service.resolve().default.key.source == "none" and hub.configured  # Groq-style hosts may be keyless


async def test_a_rejected_key_changes_nothing(repos) -> None:
    service, hub, probe, _ = make(repos)
    await service.save(groq_request(), "a")
    before = repos.app_settings.get(SETTING)
    probe.result = ProbeResult("rejected")
    with pytest.raises(AiKeyRejected) as raised:
        await service.save(groq_request(default=ConnectionInput(GROQ, api_key="gsk_other_000000")), "a")
    assert raised.value.fields == ["default"] and repos.app_settings.get(SETTING) == before
    assert hub.config is not None and hub.config.tutor.connection.api_key == GROQ_KEY


async def test_an_unreachable_server_changes_nothing(repos) -> None:
    service, hub, _, _ = make(repos, probe=FakeProbe(ProbeResult("unreachable")))
    with pytest.raises(ProviderUnavailable):
        await service.save(groq_request(), "a")
    assert repos.app_settings.get(SETTING) is None and not hub.configured


async def test_a_server_that_cannot_list_models_is_accepted(repos) -> None:
    service, hub, _, _ = make(repos, probe=FakeProbe(ProbeResult("ok", limited=True)))
    await service.save(groq_request(), "a")
    assert hub.configured


async def test_a_key_needs_an_encryption_key_but_a_keyless_server_does_not(repos) -> None:
    service, hub, probe, _ = make(repos, cipher=False)
    with pytest.raises(StorageUnavailable):
        await service.save(groq_request(), "a")
    assert repos.app_settings.get(SETTING) is None and not hub.configured
    await service.save(SaveRequest(ConnectionInput("http://localhost:11434/v1"), {"tutor": RoleInput(model="m")}), "a")
    assert hub.configured and service.can_store is False


async def test_only_changed_connections_are_asked(repos) -> None:
    service, _, probe, _ = make(repos)
    await service.save(groq_request(), "a")
    probe.calls.clear()
    await service.save(groq_request(default=ConnectionInput(GROQ), roles={"tutor": RoleInput(model="x"),
                       "transcription": RoleInput(model="v", connection=ConnectionInput("http://localhost:8000/v1"))}), "a")
    assert probe.hosts == ["localhost"]


async def test_a_role_connection_is_stored_and_removed(repos) -> None:
    service, hub, _, _ = make(repos)
    request = groq_request(roles={
        "tutor": RoleInput(model=OSS),
        "authoring": RoleInput(model=OSS),
        "transcription": RoleInput(model="vision", connection=ConnectionInput(
            "https://openrouter.ai/api/v1", api_style="chat", structured="json", api_key="or-key-0000")),
    })
    await service.save(request, "a")
    assert hub.config is not None
    own = hub.config.transcription.connection
    assert (own.host, own.api_style, own.structured, own.api_key) == ("openrouter.ai", "chat", "json", "or-key-0000")
    assert hub.config.tutor.connection.host == "api.groq.com"
    assert service._cipher.decrypt(document(repos)["roles"]["transcription"]["connection"]["key"]["ct"],  # type: ignore[union-attr]
                                   context=key_context("transcription")) == "or-key-0000"
    await service.save(groq_request(), "a")  # connection None: back to the default
    assert hub.config.transcription.connection.host == "api.groq.com" and service.resolve().roles["transcription"].uses_default


async def test_a_failed_write_leaves_the_previous_configuration_in_force(repos, monkeypatch) -> None:
    service, hub, _, _ = make(repos)
    await service.save(groq_request(), "a")
    before = hub.config
    monkeypatch.setattr(repos.app_settings, "put", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full")))
    with pytest.raises(RuntimeError):
        await service.save(groq_request(roles={"tutor": RoleInput(model="x")}), "a")
    assert hub.config is before


async def test_a_configuration_that_cannot_be_built_is_not_stored(repos) -> None:
    service, hub, _, factory = make(repos)
    await service.save(groq_request(), "a")
    stored = repos.app_settings.get(SETTING)
    factory.fail = InvalidAiSettings(["tutor.api_style"])
    with pytest.raises(InvalidAiSettings):
        await service.save(groq_request(roles={"tutor": RoleInput(model="x")}), "a")
    assert repos.app_settings.get(SETTING) == stored


async def test_a_save_that_leaves_a_role_without_a_model_unconfigures(repos) -> None:
    service, hub, _, _ = make(repos)
    await service.save(SaveRequest(ConnectionInput("https://api.openai.com/v1")), "a")  # OpenAI, no key
    assert not hub.configured


# ---- unreadable state


async def test_a_tampered_key_is_unreadable_not_an_exception(repos, caplog) -> None:
    service, hub, _, _ = make(repos)
    await service.save(groq_request(), "a")
    doc = document(repos)
    doc["default"]["key"]["ct"] = doc["default"]["key"]["ct"][:-4] + "AAAA"
    repos.app_settings.put(SETTING, json.dumps(doc), None)
    with caplog.at_level(logging.WARNING):
        service.load()
    state = service.resolve().default
    assert (state.key.source, state.key.unreadable, state.key.last4) == ("none", True, None)
    assert any(r.message == "ai_key_unreadable" for r in caplog.records) and GROQ_KEY not in caplog.text
    assert hub.config is not None  # Groq may be keyless: configured, without the key


async def test_a_stored_key_without_a_cipher_is_unreadable(repos) -> None:
    service, _, _, _ = make(repos)
    await service.save(groq_request(), "a")
    other, hub, _, _ = make(repos, cipher=False)
    other.load()
    assert other.resolve().default.key.unreadable is True and hub.config is not None


async def test_a_garbled_document_is_ignored_with_a_warning(repos, caplog) -> None:
    repos.app_settings.put(SETTING, "not json", None)
    service, hub, _, _ = make(repos, openai_api_key=KEY)
    with caplog.at_level(logging.WARNING):
        service.load()
    assert hub.configured and any(r.message == "ai_settings_unreadable" for r in caplog.records)


async def test_a_document_with_an_unusable_address_is_ignored_as_a_whole(repos) -> None:
    service, _, _, _ = make(repos)
    await service.save(groq_request(), "a")
    doc = document(repos)
    doc["default"]["base_url"] = "javascript:alert(1)"
    repos.app_settings.put(SETTING, json.dumps(doc), None)
    resolved = service.resolve()
    assert resolved.default.base_url.source == "default" and resolved.default.key.source == "none"


async def test_unknown_and_mistyped_fields_are_ignored(repos) -> None:
    repos.app_settings.put(
        SETTING, json.dumps({"v": 9, "extra": 1, "default": {"base_url": GROQ, "api_style": 5}, "roles": {"tutor": "x"}}), None
    )
    service, _, _, _ = make(repos)
    state = service.resolve().default
    assert (state.base_url.value, state.api_style.value, state.api_style.source) == (GROQ, "responses", "default")


# ------------------------------------------------------------------ models and test


async def test_models_lists_what_the_connection_offers(repos) -> None:
    probe = FakeProbe(ProbeResult("ok", available=["a", "b"]))
    service, _, _, _ = make(repos, probe=probe, openai_api_key=KEY)
    listing = await service.models("tutor")
    assert (listing.status, listing.ids, listing.limited) == ("ok", ["a", "b"], False)
    assert probe.calls[0][0].api_key == KEY


async def test_models_of_an_unusable_connection_is_empty_without_asking(repos) -> None:
    probe = FakeProbe()
    service, _, _, _ = make(repos, probe=probe)  # OpenAI, no key
    listing = await service.models("default")
    assert listing.ids == [] and probe.calls == []


async def test_the_test_reports_each_role_and_each_models_visibility(repos) -> None:
    probe = FakeProbe(ProbeResult("ok", models=[ModelVisibility("gpt-6.1-sol", True), ModelVisibility("gpt-realtime-2.1", False)]))
    service, _, _, _ = make(repos, probe=probe, openai_api_key=KEY)
    service.load()
    report = await service.test()
    assert [(r.role, r.connection, r.model_visible) for r in report.roles] == [
        ("tutor", "ok", True), ("authoring", "ok", True), ("transcription", "ok", True), ("voice", "ok", False),
    ]
    assert len(probe.calls) == 1 and probe.calls[0][1] == ["gpt-6.1-sol", "gpt-realtime-2.1"]  # one connection, asked once


async def test_the_test_asks_each_distinct_connection(repos) -> None:
    probe = FakeProbe(by_host={"api.groq.com": ProbeResult("rejected")})
    service, _, _, _ = make(repos, probe=probe, openai_api_key=KEY, tutor_base_url=GROQ, tutor_model="m")
    service.load()
    report = await service.test()
    assert {r.role: r.connection for r in report.roles} == {
        "tutor": "rejected", "authoring": "ok", "transcription": "ok", "voice": "ok",
    }


async def test_the_test_leaves_out_voice_when_it_is_off(repos) -> None:
    service, _, _, _ = make(repos, openai_api_key=KEY, voice_enabled=False)
    service.load()
    assert [r.role for r in (await service.test()).roles] == ["tutor", "authoring", "transcription"]


async def test_the_test_of_a_limited_key_says_so(repos) -> None:
    service, _, _, _ = make(repos, openai_api_key=KEY, probe=FakeProbe(ProbeResult("ok", limited=True)))
    service.load()
    assert all(r.limited for r in (await service.test()).roles)


async def test_the_live_checks_are_off_unless_asked_for(repos) -> None:
    factory = PassingFactory()
    service, hub, _, _ = make(repos, factory=factory, openai_api_key=KEY)  # type: ignore[arg-type]
    service.load()
    report = await service.test()
    assert all(r.live is None for r in report.roles)
    assert hub.current().tutor.calls == []  # nothing was spent  # type: ignore[attr-defined]


async def test_the_live_checks_report_each_role(repos) -> None:
    from app.domain.errors import ProviderOutputInvalid

    factory = PassingFactory(authoring=[ProviderOutputInvalid("not a schema")])
    service, hub, _, _ = make(repos, factory=factory, openai_api_key=KEY)  # type: ignore[arg-type]
    service.load()
    report = await service.test(live=True)
    by_role = {r.role: (r.live.status, r.live.code) for r in report.roles if r.live}
    assert by_role == {
        "tutor": ("ok", None),
        "authoring": ("failed", "schema_unsupported"),
        "transcription": ("ok", None),
        "voice": ("ok", None),
    }
    assert all(r.connection == "ok" for r in report.roles)


async def test_the_live_checks_leave_voice_out_when_it_is_off(repos) -> None:
    service, _, _, _ = make(repos, factory=PassingFactory(), openai_api_key=KEY, voice_enabled=False)  # type: ignore[arg-type]
    service.load()
    assert [r.role for r in (await service.test(live=True)).roles] == ["tutor", "authoring", "transcription"]


async def test_the_test_needs_a_configuration(repos) -> None:
    service, _, _, _ = make(repos)
    with pytest.raises(AiNotConfigured):
        await service.test()


# ------------------------------------------------------------------ for scripts


def test_load_ai_config_from_the_environment_alone() -> None:
    config = load_ai_config(settings_with(openai_api_key=KEY, openai_base_url=GROQ, openai_model=OSS))
    assert config.tutor.connection.host == "api.groq.com" and config.tutor.model == OSS


def test_load_ai_config_says_what_is_missing() -> None:
    with pytest.raises(MissingApiKey) as raised:
        load_ai_config(settings_with())
    assert "OPENAI_API_KEY" in str(raised.value) and "tutor" in str(raised.value)


async def test_load_ai_config_reads_what_an_admin_stored(repos) -> None:
    service, _, _, _ = make(repos)
    await service.save(groq_request(), "a")
    config = load_ai_config(settings_with(), repos.app_settings, service._cipher)
    assert config.authoring.reasoning_effort == "low" and config.tutor.connection.api_key == GROQ_KEY
