"""The AI provider settings an administrator edits (spec 014 §3.3), replacing spec 013's OpenAI key service.

`Resolver` (ai_resolution.py) says which configuration is in force. This service loads it into the provider
hub at startup, saves an administrator's edit, lists a server's models and tests the configuration.

A save is atomic from the outside: it is validated, the connections whose address or key changed are asked
whether they work, the clients are built, and only then is the document written and the hub swapped. Any
failure leaves the previous configuration in force. Whatever happens, no key is returned, logged or put in
an error: callers get `last4` at most.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from starlette.concurrency import run_in_threadpool

from app.config import MissingApiKey, Settings
from app.db.repositories import AppSettingsRepository
from app.domain.ai_config import (
    MAX_KEY_CHARS,
    MAX_MODEL_CHARS,
    ROLES,
    AiConfig,
    ApiStyle,
    Connection,
    LiveCode,
    Role,
    StructuredMode,
    normalise_base_url,
)
from app.domain.errors import (
    AiKeyRejected,
    AiNotConfigured,
    InvalidAiSettings,
    ProviderUnavailable,
    SettingFromEnvironment,
    StorageUnavailable,
)
from app.providers.base import ConnectionProbe, ProbeResult
from app.providers.hub import ProviderHub
from app.services.ai_resolution import (
    EFFORTS,
    LEGACY_CONTEXT,
    LEGACY_SETTING,
    SETTING,
    ConnectionState,
    Resolved,
    Resolver,
    Slot,
    Stored,
    StoredConnection,
    StoredKey,
    StoredRole,
    dump_stored,
    key_context,
)
from app.services.ai_test import run_live_checks
from app.services.cipher import Cipher

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ what an administrator submits


@dataclass(frozen=True)
class ConnectionInput:
    base_url: str
    api_style: ApiStyle = "responses"
    structured: StructuredMode = "schema"
    api_key: str | None = None
    clear_key: bool = False


@dataclass(frozen=True)
class RoleInput:
    model: str | None = None
    reasoning_effort: str | None = None  # None: unset; "": not sent
    voice_transcription_model: str | None = None
    connection: ConnectionInput | None = None


@dataclass(frozen=True)
class SaveRequest:
    default: ConnectionInput
    roles: dict[Role, RoleInput] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelListing:
    status: Literal["ok", "rejected", "unreachable"]
    ids: list[str]
    limited: bool


# ------------------------------------------------------------------ the test report


@dataclass(frozen=True)
class LiveResult:
    status: Literal["ok", "failed"]
    code: LiveCode | None = None


@dataclass(frozen=True)
class RoleTest:
    role: Role
    connection: Literal["ok", "rejected", "unreachable"]
    limited: bool
    model_visible: bool | None
    live: LiveResult | None = None


@dataclass(frozen=True)
class AiTestReport:
    __test__ = False  # not a pytest class, whatever its name says

    roles: list[RoleTest]


# ------------------------------------------------------------------ the service


class AiSettingsService:
    def __init__(
        self,
        repo: AppSettingsRepository,
        cipher: Cipher | None,
        hub: ProviderHub,
        probe: ConnectionProbe,
        settings: Settings,
    ) -> None:
        self._repo = repo
        self._cipher = cipher
        self._hub = hub
        self._probe = probe
        self._settings = settings
        self._resolver = Resolver(settings, repo, cipher)
        self._lock = asyncio.Lock()  # one save at a time

    @property
    def can_store(self) -> bool:
        return self._cipher is not None

    # ---- what is in force

    def resolve(self) -> Resolved:
        return self._resolver.resolve()

    def load(self) -> None:
        """At startup: put the configuration in force into the hub."""
        resolved = self.resolve()
        for slot, state in (("default", resolved.default), *((r, s.own) for r, s in resolved.roles.items())):
            if state is not None and state.key.unreadable:
                log.warning("ai_key_unreadable", extra={"slot": slot})  # never why, in detail
        self._hub.apply(resolved.config)
        if resolved.config is None:
            log.warning("ai_not_configured", extra={"missing": resolved.missing})
        else:
            log.info("ai_config_applied", extra={"roles": resolved.config.describe()})

    # ---- what an administrator can do

    async def save(self, request: SaveRequest, actor_id: str) -> Resolved:
        async with self._lock:
            before = await run_in_threadpool(self.resolve)
            stored, to_probe = self._build(request, before)
            candidate = Resolver(self._settings, _Memory(dump_stored(stored)), self._cipher).resolve()
            await self._probe_changed(to_probe)
            clients = await run_in_threadpool(self._hub.build, candidate.config)
            await run_in_threadpool(self._write, stored, candidate, actor_id)
            self._hub.install(clients)
        changed = _changed_fields(before, candidate)
        log.info("ai_settings_changed", extra={"user_id": actor_id, "changed": changed})
        if candidate.config is not None:
            log.info("ai_config_applied", extra={"roles": candidate.config.describe()})
        return candidate

    def _write(self, stored: Stored, candidate: Resolved, actor_id: str) -> None:
        self._repo.put(SETTING, dump_stored(stored), actor_id)
        # Rolling back to spec 013's code must still find the key: the legacy row mirrors the default
        # connection's stored key while that connection is OpenAI's, and is removed otherwise.
        default = candidate.default
        if default.key.source == "stored" and default.key.value and default.to_connection().is_openai and self._cipher:
            document = {
                "v": 1,
                "ct": self._cipher.encrypt(default.key.value, context=LEGACY_CONTEXT),
                "last4": default.key.value[-4:],
            }
            self._repo.put(LEGACY_SETTING, json.dumps(document), actor_id)
        elif default.key.source != "environment":
            self._repo.delete(LEGACY_SETTING)

    def _build(
        self, request: SaveRequest, before: Resolved
    ) -> tuple[Stored, list[tuple[Slot, Connection]]]:
        """The document to store from what was submitted, validated; the connections to ask about."""
        locked: list[str] = []
        invalid: list[str] = []
        to_probe: list[tuple[Slot, Connection]] = []

        def connection(slot: Slot, given: ConnectionInput, previous: ConnectionState | None, prefix: str) -> StoredConnection:
            """One connection's stored form. Fields the environment sets are not stored."""
            out = StoredConnection()
            try:
                url = normalise_base_url(given.base_url, f"{prefix}.base_url")
            except InvalidAiSettings as exc:
                invalid.extend(exc.fields)
                return out
            if previous is not None and previous.base_url.source == "environment":
                if url != previous.base_url.value:
                    locked.append(f"{prefix}.base_url")
            else:
                out.base_url = url
            for name, value, prior in (
                ("api_style", given.api_style, previous.api_style if previous else None),
                ("structured", given.structured, previous.structured if previous else None),
            ):
                if prior is not None and prior.source == "environment":
                    if value != prior.value:
                        locked.append(f"{prefix}.{name}")
                else:
                    setattr(out, name, value)
            # The key: a new one, the stored one kept, or none. A new address drops the old key: it was
            # given for another server and must not be sent to this one.
            prior_key = previous.key if previous else None
            new_key = (given.api_key or "").strip() or None
            if prior_key is not None and prior_key.source == "environment":
                if new_key or given.clear_key:
                    locked.append(f"{prefix}.api_key")
                keep_plain = None
            elif new_key:
                if len(new_key) > MAX_KEY_CHARS or any(c.isspace() for c in new_key):
                    invalid.append(f"{prefix}.api_key")
                    return out
                keep_plain = new_key
            elif given.clear_key:
                keep_plain = None
            elif prior_key is not None and prior_key.value and previous and url == previous.base_url.value:
                keep_plain = prior_key.value
            else:
                keep_plain = None
            if keep_plain:
                if self._cipher is None:
                    raise StorageUnavailable()
                out.key = StoredKey(self._cipher.encrypt(keep_plain, context=key_context(slot)), keep_plain[-4:])
            if previous is None or url != previous.base_url.value or new_key:
                # An environment key is the one in force; it is what the new address is asked with.
                asked_with = keep_plain or (prior_key.value if prior_key and prior_key.source == "environment" else None)
                to_probe.append((slot, Connection(url, asked_with, given.api_style, given.structured)))
            return out

        stored = Stored()
        stored.default = connection("default", request.default, before.default, "default")

        for role in ROLES:
            given = request.roles.get(role) or RoleInput()
            state = before.roles[role]
            entry = StoredRole()
            model = (given.model or "").strip()
            if len(model) > MAX_MODEL_CHARS:
                invalid.append(f"{role}.model")
            elif state.model.source == "environment":
                if model and model != state.model.value:
                    locked.append(f"{role}.model")
            elif model:
                entry.model = model
            if given.reasoning_effort is not None and given.reasoning_effort not in ("", *EFFORTS):
                invalid.append(f"{role}.reasoning_effort")
            elif state.effort.source == "environment":
                if given.reasoning_effort is not None and (given.reasoning_effort or None) != state.effort.value:
                    locked.append(f"{role}.reasoning_effort")
            else:
                entry.reasoning_effort = given.reasoning_effort
            if role == "voice":
                vm = (given.voice_transcription_model or "").strip()
                prior = state.voice_transcription_model
                if len(vm) > MAX_MODEL_CHARS:
                    invalid.append("voice.transcription_model")
                elif prior is not None and prior.source == "environment":
                    if vm and vm != prior.value:
                        locked.append("voice.transcription_model")
                elif vm:
                    entry.voice_transcription_model = vm
            if given.connection is not None:
                entry.connection = connection(role, given.connection, state.own, role)
            stored.roles[role] = entry

        if invalid:
            raise InvalidAiSettings(sorted(set(invalid)))
        if locked:
            raise SettingFromEnvironment(sorted(set(locked)))
        return stored, to_probe

    async def _probe_changed(self, connections: Sequence[tuple[Slot, Connection]]) -> None:
        """Ask each new or changed connection whether it works, together. `rejected` and `unreachable` stop
        the save; `limited` (cannot list models) does not."""
        if not connections:
            return
        results = await asyncio.gather(*(self._probe.check(c) for _, c in connections))
        for (slot, _), result in zip(connections, results, strict=True):
            if result.status == "rejected":
                raise AiKeyRejected([slot])
            if result.status == "unreachable":
                raise ProviderUnavailable()

    async def models(self, slot: Slot) -> ModelListing:
        """The model ids a slot's connection lists, as suggestions. Empty when it cannot say."""
        resolved = await run_in_threadpool(self.resolve)
        state = resolved.default if slot == "default" else resolved.roles[slot].connection
        connection = state.to_connection()
        if not connection.usable:
            return ModelListing("ok", [], True)
        result = await self._probe.check(connection)
        return ModelListing(result.status, result.available, result.limited)

    async def test(self, live: bool = False) -> AiTestReport:
        """Ask each distinct connection of the configuration in force about it and about the models the
        roles use. `live` runs the checks of spec 014 §3.9 on top: one tiny real call per role, which costs
        a few dozen tokens."""
        clients = self._hub.clients  # one read: the checks and the report are about the same configuration
        if clients is None:
            raise AiNotConfigured()
        config = clients.config
        by_connection: dict[Connection, list[tuple[Role, str]]] = {}
        for rc in config.roles():
            by_connection.setdefault(rc.connection, []).append((rc.role, rc.model))

        async def probe_all() -> dict[Connection, ProbeResult]:
            results = await asyncio.gather(
                *(self._probe.check(c, list(dict.fromkeys(m for _, m in wanted))) for c, wanted in by_connection.items())
            )
            return dict(zip(by_connection, results, strict=True))

        async def live_all() -> dict[Role, LiveCode | None]:
            return await run_live_checks(clients) if live else {}

        # Independent of each other, and the live checks are the slow part: ask both at once.
        probed, checked = await asyncio.gather(probe_all(), live_all())
        roles: list[RoleTest] = []
        for rc in config.roles():
            result = probed[rc.connection]
            seen = {item.model: item.visible for item in result.models}
            live_result = _live_result(checked, rc.role)
            roles.append(
                RoleTest(
                    rc.role,
                    result.status,
                    result.limited,
                    seen.get(rc.model),
                    live_result,
                )
            )
        return AiTestReport(roles)


