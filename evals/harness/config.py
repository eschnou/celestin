"""The candidate list: `models.toml` read into specs, and the environment a worker runs in.

A worker is the application's own code in the backend's virtualenv. It learns which model to use the way the
server does, from environment variables (`documentation/ai-providers.md`), so this module's job is to build an
environment that says exactly what the spec says and nothing the developer's shell or `.env` happened to hold.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SUITES = ("live", "tutor", "authoring")
# The probe sets a worker can run, and the flag `scripts.probe` knows each by (None: the guardrail set).
SETS: dict[str, str | None] = {
    "guardrails": None,
    "charts": "--charts",
    "flowcharts": "--flowcharts",
    "figures": "--figures",
    "plots": "--plots",
}
LANGUAGES = ("fr", "en")
EFFORTS = ("", "low", "medium", "high")  # "" is « not sent »: a setting, unlike an absent key
API_STYLES = ("responses", "chat")
STRUCTURED = ("schema", "json")
ROLES = ("tutor", "authoring", "transcription", "voice")

# Every variable that could point a worker at a provider other than the one the spec names.
_PER_ROLE = ("BASE_URL", "API_KEY", "API_STYLE", "STRUCTURED_OUTPUTS")
AMBIENT_AI_VARS = frozenset(
    {
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "AI_API_STYLE",
        "AI_STRUCTURED_OUTPUTS",
        "AUTHORING_MODEL",
        "AUTHORING_MAX_OUTPUT_TOKENS",
        "TRANSCRIPTION_MODEL",
        "VOICE_MODEL",
        "VOICE_TRANSCRIPTION_MODEL",
        "SECRETS_DIR",
        "DEBUG_LOG_PROMPTS",
        *(f"{role.upper()}_REASONING_EFFORT" for role in ROLES),
        *(f"{role.upper()}_{suffix}" for role in ROLES for suffix in _PER_ROLE),
    }
)

SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class ConfigError(ValueError):
    """The file is wrong in a way the message names."""


@dataclass(frozen=True)
class Gates:
    live_tutor_min: float = 1.0
    tutor_ok_min: float = 0.90
    leak_max: float = 0.01
    out_of_pack_max: float = 0.05
    french_max: float = 0.05
    authoring_ok_min: float = 1.0


@dataclass(frozen=True)
class Defaults:
    language: str = "fr"
    runs: int = 3
    authoring_runs: int = 1
    sets: tuple[str, ...] = ("guardrails",)
    suites: tuple[str, ...] = SUITES
    turn_timeout_s: int = 180


@dataclass(frozen=True)
class ModelSpec:
    name: str
    base_url: str
    model: str
    api_key_env: str | None = None
    api_style: str = "responses"
    structured: str = "schema"
    reference: bool = False
    tutor_model: str | None = None
    authoring_model: str | None = None
    transcription_model: str | None = None
    # `effort` is the shorthand for the tutor and authoring roles; a role's own field wins over it.
    # None: the variable is not set at all (the application's own default applies); "" means "not sent".
    effort: str | None = None
    tutor_effort: str | None = None
    authoring_effort: str | None = None
    transcription_effort: str | None = None
    # The authoring agent asks for up to 32 000 output tokens; a provider may cap a model lower (Groq's Qwen: 16 384)
    # and then refuses every authoring request. None: the application's default.
    authoring_max_output_tokens: int | None = None
    price_input: float = 0.0
    price_cached: float = 0.0
    price_output: float = 0.0

    def role_model(self, role: str) -> str:
        return getattr(self, f"{role}_model", None) or self.model

    def role_effort(self, role: str) -> str | None:
        own = getattr(self, f"{role}_effort")
        if own is not None:
            return own
        return self.effort if role in ("tutor", "authoring") else None

    def api_key(self, environ: dict[str, str] | None = None) -> str | None:
        if not self.api_key_env:
            return None
        return (environ if environ is not None else os.environ).get(self.api_key_env) or None

    def describe(self) -> dict[str, Any]:
        """What a run records about the model: everything but a secret (the key's variable name is not one)."""
        return asdict(self)


@dataclass(frozen=True)
class Config:
    defaults: Defaults
    gates: Gates
    models: tuple[ModelSpec, ...]

    def reference(self) -> ModelSpec | None:
        return next((m for m in self.models if m.reference), None)

    def select(self, names: list[str] | None) -> tuple[ModelSpec, ...]:
        if not names:
            return self.models
        known = {m.name: m for m in self.models}
        missing = [n for n in names if n not in known]
        if missing:
            raise ConfigError(f"unknown model(s) {', '.join(missing)}; the file has {', '.join(known)}")
        return tuple(known[n] for n in names)


def _only(table: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ConfigError(f"{where}: unknown key(s) {', '.join(unknown)}")


def _choice(value: str, allowed: tuple[str, ...], where: str) -> str:
    if value not in allowed:
        raise ConfigError(f"{where}: {value!r} is not one of {', '.join(allowed)}")
    return value


def _names(values: Any, allowed: Any, where: str) -> tuple[str, ...]:
    if not isinstance(values, list) or not values:
        raise ConfigError(f"{where}: a non-empty list is expected")
    return tuple(_choice(str(v), tuple(allowed), where) for v in values)


def _variants(table: dict[str, Any], where: str) -> list[ModelSpec]:
    """A model, or one variant per level of `efforts`, named `<name>-<level>`. When the model is the reference
    and has several levels, `reference_effort` (default: the last one listed) says which variant is."""
    efforts = table.pop("efforts", None)
    reference_effort = table.pop("reference_effort", None)
    if efforts is None:
        if reference_effort is not None:
            raise ConfigError(f"{where}: `reference_effort` needs `efforts`")
        return [ModelSpec(**table)]
    if "effort" in table:
        raise ConfigError(f"{where}: give `effort` or `efforts`, not both")
    if not isinstance(efforts, list) or not efforts or len(set(efforts)) != len(efforts):
        raise ConfigError(f"{where}: `efforts` must be a non-empty list without repeats")
    for level in efforts:
        _choice(str(level), EFFORTS, f"{where} efforts")
    if reference_effort is not None and reference_effort not in efforts:
        raise ConfigError(f"{where}: `reference_effort` {reference_effort!r} is not in `efforts`")
    chosen = reference_effort if reference_effort is not None else efforts[-1]
    reference = bool(table.get("reference"))
    return [
        ModelSpec(**{**table, "name": f"{table['name']}-{level or 'unsent'}", "effort": level,
                     "reference": reference and level == chosen})  # fmt: skip
        for level in efforts
    ]


def parse(raw: dict[str, Any]) -> Config:
    _only(raw, {"defaults", "gates", "model"}, "the file")

    table = raw.get("defaults", {})
    _only(table, {"language", "runs", "authoring_runs", "sets", "suites", "turn_timeout_s"}, "[defaults]")
    base = Defaults()
    defaults = Defaults(
        language=_choice(str(table.get("language", base.language)), LANGUAGES, "[defaults] language"),
        runs=int(table.get("runs", base.runs)),
        authoring_runs=int(table.get("authoring_runs", base.authoring_runs)),
        sets=_names(table.get("sets", list(base.sets)), SETS, "[defaults] sets"),
        suites=_names(table.get("suites", list(base.suites)), SUITES, "[defaults] suites"),
        turn_timeout_s=int(table.get("turn_timeout_s", base.turn_timeout_s)),
    )
    if defaults.runs < 1 or defaults.authoring_runs < 1 or defaults.turn_timeout_s < 1:
        raise ConfigError("[defaults]: runs, authoring_runs and turn_timeout_s must be at least 1")

    gates_table = raw.get("gates", {})
    _only(gates_table, set(asdict(Gates())), "[gates]")
    gates = Gates(**{key: float(value) for key, value in gates_table.items()})

    allowed = set(ModelSpec.__dataclass_fields__) | {"efforts", "reference_effort"}
    models: list[ModelSpec] = []
    for index, table in enumerate(raw.get("model", []), start=1):
        where = f"[[model]] #{index}"
        _only(table, allowed, where)
        for required in ("name", "base_url", "model"):
            if not table.get(required):
                raise ConfigError(f"{where}: `{required}` is required")
        if not SLUG.match(str(table["name"])):
            raise ConfigError(f"{where}: name {table['name']!r} must be letters, digits, '.', '_' or '-'")
        for spec in _variants(dict(table), where):
            _choice(spec.api_style, API_STYLES, f"{where} api_style")
            _choice(spec.structured, STRUCTURED, f"{where} structured")
            if spec.authoring_max_output_tokens is not None and spec.authoring_max_output_tokens < 1000:
                raise ConfigError(f"{where}: authoring_max_output_tokens must be at least 1000")
            for field_name in ("effort", "tutor_effort", "authoring_effort", "transcription_effort"):
                value = getattr(spec, field_name)
                if value is not None:
                    _choice(value, EFFORTS, f"{where} {field_name}")
            models.append(spec)
    if not models:
        raise ConfigError("the file names no [[model]]")
    names = [m.name for m in models]
    if len(set(names)) != len(names):
        raise ConfigError("model names must be unique")
    if sum(m.reference for m in models) > 1:
        raise ConfigError("at most one model can be the reference")
    return Config(defaults, gates, tuple(models))


def load(path: Path) -> Config:
    try:
        return parse(tomllib.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        raise ConfigError(f"{path} does not exist (copy models.example.toml to start)") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from None


def load_dotenv(path: Path, environ: dict[str, str] | None = None) -> list[str]:
    """Read `KEY=value` lines (comments, blanks and optional quotes allowed) into the environment, without
    overriding a variable that is already set: the shell wins. Returns the names it added. Only the harness's
    own process reads this file: a worker is given exactly what `worker_env` builds, never this."""
    target = os.environ if environ is None else environ
    added: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return added
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and value and key not in target:
            target[key] = value
            added.append(key)
    return added


def worker_env(spec: ModelSpec, base: dict[str, str], *, scratch: Path, key: str | None = None) -> dict[str, str]:
    """The environment of a worker: the parent's, minus every AI variable, plus the spec.

    The database points at a file that does not exist (so the stored administrator settings are never read) and
    no secrets directory is given. Python writes no bytecode, so a run leaves nothing in `backend/`.
    """
    env = {k: v for k, v in base.items() if k not in AMBIENT_AI_VARS}
    env.update(
        OPENAI_BASE_URL=spec.base_url,
        AI_API_STYLE=spec.api_style,
        AI_STRUCTURED_OUTPUTS=spec.structured,
        OPENAI_MODEL=spec.role_model("tutor"),
        AUTHORING_MODEL=spec.role_model("authoring"),
        TRANSCRIPTION_MODEL=spec.role_model("transcription"),
        DATABASE_URL=f"sqlite:///{scratch / 'no-such.db'}",
        SESSION_SECRET="evals-" + "x" * 48,
        PYTHONDONTWRITEBYTECODE="1",
    )
    if spec.authoring_max_output_tokens is not None:
        env["AUTHORING_MAX_OUTPUT_TOKENS"] = str(spec.authoring_max_output_tokens)
    api_key = key if key is not None else spec.api_key(base)
    if api_key:
        env["OPENAI_API_KEY"] = api_key
    for role in ("tutor", "authoring", "transcription"):
        effort = spec.role_effort(role)
        if effort is not None:
            env[f"{role.upper()}_REASONING_EFFORT"] = effort
    return env


def redact(env: dict[str, str]) -> dict[str, str]:
    """The variables a worker is given that this module set, with the key hidden: what `plan` prints."""
    shown = {k: v for k, v in env.items() if k in AMBIENT_AI_VARS or k == "DATABASE_URL"}
    if "OPENAI_API_KEY" in shown:
        shown["OPENAI_API_KEY"] = "…" + shown["OPENAI_API_KEY"][-4:] if len(shown["OPENAI_API_KEY"]) > 8 else "set"
    return shown
