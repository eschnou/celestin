"""Domain error hierarchy (design 4.4).

Every error carries a stable machine code and a message safe to show the learner.
The message is not text kept here: an error holds a catalog key (its code, unless it
says otherwise) and parameters, and `message(locale)` renders them in the language of the
request (spec 010 §4.2). `str(error)` is the French text, for the logs and the tests.
Internals stay in the logs (NFR 4.3.6).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.domain.locale import DEFAULT_LOCALE, Locale
from app.domain.messages import render
from app.domain.messages.issues import render_issue
from app.domain.password import MIN_LENGTH


class TutorError(Exception):
    code = "internal"
    status = 500
    params: Mapping[str, Any] = {}

    @property
    def message_key(self) -> str:
        return self.code

    def message(self, locale: Locale = DEFAULT_LOCALE) -> str:
        return render(self.message_key, locale, **self.params)

    def body(self, locale: Locale = DEFAULT_LOCALE) -> dict[str, Any]:
        """The wire shape of every error: `{code, message}`, in the request's language."""
        return {"code": self.code, "message": self.message(locale)}

    def __str__(self) -> str:
        """The French text, for the logs and the tests."""
        return self.message()


class PromptUnavailable(TutorError):
    code = "prompt_unavailable"
    status = 500


class ProviderUnavailable(TutorError):
    code = "provider_unavailable"
    status = 502


class _SameSentence:
    """A provider failure the administrator can tell apart (the test action, the logs) is, for the student,
    the same sentence as `provider_unavailable`."""

    @property
    def message_key(self) -> str:
        return ProviderUnavailable.code


class ProviderAuthRejected(_SameSentence, ProviderUnavailable):
    """The server refused the credentials."""

    code = "provider_auth_rejected"


class ProviderModelNotFound(_SameSentence, ProviderUnavailable):
    """The server does not know the model."""

    code = "provider_model_not_found"


class ProviderRejectedRequest(_SameSentence, ProviderUnavailable):
    """The server refused the request itself (a parameter, a schema, an image, tools)."""

    code = "provider_rejected_request"


class ProviderRateLimited(TutorError):
    code = "provider_rate_limited"
    status = 429


class ProviderTimeout(TutorError):
    code = "provider_timeout"
    status = 504


class VoiceDisabled(TutorError):
    code = "voice_disabled"
    status = 503


class DictationDisabled(TutorError):
    code = "dictation_disabled"
    status = 503


class InvalidAudio(TutorError):
    """A recording the server cannot use: empty, or not a kind of audio the transcription models read."""

    code = "invalid_audio"
    status = 422


class NotAuthenticated(TutorError):
    code = "not_authenticated"
    status = 401


class Forbidden(TutorError):
    code = "forbidden"
    status = 403


class InvalidCredentials(TutorError):
    code = "invalid_credentials"
    status = 401


class AccountDisabled(TutorError):
    """The password was right but an admin has not enabled the account (spec 012)."""

    code = "account_disabled"
    status = 403


class RegistrationClosed(TutorError):
    code = "registration_closed"
    status = 403


class SetupDone(TutorError):
    """Spec 013: setup ended with the first account; it never reopens."""

    code = "setup_done"
    status = 409


class SetupRequired(TutorError):
    """No administrator exists yet."""

    code = "setup_required"
    status = 409


class AiNotConfigured(TutorError):
    """No AI provider is configured (no usable connection or model for the tutor, authoring or transcription)."""

    code = "ai_not_configured"
    status = 503


class InvalidAiSettings(TutorError):
    """A setting of the AI provider is not valid. `fields` names them, for the logs."""

    code = "invalid_ai_settings"
    status = 422

    def __init__(self, fields: list[str] | None = None) -> None:
        self.fields = list(fields or [])
        super().__init__()


class AiKeyRejected(TutorError):
    """A provider rejected the API key."""

    code = "ai_key_rejected"
    status = 422

    def __init__(self, fields: list[str] | None = None) -> None:
        self.fields = list(fields or [])
        super().__init__()


class SettingFromEnvironment(TutorError):
    """A setting the request tried to change is fixed by the server's environment."""

    code = "setting_from_environment"
    status = 409

    def __init__(self, fields: list[str] | None = None) -> None:
        self.fields = list(fields or [])
        super().__init__()