def _live_result(checked: dict[Role, LiveCode | None], role: Role) -> LiveResult | None:
    if role not in checked:
        return None
    code = checked[role]
    return LiveResult("ok") if code is None else LiveResult("failed", code)


class _Memory:
    """A read-only stand-in for the repository: resolves a document that is not stored yet."""

    def __init__(self, document: str) -> None:
        self._document = document

    def get(self, key: str) -> str | None:
        return self._document if key == SETTING else None


def _changed_fields(before: Resolved, after: Resolved) -> list[str]:
    """Names of what the save changed, never values."""
    changed: list[str] = []
    pairs = [("default", before.default, after.default)] + [
        (r, before.roles[r].own, after.roles[r].own) for r in ROLES
    ]
    for name, b, a in pairs:
        if (b is None) != (a is None):
            changed.append(f"{name}.connection")
        elif b is not None and a is not None:
            for attr in ("base_url", "api_style", "structured"):
                if getattr(b, attr).value != getattr(a, attr).value:
                    changed.append(f"{name}.{attr}")
            if (b.key.last4, b.key.source) != (a.key.last4, a.key.source):
                changed.append(f"{name}.key")
    for role in ROLES:
        b, a = before.roles[role], after.roles[role]
        if b.model.value != a.model.value:
            changed.append(f"{role}.model")
        if b.effort.value != a.effort.value:
            changed.append(f"{role}.reasoning_effort")
    return changed


def load_ai_config(settings: Settings, repo: AppSettingsRepository | None = None, cipher: Cipher | None = None) -> AiConfig:
    """For the scripts: the configuration from the environment and, when a repository is given, from what an
    administrator stored. Raises `MissingApiKey` naming what is missing."""
    resolved = Resolver(settings, repo, cipher).resolve()
    if resolved.config is None:
        raise MissingApiKey(
            "No AI provider is configured: " + "; ".join(resolved.missing)
            + ". Set OPENAI_API_KEY (and OPENAI_BASE_URL, OPENAI_MODEL for another provider) in .env, "
            "or configure it in the settings screen and point DATABASE_URL at that database."
        )
    return resolved.config
