"""Application settings, read once from the repo-root .env."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.domain.ai_config import OPENAI_BASE_URL, ApiStyle, StructuredMode
from app.domain.user import RegistrationMode

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


# The shortest SESSION_SECRET taken from the environment (a generated one is 64 characters).
MIN_SESSION_SECRET_CHARS = 16

# A reasoning effort: empty means the parameter is not sent (a model that does not reason refuses it).
EffortSetting = Literal["", "low", "medium", "high"]


class MissingApiKey(RuntimeError):
    """Raised at startup when no provider credential is configured."""


class MissingSessionSecret(RuntimeError):
    """Raised at startup when sessions cannot be signed."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Either location works; backend/.env wins if both exist.
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # The AI provider (spec 014). The default connection and the tutor's model keep their OpenAI names; what
    # an administrator stores in the interface fills whatever the environment leaves unset
    # (`Settings.model_fields_set` says which fields the environment did set).
    openai_api_key: str = ""
    openai_base_url: str = OPENAI_BASE_URL
    ai_api_style: ApiStyle = "responses"
    ai_structured_outputs: StructuredMode = "schema"
    openai_model: str = "gpt-6.1-sol"
    tutor_reasoning_effort: EffortSetting = ""
    # A role's own connection, from the environment: set `<ROLE>_BASE_URL` and the role leaves the default one.
    tutor_base_url: str = ""
    tutor_api_key: str = ""
    tutor_api_style: ApiStyle = "responses"
    tutor_structured_outputs: StructuredMode = "schema"
    authoring_base_url: str = ""
    authoring_api_key: str = ""
    authoring_api_style: ApiStyle = "responses"
    authoring_structured_outputs: StructuredMode = "schema"
    transcription_base_url: str = ""
    transcription_api_key: str = ""
    transcription_api_style: ApiStyle = "responses"
    transcription_structured_outputs: StructuredMode = "schema"
    voice_base_url: str = ""
    voice_api_key: str = ""
    voice_api_style: ApiStyle = "responses"
    voice_structured_outputs: StructuredMode = "schema"

    # Accounts (004 design 3.13). The session secret keys the token hash: a leaked
    # database alone cannot mint a session.
    database_url: str = "sqlite:///./data/celestin.db"
    session_secret: str = ""
    # Where the generated secrets live (spec 013 R4): `session_secret` and `encryption_key`,
    # created on first boot. Unset: the secrets come from the environment, as they always did.
    secrets_dir: Path | None = None
    # Backups of the SQLite file kept by `scripts.migrate` before a pending migration (spec 013 R9).
    migration_backups_kept: Annotated[int, Field(ge=1)] = 5
    session_idle_days: Annotated[int, Field(ge=1, le=365)] = 30
    session_absolute_days: Annotated[int, Field(ge=1, le=730)] = 90
    # `auto`: Secure when the request arrived over HTTPS (the image's default), so sign-in
    # works on plain http://localhost and LAN addresses too (spec 013 R8).
    cookie_secure: bool | Literal["auto"] = True
    argon2_memory_kib: Annotated[int, Field(ge=8192)] = 19456
    argon2_time: Annotated[int, Field(ge=1)] = 2
    argon2_parallelism: Annotated[int, Field(ge=1)] = 1
    auth_attempts_per_window: Annotated[int, Field(ge=1)] = 10
    auth_window_s: Annotated[int, Field(ge=10)] = 900
    # Who may create an account (spec 012): `open`, `closed` (no sign-up at all) or
    # `verification` (sign-up, but no sign-in until an admin enables the account).
    registration_mode: RegistrationMode = "open"

    # Tutor prompt, subject prompts, pack templates and authoring prompts (005 design 3.4).
    prompts_dir: Path = BACKEND_DIR / "prompts"

    max_tool_rounds: int = 6
    max_message_chars: int = 4000
    # An abuse guard, not context management: one exchange adds three to five
    # entries, so a long session must stay well clear of this. Fitting the
    # transcript to the model is history_token_budget's job, and it trims rather
    # than rejects.
    max_history_entries: int = 400
    history_token_budget: int = 30_000
    # 100 000 characters of French with math symbols is well over the old 256 KiB.
    max_body_bytes: int = 1_048_576

    # Discussion mode (007 design 4.4). A conversation is stored whole, so it is
    # capped: whichever limit is crossed first closes it and the student starts a
    # new one. Trimming for the model stays `history_token_budget`'s job.
    discussion_max_entries: Annotated[int, Field(ge=1)] = 400
    discussion_max_chars: Annotated[int, Field(ge=1000)] = 200_000
    discussion_conversations_per_day: Annotated[int, Field(ge=1)] = 30

    # Courses and chapters (005 design 3.13).
    max_courses_per_student: Annotated[int, Field(ge=1)] = 30
    max_chapters_per_course: Annotated[int, Field(ge=1, le=40)] = 40
    chapter_text_min_chars: Annotated[int, Field(ge=1)] = 300
    chapter_text_max_chars: Annotated[int, Field(ge=1)] = 100_000
    pack_max_chars: Annotated[int, Field(ge=1000)] = 60_000

    # NoDecode: the value is a comma-separated list, not JSON.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    log_level: str = "INFO"
    debug_log_prompts: bool = False
    request_timeout_s: float = 120.0
    # The learner's clock, for the greeting and the state message. Never in the
    # cached prefix.
    timezone: str = "Europe/Brussels"

    # Authoring (005 design 3.13). Prices are USD per million tokens, for the cost
    # estimate stored with each run.
    authoring_model: str = "gpt-6.1-sol"
    authoring_reasoning_effort: EffortSetting = "medium"
    authoring_max_output_tokens: Annotated[int, Field(ge=1000)] = 32_000
    authoring_max_repairs: Annotated[int, Field(ge=0, le=5)] = 2
    authoring_timeout_s: Annotated[float, Field(ge=10)] = 900.0
    authoring_call_timeout_s: Annotated[float, Field(ge=10)] = 300.0
    authoring_concurrent_per_student: Annotated[int, Field(ge=1)] = 2
    authoring_runs_per_day: Annotated[int, Field(ge=1)] = 20
    authoring_max_concurrent: Annotated[int, Field(ge=1)] = 4
    authoring_price_in: float = 2.0
    authoring_price_cached: float = 0.10
    authoring_price_out: float = 10.0

    # Documents and transcription (006 design 3.8).
    document_max_bytes: Annotated[int, Field(ge=1)] = 26_214_400
    document_max_pages: Annotated[int, Field(ge=1, le=100)] = 50
    document_min_pixels: Annotated[int, Field(ge=1)] = 800
    document_workers: Annotated[int, Field(ge=1)] = 2
    document_render_timeout_s: Annotated[float, Field(gt=0)] = 60.0
    transcription_model: str = "gpt-6.1-sol"
    transcription_reasoning_effort: EffortSetting = "low"
    transcription_detail: Literal["low", "high", "auto"] = "high"
    transcription_dpi: Annotated[int, Field(ge=72, le=300)] = 150
    transcription_max_side_px: Annotated[int, Field(ge=512)] = 1800
    transcription_batch_pages: Annotated[int, Field(ge=1, le=8)] = 2
    transcription_concurrency: Annotated[int, Field(ge=1)] = 4
    transcription_max_output_tokens: Annotated[int, Field(ge=1000)] = 16_000
    transcription_verify_handwriting: bool = False
    transcription_price_in: float = 2.0
    transcription_price_cached: float = 0.10
    transcription_price_out: float = 10.0

    # Voice (003 design 3.15). The transcription model must be one the Realtime
    # session schema lists; the SDK rejects others at mint time.
    voice_enabled: bool = True
    voice_model: str = "gpt-realtime-2.1"
    voice_name: str = "marin"
    voice_speed: Annotated[float, Field(ge=0.25, le=1.5)] = 1.0
    voice_reasoning_effort: EffortSetting = "low"
    voice_transcription_model: str = "gpt-4o-mini-transcribe"
    voice_turn_detection: Literal["semantic_vad", "server_vad"] = "semantic_vad"
    voice_max_output_tokens: int = 1024
    voice_secret_ttl_s: Annotated[int, Field(ge=10, le=7200)] = 90
    voice_session_max_s: Annotated[int, Field(ge=30, le=3600)] = 1500
    voice_idle_s: Annotated[int, Field(ge=10, le=3600)] = 180
    voice_sessions_per_hour: Annotated[int, Field(ge=1)] = 6
    voice_seed_token_budget: int = 12_000

    # Photographed work: the camera in the composer. The photo is read by the transcription role (a vision
    # model) into text the student corrects and sends; nothing is stored.
    work_max_bytes: Annotated[int, Field(ge=1)] = 12_582_912
    work_min_pixels: Annotated[int, Field(ge=64)] = 400  # a webcam's 480p is a small photo, not a refusal
    work_max_output_tokens: Annotated[int, Field(ge=200)] = 3000
    work_per_hour: Annotated[int, Field(ge=1)] = 60

    # Dictation: the microphone in the composer turns speech into a written message. The model is the voice
    # role's speech-to-text model (`voice_transcription_model`), on the voice connection if it has one of its
    # own, else the default connection. Not related to `transcription_*`, which reads uploaded documents.
    dictation_enabled: bool = True
    dictation_max_bytes: Annotated[int, Field(ge=1)] = 4_194_304
    dictation_max_s: Annotated[int, Field(ge=5, le=300)] = 60
    dictation_per_hour: Annotated[int, Field(ge=1)] = 240
    dictation_price_per_min: float = 0.003  # USD, for the dictation log line
    trust_proxy: bool = False
    # USD per million tokens, for the cost estimate in the voice_usage log.
    voice_price_audio_in: float = 32.0
    voice_price_audio_cached: float = 0.40
    voice_price_audio_out: float = 64.0
    voice_price_text_in: float = 4.0
    voice_price_text_cached: float = 0.40
    voice_price_text_out: float = 24.0

    @field_validator("prompts_dir")
    @classmethod
    def _absolute(cls, value: Path) -> Path:
        return value if value.is_absolute() else (REPO_ROOT / value).resolve()

    @field_validator("secrets_dir", mode="before")
    @classmethod
    def _secrets_dir(cls, value: object) -> object:
        """`SECRETS_DIR=` (empty) means unset; a relative path is relative to the repository."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        path = Path(str(value)).expanduser()
        return path if path.is_absolute() else (REPO_ROOT / path).resolve()

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    def local_now(self) -> datetime:
        """The learner's clock, for the greeting and the state message."""
        return datetime.now(ZoneInfo(self.timezone))

    def require_session_secret(self) -> str:
        """Like the API key: fail at startup, not on the first sign-in."""
        if len(self.session_secret) < MIN_SESSION_SECRET_CHARS:
            raise MissingSessionSecret(
                f"SESSION_SECRET is not set (or shorter than {MIN_SESSION_SECRET_CHARS} characters). Add a long random "
                "value to .env before starting the backend."
            )
        return self.session_secret


@lru_cache
def get_settings() -> Settings:
    return Settings()