class StorageUnavailable(TutorError):
    """Key storage is unavailable (no secrets directory)."""

    code = "storage_unavailable"
    status = 409


class OwnAccount(TutorError):
    """An admin acting on their own account where that would lock them out (spec 012)."""

    code = "own_account"
    status = 409


class LastAdmin(TutorError):
    """Disabling this account would leave no enabled admin."""

    code = "last_admin"
    status = 409


class WrongPassword(TutorError):
    """The current password given to change it is not the account's. Not a 401: that
    would sign the browser out."""

    code = "wrong_password"
    status = 422


class EmailTaken(TutorError):
    code = "email_taken"
    status = 409


class WeakPassword(TutorError):
    code = "weak_password"
    status = 422

    def __init__(self, reason: str) -> None:
        """`reason` is `too_short` or `personal` (domain/password.py)."""
        self.reason = reason
        self.params = {"min_length": MIN_LENGTH}
        super().__init__()

    @property
    def message_key(self) -> str:
        return f"{self.code}.{self.reason}"


class NotFound(TutorError):
    code = "not_found"
    status = 404


class RateLimited(TutorError):
    code = "rate_limited"
    status = 429


class VoiceRateLimited(RateLimited):
    code = "voice_rate_limited"


class DictationRateLimited(RateLimited):
    code = "dictation_rate_limited"


class WorkRateLimited(RateLimited):
    code = "work_rate_limited"


class CrossOrigin(TutorError):
    code = "cross_origin"
    status = 403


class InvalidSubject(TutorError):
    code = "invalid_subject"
    status = 422


class InvalidLanguage(TutorError):
    """A course language that is unknown, or that the subject is not offered in."""

    code = "invalid_language"
    status = 422


class ContentInvalid(TutorError):
    """A pack or curriculum edit that does not validate: the issues travel with it."""

    code = "content_invalid"
    status = 422

    def __init__(self, issues: list[Any]) -> None:  # list[domain.pack.ContentIssue]
        super().__init__()
        self.issues = issues

    def body(self, locale: Locale = DEFAULT_LOCALE) -> dict[str, Any]:
        return {
            **super().body(locale),
            "issues": [render_issue(i, locale) for i in self.issues],
        }


class CourseLimit(TutorError):
    code = "course_limit"
    status = 409


class ChapterLimit(TutorError):
    code = "chapter_limit"
    status = 409


class StaleVersion(TutorError):
    code = "stale_version"
    status = 409


class ChapterNotReady(TutorError):
    code = "chapter_not_ready"
    status = 409


class ChapterUnavailable(TutorError):
    code = "chapter_unavailable"
    status = 500


class SourceLength(TutorError):
    code = "source_length"
    status = 422

    def __init__(self, minimum: int, maximum: int) -> None:
        self.params = {"minimum": minimum, "maximum": maximum}
        super().__init__()


class AuthoringBusy(TutorError):
    code = "authoring_busy"
    status = 429

    def __init__(self, limit: int) -> None:
        self.params = {"limit": limit, "count": limit}  # `count` picks the plural form
        super().__init__()


class AuthoringQuota(TutorError):
    code = "authoring_quota"
    status = 429

    def __init__(self, retry_at: str) -> None:
        self.params = {"retry_at": retry_at}
        super().__init__()


class AuthoringRunning(TutorError):
    code = "authoring_running"
    status = 409


class NothingToRetry(TutorError):
    code = "nothing_to_retry"
    status = 409


class DocumentInvalid(TutorError):
    """An uploaded document that cannot become pages; the message names why.

    `reason` is the short word the logs and tests use (`unreadable`, `type`, ...);
    `key` names the catalog entry (`document.<key>`) when two refusals share a reason
    but say different things (a PDF and a photo that cannot be read)."""

    code = "document_invalid"
    status = 422

    def __init__(self, reason: str = "unreadable", *, key: str | None = None, **params: Any) -> None:
        self.reason = reason
        self.key = key or reason
        self.params = params
        super().__init__()

    @property
    def message_key(self) -> str:
        return f"document.{self.key}"


class TooManyPages(DocumentInvalid):
    code = "too_many_pages"

    def __init__(self, maximum: int) -> None:
        super().__init__("too_many_pages", maximum=maximum)

    @property
    def message_key(self) -> str:
        return self.code


