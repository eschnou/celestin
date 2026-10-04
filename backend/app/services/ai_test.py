"""The live checks of the test action (spec 014 §3.9): one tiny real call per role, through the clients the
hub holds, so the report is about exactly what a student's request will use.

Each check asks for what the application needs of that role: a tutor must stream and call a tool, authoring
must follow a schema, transcription must read an image, voice must be able to mint a session. A check
costs a few dozen tokens. Nothing here forwards or logs provider text: a failure is a code, and the code is
all the administrator needs (the interface words the remedy).
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import time
from functools import lru_cache
from pydantic import BaseModel, ValidationError

from app.domain.ai_config import LiveCode, Role
from app.domain.errors import (
    ProviderAuthRejected,
    ProviderModelNotFound,
    ProviderOutputInvalid,
    ProviderOutputTruncated,
    ProviderRejectedRequest,
    ProviderTimeout,
    ProviderUnavailable,
    VoiceDisabled,
)
from app.providers.base import Failed, ToolCallRequested
from app.providers.hub import Clients
from app.services.tools import registry

log = logging.getLogger(__name__)

CHECK_TIMEOUT_S = 45.0
EXPECTED_NUMBER = "42"


class Ping(BaseModel):
    ok: bool
    word: str


class CheckFailed(Exception):
    """A check that ran and found the model unable. `code` is what the administrator is told."""

    def __init__(self, code: LiveCode) -> None:
        super().__init__(code)
        self.code = code


@lru_cache(maxsize=1)
def number_image_data_url() -> str:
    """A small PNG of the number 42, drawn here: nothing to download, nothing to store."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (180, 80), "white")
    ImageDraw.Draw(image).text((20, 10), EXPECTED_NUMBER, fill="black", font=ImageFont.load_default(size=56))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


# ------------------------------------------------------------------ the four checks


async def check_tutor(clients: Clients) -> None:
    """Stream one request, with the application's own tools, that must end in a valid call of the board tool.

    The real declarations, not a toy tool: the board's card is the hardest thing the tutor asks of a model (a
    nested union), and a model that cannot call it cannot teach, whatever else it can do."""
    items = [
        {"role": "developer", "content": [{"type": "input_text", "text": "This is a test. Use the tools you are given."}]},
        {"role": "user", "content": "Display a title card on the board for a chapter called « Test »."},
    ]
    refused = None
    async with clients.tutor.stream(input=items, tools=registry.declarations("parcours", "fr")) as stream:
        async for event in stream:
            if isinstance(event, ToolCallRequested):
                if event.name == "display_board" and registry.arguments_valid(event.name, event.arguments_json):
                    return  # the stream is closed on the way out: the rest of the answer is not wanted
                raise CheckFailed("tool_arguments")
            if isinstance(event, Failed):
                # A server that checks tool arguments itself refuses a malformed call, mid-stream; the failure
                # may come in two events, the second one saying why.
                refused = "tool_arguments" if (refused == "tool_arguments" or "tool" in event.message.lower()) else "other"
    raise CheckFailed(refused or "no_tool_calls")


async def check_authoring(clients: Clients) -> None:
    """One answer that must follow a schema (or, in JSON mode, be a JSON object that does)."""
    result = await clients.authoring.complete(
        role="authoring",
        instructions=["This is a test. Answer with the JSON object asked for, and nothing else."],
        input=[{"role": "user", "content": 'Return ok set to true and word set to "bonjour".'}],
        schema=Ping,
        schema_name="ping",
        max_output_tokens=2000,
    )
    try:
        Ping.model_validate(result.data)
    except ValidationError as exc:
        raise CheckFailed("schema_unsupported") from exc


async def check_transcription(clients: Clients) -> None:
    """An image that must be read."""
    result = await clients.transcription.complete(
        role="transcription",
        instructions=["This is a test. Read the image."],
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "What number is written in this image? Answer with the digits only."},
                    {"type": "input_image", "image_url": number_image_data_url(), "detail": "low"},
                ],
            }
        ],
        max_output_tokens=2000,
    )
    if EXPECTED_NUMBER not in result.text:
        raise CheckFailed("no_image_input")


async def check_voice(clients: Clients) -> None:
    """A Realtime client secret must be mintable (no audio, no session is used)."""
    voice = clients.config.voice
    if clients.realtime is None or voice is None:
        raise VoiceDisabled()
    await clients.realtime.create_client_secret(session={"type": "realtime", "model": voice.model}, ttl_s=10)


CHECKS = {
    "tutor": check_tutor,
    "authoring": check_authoring,
    "transcription": check_transcription,
    "voice": check_voice,
}

# What a request the server refused means, per role.
_REFUSED_AS: dict[str, LiveCode] = {
    "tutor": "no_tool_calls",
    "authoring": "schema_unsupported",
    "transcription": "no_image_input",
    "voice": "other",
}


def classify(role: Role, error: BaseException) -> LiveCode:
    if isinstance(error, CheckFailed):
        return error.code
    if isinstance(error, ProviderAuthRejected):
        return "rejected"
    if isinstance(error, ProviderModelNotFound):
        return "model_not_found"
    if isinstance(error, ProviderRejectedRequest):
        return _REFUSED_AS[role]
    if isinstance(error, ProviderOutputInvalid):
        return "schema_unsupported"
    if isinstance(error, ProviderOutputTruncated):
        return "other"
    if isinstance(error, (ProviderTimeout, ProviderUnavailable, TimeoutError)):
        return "unreachable"
    return "other"


async def run_check(role: Role, clients: Clients) -> LiveCode | None:
    """What one role's check found: `None` when it passed. Bounded in time, never raising, and logging only
    the outcome."""
    started = time.monotonic()
    code: LiveCode | None = None
    try:
        await asyncio.wait_for(CHECKS[role](clients), CHECK_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 - a check reports, it does not raise
        code = classify(role, exc)
    log.info(
        "ai_test",
        extra={"role": role, "live": code or "ok", "ms": round((time.monotonic() - started) * 1000)},
    )
    return code


async def run_live_checks(clients: Clients) -> dict[Role, LiveCode | None]:
    """Every role the configuration has, together."""
    roles: list[Role] = [rc.role for rc in clients.config.roles()]
    results = await asyncio.gather(*(run_check(role, clients) for role in roles))
    return dict(zip(roles, results, strict=True))
