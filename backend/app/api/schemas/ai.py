"""The AI provider settings on the wire (spec 014 §3.8). A key is never in a response: a source and its last
four characters at most."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.ai_config import ApiStyle, Effort, LiveCode, Role, StructuredMode
from app.services.ai_resolution import ConnectionState, FieldValue, KeySource, Resolved, RoleState, Source
from app.services.ai_settings import ConnectionInput, RoleInput, SaveRequest


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- what the screen shows


class TextFieldDTO(_Out):
    value: str | None
    source: Source


class StyleFieldDTO(_Out):
    value: ApiStyle
    source: Source


class StructuredFieldDTO(_Out):
    value: StructuredMode
    source: Source


class EffortFieldDTO(_Out):
    value: Effort | None
    source: Source


class KeyDTO(_Out):
    source: KeySource
    last4: str | None
    unreadable: bool


class ConnectionDTO(_Out):
    base_url: TextFieldDTO
    api_style: StyleFieldDTO
    structured: StructuredFieldDTO
    key: KeyDTO


class RoleDTO(_Out):
    model: TextFieldDTO
    reasoning_effort: EffortFieldDTO
    voice_transcription_model: TextFieldDTO | None
    own_connection: ConnectionDTO | None
    uses_default: bool
    resolved: bool


class AiSettingsDTO(_Out):
    can_store: bool
    configured: bool
    voice_available: bool
    default: ConnectionDTO
    roles: dict[Role, RoleDTO]


def _field(f: FieldValue) -> dict[str, object]:
    return {"value": f.value, "source": f.source}


def _connection(c: ConnectionState) -> ConnectionDTO:
    k = c.key
    return ConnectionDTO(
        base_url=TextFieldDTO(**_field(c.base_url)),
        api_style=StyleFieldDTO(**_field(c.api_style)),
        structured=StructuredFieldDTO(**_field(c.structured)),
        key=KeyDTO(source=k.source, last4=k.last4, unreadable=k.unreadable),
    )


def _role(r: RoleState) -> RoleDTO:
    return RoleDTO(
        model=TextFieldDTO(**_field(r.model)),
        reasoning_effort=EffortFieldDTO(**_field(r.effort)),
        voice_transcription_model=TextFieldDTO(**_field(r.voice_transcription_model)) if r.voice_transcription_model else None,
        own_connection=_connection(r.own) if r.own else None,
        uses_default=r.uses_default,
        resolved=r.resolved,
    )


def settings_view(resolved: Resolved, *, can_store: bool) -> AiSettingsDTO:
    config = resolved.config
    return AiSettingsDTO(
        can_store=can_store,
        configured=config is not None,
        voice_available=bool(config and config.voice),
        default=_connection(resolved.default),
        roles={name: _role(state) for name, state in resolved.roles.items()},
    )


# ---------------------------------------------------------------- what the screen sends


class ConnectionInputDTO(_Model):
    base_url: Annotated[str, Field(max_length=2048)]
    api_style: ApiStyle = "responses"
    structured: StructuredMode = "schema"
    # Its length and shape are the service's to judge: a schema refusal would echo the key back in its body.
    api_key: str | None = None
    clear_key: bool = False

    def to_input(self) -> ConnectionInput:
        return ConnectionInput(self.base_url, self.api_style, self.structured, self.api_key, self.clear_key)


class RoleInputDTO(_Model):
    model: Annotated[str, Field(max_length=1024)] | None = None
    reasoning_effort: Literal["", "low", "medium", "high"] | None = None
    voice_transcription_model: Annotated[str, Field(max_length=1024)] | None = None
    connection: ConnectionInputDTO | None = None

    def to_input(self) -> RoleInput:
        return RoleInput(
            self.model,
            self.reasoning_effort,
            self.voice_transcription_model,
            self.connection.to_input() if self.connection else None,
        )


class SaveAiSettingsRequest(_Model):
    default: ConnectionInputDTO
    roles: dict[Role, RoleInputDTO] = Field(default_factory=dict)

    def to_request(self) -> SaveRequest:
        return SaveRequest(self.default.to_input(), {name: item.to_input() for name, item in self.roles.items()})


class ModelListingDTO(_Out):
    status: Literal["ok", "rejected", "unreachable"]
    ids: list[str]
    limited: bool


class TestRequest(_Model):
    live: bool = False


class LiveResultDTO(_Out):
    status: Literal["ok", "failed"]
    code: LiveCode | None


class RoleTestDTO(_Out):
    role: Role
    connection: Literal["ok", "rejected", "unreachable"]
    limited: bool
    model_visible: bool | None
    live: LiveResultDTO | None


class AiTestDTO(_Out):
    roles: list[RoleTestDTO]

