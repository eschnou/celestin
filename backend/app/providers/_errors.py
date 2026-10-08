"""SDK exceptions → domain errors, shared by the adapters (spec 014 §3.6).

Authentication, unknown model and refused request are told apart (the test action and the logs need to),
and all three are `ProviderUnavailable`s, so every existing handler keeps working.

`classify` (spec 016 §3.4) says *why* a call failed, for the log: the exception's class, a fixed reason
token, the HTTP status and the provider's own error code and request id. It reads an exception's message
for one test (does it mention `stream`?) and returns none of it.
"""

from __future__ import annotations

import openai

from app.domain.errors import (
    CallDiagnostics,
    ProviderAuthRejected,
    ProviderModelNotFound,
    ProviderOutputInvalid,
    ProviderOutputTruncated,
    ProviderRateLimited,
    ProviderRejectedRequest,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.providers.base import StreamBroken, StreamTimeout

MAX_TOKEN_CHARS = 64  # a provider's error code or request id: short strings, cut so a log line stays small

_BROKEN_CODES: dict[str, type[Exception]] = {
    ProviderRateLimited.code: ProviderRateLimited,
    ProviderTimeout.code: ProviderTimeout,
}


def translate(exc: Exception) -> Exception:
    if isinstance(exc, StreamTimeout):
        return ProviderTimeout()
    if isinstance(exc, StreamBroken):
        return _BROKEN_CODES.get(exc.code, ProviderUnavailable)()
    if isinstance(exc, openai.RateLimitError):
        return ProviderRateLimited()
    if isinstance(exc, (openai.APITimeoutError, TimeoutError)):
        return ProviderTimeout()
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return ProviderAuthRejected()
    if isinstance(exc, openai.NotFoundError):
        return ProviderModelNotFound()
    if isinstance(exc, (openai.BadRequestError, openai.UnprocessableEntityError)):
        return ProviderRejectedRequest()
    if isinstance(exc, openai.APIError):
        return ProviderUnavailable()
    return exc


def _short(value: object) -> str | None:
    return value[:MAX_TOKEN_CHARS] if isinstance(value, str) and value else None


def classify(exc: BaseException) -> CallDiagnostics:
    """Why `exc` is a failure, as far as the exception says: the call's own numbers (elapsed, idle, characters)
    are added by the caller that measured them."""
    error_class = type(exc).__name__
    if isinstance(exc, (StreamTimeout, StreamBroken)):
        return CallDiagnostics(error_class, exc.reason, None)
    if isinstance(exc, ProviderOutputTruncated):
        return CallDiagnostics(error_class, "truncated", None)
    if isinstance(exc, ProviderOutputInvalid):
        return CallDiagnostics(error_class, "invalid_output", None)
    if isinstance(exc, openai.APITimeoutError):  # before APIConnectionError, which it extends
        return CallDiagnostics(error_class, "transport_timeout", None)
    if isinstance(exc, openai.APIConnectionError):
        return CallDiagnostics(error_class, "connection", None)
    if isinstance(exc, openai.APIStatusError):
        reason = "http_status"
        if isinstance(exc, openai.BadRequestError) and "stream" in str(exc).lower():
            reason = "stream_unsupported"
        return CallDiagnostics(
            error_class,
            reason,
            status_code=exc.status_code,
            provider_code=_short(getattr(exc, "code", None)),
            request_id=_short(getattr(exc, "request_id", None)),
        )
    return CallDiagnostics(error_class, "other", None)