class DocumentTooLarge(TutorError):
    code = "document_too_large"
    status = 413

    def __init__(self, max_bytes: int) -> None:
        self.params = {"size_mb": max_bytes // 1_048_576}
        super().__init__()


class DocumentNeeded(TutorError):
    code = "document_needed"
    status = 409


class _BilledOutput(Exception):
    """A one-shot call that answered, but not usably: the tokens it was billed for are the provider's own
    usage block (empty when it sent none), which the usage ledger and the authoring run's count read (spec 015)."""

    def __init__(self, detail: str = "", usage: dict[str, Any] | None = None) -> None:
        super().__init__(detail)
        self.usage: dict[str, Any] = usage or {}


class ProviderOutputTruncated(_BilledOutput):
    """A one-shot call stopped at its output limit (005 design 3.7)."""


class ProviderOutputInvalid(_BilledOutput):
    """A schema-constrained call returned text that is not JSON."""

    code = "provider_output_invalid"  # what the usage ledger records for it


class PromptInvalid(RuntimeError):
    """Startup only: a prompt or template file is missing or does not parse."""

    def __init__(self, path: object, detail: str) -> None:
        super().__init__(f"{path}: {detail}")


class SchemaOutdated(RuntimeError):
    """Startup only: the database is behind the migrations."""

    def __init__(self, current: str | None, expected: str | None, command: str) -> None:
        super().__init__(
            f"database schema is at revision {current or 'none'}, expected {expected or 'none'}; "
            f"run: {command}"
        )


class PayloadTooLarge(TutorError):
    code = "payload_too_large"
    status = 413


def format_validation_errors(
    exc: Any, locate: Callable[[tuple[Any, ...]], str] | None = None, root: str = "(racine)"
) -> str:
    """Pydantic errors as one line, at most five, `locate` naming the place and `root`
    the empty one (the caller's language)."""
    parts = []
    for err in exc.errors()[:5]:
        loc = tuple(err["loc"])
        where = locate(loc) if locate else ".".join(str(p) for p in loc) or root
        parts.append(f"{where}: {err['msg']}")
    return "; ".join(parts)


class ToolValidationError(Exception):
    """Never reaches HTTP: the message goes back to the model so it can correct itself."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


_BY_CODE: dict[str, type[TutorError]] = {
    cls.code: cls
    for cls in (
        ProviderUnavailable,
        ProviderRateLimited,
        ProviderTimeout,
        PromptUnavailable,
        VoiceDisabled,
        NotAuthenticated,
        Forbidden,
        InvalidCredentials,
        EmailTaken,
        NotFound,
        RateLimited,
        VoiceRateLimited,
        DictationRateLimited,
        WorkRateLimited,
        DictationDisabled,
        InvalidAudio,
        CrossOrigin,
        PayloadTooLarge,
    )
}


def from_code(code: str) -> TutorError:
    """Turn a provider-reported code back into the matching error."""
    return _BY_CODE.get(code, TutorError)()


class CurriculumInvalid(RuntimeError):
    """A curriculum file (seed and scripts input) does not validate. Carries the
    detail for the message naming the file."""

    def __init__(self, path: str, detail: str) -> None:
        super().__init__(f"{path}: {detail}")
        self.path = path
        self.detail = detail


# --- discussion mode (007 design 5) -------------------------------------------


class ConversationClosed(TutorError):
    """Replaced by a newer one, filled up, or held against content that has since
    changed. The view offers « Nouvelle conversation »."""

    code = "conversation_closed"
    status = 409

    _REASONS = ("replaced", "capped", "content_changed")

    def __init__(self, reason: str = "replaced") -> None:
        self.reason = reason
        super().__init__()

    @property
    def message_key(self) -> str:
        return f"{self.code}.{self.reason if self.reason in self._REASONS else 'replaced'}"


class ConversationFull(TutorError):
    code = "conversation_full"
    status = 409


class ConversationBusy(TutorError):
    code = "conversation_busy"
    status = 409


class EmptyTurnExpected(TutorError):
    code = "empty_conversation_expected"
    status = 422


class DiscussionQuota(TutorError):
    code = "discussion_quota"
    status = 429

    def __init__(self, maximum: int) -> None:
        self.params = {"maximum": maximum}
        super().__init__()
