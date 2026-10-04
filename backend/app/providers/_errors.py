"""SDK exceptions → domain errors, shared by the adapters (spec 014 §3.6).

Authentication, unknown model and refused request are told apart (the test action and the logs need to),
and all three are `ProviderUnavailable`s, so every existing handler keeps working.
"""

from __future__ import annotations

import openai

from app.domain.errors import (
    ProviderAuthRejected,
    ProviderModelNotFound,
    ProviderRateLimited,
    ProviderRejectedRequest,
    ProviderTimeout,
    ProviderUnavailable,
)


def translate(exc: Exception) -> Exception:
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
