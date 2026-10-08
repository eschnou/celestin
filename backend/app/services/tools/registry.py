"""Tool declarations and dispatch.

Declaration order is fixed: tool definitions sit inside the cached prefix, and
reordering them invalidates every cache entry (design 7). Section tools come
after the board tools so the board declarations' bytes do not move (002 R4.5).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.domain.errors import ToolValidationError, format_validation_errors
from app.domain.language import COURSE_LANGUAGES, DEFAULT_COURSE_LANGUAGE, CourseLanguage, by_language
from app.domain.mode import DEFAULT_MODE, MODES, Mode
from app.services.tools.board import (
    BoardCleared,
    BoardSet,
    ClearBoardArgs,
    DisplayBoardArgs,
    clear_board,
    display_board,
    log_schema_refusal,
)
from app.services.tools.context import TurnContext
from app.services.tools.pace import NextStepProposed, ProposeNextStepArgs, propose_next_step
from app.services.tools.section import (
    CompleteSectionArgs,
    SectionCompleted,
    SectionStarted,
    StartSectionArgs,
    complete_section,
    replay_complete,
    replay_start,
    start_section,
)

ToolOutcome = BoardSet | BoardCleared | SectionStarted | SectionCompleted | NextStepProposed


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[Any, TurnContext], ToolOutcome]
    strict: bool
    # What a replayed, successful call answers on later turns (design 3.8), from
    # the raw stored arguments. None means a bare {"ok": true}.
    replay: Callable[[dict[str, Any], TurnContext], str] | None = None
    # Told about arguments Pydantic refused, before the model is: for the logs only.
    on_invalid: Callable[[ValidationError, TurnContext], None] | None = None

    def declaration(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.args_model.model_json_schema(),
            "strict": self.strict,
        }


# strict=False on display_board: a discriminated union over six card shapes is not
# reliably expressible under strict mode, which requires every field to be required
# with additionalProperties false. We validate with Pydantic regardless (design 4.3).
_TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        Tool(
            name="display_board",
            description=(
                "Affiche une carte au tableau, à droite de l'écran. Choisis le type de carte "
                "qui correspond : title pour ouvrir une séance, explanation pour une notion, "
                "worked_example pour un exemple guidé, exercise pour un énoncé à chercher, "
                "check_question pour une question de compréhension, recap pour clore. "
                "Un bloc chart dessine un graphique statistique, flowchart un organigramme, figure "
                "une figure géométrique, une droite graduée ou un diagramme d'ensembles, plot des "
                "fonctions, des suites ou des mesures dans un repère (expr : une expression de "
                "calcul, pas du LaTeX), tous à partir de leurs données. "
                "Les mathématiques s'écrivent en LaTeX ; $…$ pour les formules dans une phrase."
            ),
            args_model=DisplayBoardArgs,
            handler=display_board,
            strict=False,
            on_invalid=log_schema_refusal,
        ),
        Tool(
            name="clear_board",
            description="Efface le tableau. L'historique des cartes précédentes est conservé.",
            args_model=ClearBoardArgs,
            handler=clear_board,
            strict=True,
        ),
        Tool(
            name="start_section",
            description=(
                "Ouvre une section du parcours et renvoie son plan : objectif, déroulé ou "
                "exercices types, critère de fin. Refusée si la section n'est pas encore "
                "ouverte. Une section déjà faite s'ouvre en révision."
            ),
            args_model=StartSectionArgs,
            handler=start_section,
            strict=True,
            replay=replay_start,
        ),
        Tool(
            name="complete_section",
            description=(
                "Termine la section en cours, avec une phrase résumant ce qui a été fait. "
                "Seulement quand son critère de fin est atteint. Renvoie la section suivante."
            ),
            args_model=CompleteSectionArgs,
            handler=complete_section,
            strict=True,
            replay=replay_complete,
        ),
        Tool(
            name="propose_next_step",
            description=(
                "Active le bouton « Étape suivante » au tableau. Appelle-le quand tu es "
                "satisfait de l'échange sur la carte en cours, puis termine ton tour : la carte "
                "suivante n'arrive qu'après son clic ou son accord explicite."
            ),
            args_model=ProposeNextStepArgs,
            handler=propose_next_step,
            strict=True,
        ),
    )
}

# Which tools each mode offers (007 §3.5). A discussion has the board and nothing
# that could move the path: not declaring them is the first of the two locks, the
# controller's `save=None` being the second.
_MODE_TOOLS: dict[Mode, tuple[str, ...]] = {
    "parcours": tuple(_TOOLS),
    "discussion": ("display_board", "clear_board"),
}


# What the model reads in the tool declarations, per course language (spec 011 §4.7):
# `{tool name: {JSON pointer into its declaration: text}}`. Empty means the declaration is
# the one built from the code, French; both rows are empty until the English probes show
# French leaking from the descriptions into an English course's speech, and then only the
# texts that leak are written here, with one more snapshot (`board_declarations_en.json`).
TOOL_TEXT: dict[CourseLanguage, dict[str, dict[str, str]]] = by_language(fr={}, en={}, nl={})


def _pointer(declaration: dict[str, Any], pointer: str) -> tuple[Any, str]:
    """The container and the key `pointer` (RFC 6901) names in `declaration`."""
    keys = [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]]
    node: Any = declaration
    for key in keys[:-1]:
        node = node[int(key)] if isinstance(node, list) else node[key]
    last = keys[-1]
    return node, (int(last) if isinstance(node, list) else last)  # type: ignore[return-value]


def _localise(declaration: dict[str, Any], overlay: dict[str, str]) -> dict[str, Any]:
    """The declaration with the overlay's texts in place. A pointer that does not resolve
    is a stale overlay: it fails at import, not in front of a student."""
    for pointer, text in overlay.items():
        try:
            node, key = _pointer(declaration, pointer)
            node[key]  # noqa: B018 - the key must exist: an overlay replaces, never adds
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise ValueError(f"tool text for {declaration['name']!r}: {pointer!r} does not resolve") from exc
        node[key] = text
    return declaration


def _declare(mode: Mode, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> list[dict[str, Any]]:
    """In `_TOOLS` order, so a mode's list is a subset that never moves the bytes
    of the declarations it shares with another mode."""
    offered = _MODE_TOOLS[mode]
    return [
        _localise(tool.declaration(), TOOL_TEXT[language].get(tool.name, {}))
        for tool in _TOOLS.values()
        if tool.name in offered
    ]


# Built once per mode and language. Generating the display_board schema costs ~7 ms, it
# never varies, and it sits in the cached prompt prefix — so this is byte-stable by
# construction rather than by trusting the schema generator to be deterministic.
# A language whose overlay is empty shares its mode's list with French: the schema is generated
# once, and nothing mutates a declaration after the build.
_DECLARATIONS: dict[tuple[Mode, CourseLanguage], list[dict[str, Any]]] = {}
for _mode in MODES:
    _base = _declare(_mode, DEFAULT_COURSE_LANGUAGE)
    for _language in COURSE_LANGUAGES:
        _DECLARATIONS[(_mode, _language)] = (
            _base
            if _language == DEFAULT_COURSE_LANGUAGE or not TOOL_TEXT[_language]
            else _declare(_mode, _language)
        )


def declarations(mode: Mode = DEFAULT_MODE, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> list[dict[str, Any]]:
    return _DECLARATIONS[(mode, language)]


# The Realtime session schema declares a function tool without `strict` (003
# design 3.3). Same tools, same order, same bytes otherwise: a test pins it.
_REALTIME_DECLARATIONS: dict[tuple[Mode, CourseLanguage], list[dict[str, Any]]] = {
    key: [{k: v for k, v in declaration.items() if k != "strict"} for declaration in declared]
    for key, declared in _DECLARATIONS.items()
}


def realtime_declarations(
    mode: Mode = DEFAULT_MODE, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> list[dict[str, Any]]:
    return _REALTIME_DECLARATIONS[(mode, language)]


@dataclass(frozen=True)
class _Words:
    """What the registry tells the model when a call cannot be run, per course language."""

    bad_json: str  # {reason}
    not_object: str
    invalid: str  # {details}
    unavailable: str  # {name} {offered}
    root: str


_WORDS = by_language(
    fr=_Words(
        bad_json="Arguments JSON invalides : {reason}.",
        not_object="Les arguments doivent être un objet JSON.",
        invalid="Arguments invalides. {details}",
        unavailable="L'outil '{name}' n'est pas disponible ici. Outils disponibles : {offered}.",
        root="(racine)",
    ),
    en=_Words(
        bad_json="Invalid JSON arguments: {reason}.",
        not_object="The arguments must be a JSON object.",
        invalid="Invalid arguments. {details}",
        unavailable="The tool '{name}' is not available here. Available tools: {offered}.",
        root="(root)",
    ),
    nl=_Words(
        bad_json="Ongeldige JSON-argumenten: {reason}.",
        not_object="De argumenten moeten een JSON-object zijn.",
        invalid="Ongeldige argumenten. {details}",
        unavailable="De tool '{name}' is hier niet beschikbaar. Beschikbare tools: {offered}.",
        root="(basis)",
    ),
)


def _parse(tool: Tool, arguments_json: str, ctx: TurnContext) -> BaseModel:
    w = _WORDS[ctx.language]
    try:
        payload = json.loads(arguments_json or "{}")
    except json.JSONDecodeError as exc:
        raise ToolValidationError(w.bad_json.format(reason=exc.msg)) from exc
    if not isinstance(payload, dict):
        raise ToolValidationError(w.not_object)
    try:
        return tool.args_model.model_validate(payload)
    except ValidationError as exc:
        if tool.on_invalid is not None:
            tool.on_invalid(exc, ctx)
        details = format_validation_errors(exc, root=w.root)
        raise ToolValidationError(w.invalid.format(details=details)) from exc


def execute(name: str, arguments_json: str, ctx: TurnContext) -> ToolOutcome:
    """Validate then run. Every failure is a ToolValidationError whose message goes
    back to the model as a tool result, so it can correct itself (R4.6).

    The mode gate is not belt-and-braces: `/api/voice/tool` takes a tool name from
    the browser, so this is what makes the mode a server-side fact (007 §3.5)."""
    offered = _MODE_TOOLS[ctx.mode]
    tool = _TOOLS.get(name)
    if tool is None or name not in offered:
        raise ToolValidationError(
            _WORDS[ctx.language].unavailable.format(name=name, offered=", ".join(offered))
        )
    return tool.handler(_parse(tool, arguments_json, ctx), ctx)


def arguments_valid(name: str, arguments_json: str) -> bool:
    """Whether a call's arguments satisfy the tool's schema, without running it: what the AI provider test
    asks of a model before a student ever meets it."""
    tool = _TOOLS.get(name)
    try:
        payload = json.loads(arguments_json or "{}")
        if tool is None or not isinstance(payload, dict):
            return False
        tool.args_model.model_validate(payload)
    except (ValueError, ValidationError):
        return False
    return True


def replay_output(name: str, arguments: dict[str, Any], ctx: TurnContext) -> dict[str, Any]:
    """The tool result a successful call from an earlier turn answers now (design 3.8).
    Never raises: an unknown tool replays as a bare success."""
    tool = _TOOLS.get(name)
    if tool is None or tool.replay is None:
        return {"ok": True}
    return {"ok": True, "result": tool.replay(arguments, ctx)}


def output_of(outcome: ToolOutcome) -> dict[str, Any]:
    """What the model reads after a successful call in the current turn."""
    return {"ok": True, "result": outcome.output} if outcome.output else {"ok": True}


def encode_output(payload: dict[str, Any]) -> str:
    """The wire form of a tool result, on both channels. Accents stay accents."""
    return json.dumps(payload, ensure_ascii=False)
