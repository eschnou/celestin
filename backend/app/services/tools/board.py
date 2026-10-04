"""Board tool arguments and handlers.

Handlers hold no state (design 3.4): the browser owns the board. A handler
validates and returns what to emit, plus the French marker the transcript shows
(R5.2 — the backend owns the wording because it owns the tool semantics).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from functools import cache
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, ValidationError

from app.domain.board import CLEAR_MARKER, BoardCard, DefinitionBlock, ExerciseCard, card_blocks
from app.domain.chart import ChartBlock
from app.domain.errors import ToolValidationError
from app.domain.figure import FigureBlock
from app.domain.flowchart import FlowchartBlock
from app.domain.marker import Marker
from app.domain.plot import PlotBlock
from app.domain.prose import NotProse
from app.services.tools.charts import Refusal, charts_refusal
from app.services.tools.figures import figures_refusal, figures_summary
from app.services.tools.flowcharts import flowcharts_refusal, flowcharts_summary
from app.services.tools.plots import plots_refusal, plots_summary
from app.services.tools.context import TurnContext
from app.services.tools.text import MATH, spaced

log = logging.getLogger(__name__)
_COMMAND = re.compile(r"\\[A-Za-z]+")
# A subscript or superscript written bare (`u_n`, `x^2`, `m·s^-2`, `^{2}`): shown raw
# outside `$…$`.
_SCRIPT = re.compile(r"[A-Za-z0-9)\]}]\s*[_^]\s*[-−]?[A-Za-z0-9({\\]|[_^]\s*\{")

# A control character in a string the model wrote, and the letters after it. JSON reads
# `\b`, `\f`, `\n`, `\r` and `\t` as escapes, so a LaTeX command whose backslash was not
# doubled arrives as one: `\frac` as a form feed and `rac`, `\neq` as a newline and `eq`.
_CONTROL = re.compile(r"([\x00-\x1f])([A-Za-z]*)")
_ESCAPED = {"\b": "b", "\f": "f", "\n": "n", "\r": "r", "\t": "t"}
# The KaTeX commands starting with one of those letters, from KaTeX's own tables (its
# colour macros and internals left out): what tells `\neq` from a paragraph starting
# « nombre ».
_ESCAPABLE = frozenset(
    """
    backepsilon backprime backsim backsimeq backslash bar barwedge bcancel because begin
    begingroup beta beth between bf big bigcap bigcirc bigcup bigg biggl biggm biggr bigl
    bigm bigodot bigoplus bigotimes bigr bigsqcup bigstar bigtriangledown bigtriangleup
    biguplus bigvee bigwedge binom blacklozenge blacksquare blacktriangle blacktriangledown
    blacktriangleleft blacktriangleright bm bmod bold boldsymbol bot bowtie boxdot boxed
    boxminus boxplus boxtimes bra brace brack braket breve bull bullet bumpeq
    fallingdotseq fbox fcolorbox flat footnotesize forall frac frak frown
    nLeftarrow nLeftrightarrow nRightarrow nVDash nVdash nabla natnums natural ncong ne
    nearrow neg negmedspace negthickspace negthinspace neq newline nexists ngeq ngeqq
    ngeqslant ngtr ni nleftarrow nleftrightarrow nleq nleqq nleqslant nless nmid nobreak
    nobreakspace nolimits nonumber normalsize not notag notin notni nparallel nprec npreceq
    nrightarrow nshortmid nshortparallel nsim nsubseteq nsubseteqq nsucc nsucceq nsupseteq
    nsupseteqq ntriangleleft ntrianglelefteq ntriangleright ntrianglerighteq nu nvDash
    nvdash nwarrow
    rArr rBrace rVert raisebox rang rangle rarr ratio rbrace rbrack rceil real reals
    reflectbox restriction rfloor rgroup rhd rho right rightarrow rightarrowtail
    rightharpoondown rightharpoonup rightleftarrows rightleftharpoons rightrightarrows
    rightsquigarrow rightthreetimes risingdotseq rlap rm rmoustache rparen rq rrbracket
    rtimes rule rvert
    tag tan tanh tau tbinom text textasciicircum textasciitilde textbackslash textbar
    textbardbl textbf textbraceleft textbraceright textcircled textcolor textcopyright
    textdagger textdaggerdbl textdegree textdollar textellipsis textemdash textendash
    textgreater textit textless textmd textnormal textquotedblleft textquotedblright
    textquoteleft textquoteright textregistered textrm textsf textsterling textstyle
    texttt textunderscore textup tfrac tg th therefore theta thetasym thickapprox thicksim
    thickspace thinspace tilde times tiny to top triangle triangledown triangleleft
    trianglelefteq triangleq triangleright trianglerighteq tt twoheadleftarrow
    twoheadrightarrow
    """.split()
)


# What a string check is handed: the string as written, and its prose (the string
# without its `$…$`), None for a field that is not prose. It answers what it found,
# "" for something it cannot name, or None.
_Check = Callable[[str, str | None], str | None]


def _loose_math_spans(text: str) -> list[tuple[int, int]]:
    """Where `$…$` / `$$…$$` sit, paired as the board's RichText pairs them on its
    price rule (a `$` right after a digit is a price and never opens maths), but
    allowing whitespace just inside the dollars: a lost `\\neq` puts a newline there."""
    spans: list[tuple[int, int]] = []
    i = 0
    while (j := text.find("$", i)) != -1:
        if j > 0 and text[j - 1].isdigit():
            i = j + 1
            continue
        delimiter = "$$" if text.startswith("$$", j) else "$"
        k = text.find(delimiter, j + len(delimiter))
        if k == -1:
            break
        spans.append((j, k + len(delimiter)))
        i = k + len(delimiter)
    return spans


def _lost_backslash(text: str, prose: str | None) -> str | None:
    r"""The LaTeX command a control character in `text` stands for (`\neq`), "" for
    one that stands for none, None when the string holds no lost backslash.

    A field that is not prose (a tex field, an id) is LaTeX throughout; elsewhere
    LaTeX is what sits between dollars. A newline, a tab or a CRLF is ordinary in
    prose, so there only the start of a real command counts; in LaTeX a tab or a
    carriage return never belongs, and a newline counts when a command follows it.
    Any other control character (a form feed, a backspace) is a lost backslash
    wherever it is."""
    text = text.replace("\r\n", "\n")
    latex = [(0, len(text))] if prose is None else _loose_math_spans(text)
    for found in _CONTROL.finditer(text):
        char, letters = found.groups()
        command = _ESCAPED.get(char, "") + letters
        known = char in _ESCAPED and command in _ESCAPABLE
        inside = any(start <= found.start() < end for start, end in latex)
        if char == "\n":
            lost = inside and known
        elif char in "\t\r":
            # Before a command's tail even in prose: a model writes `\to` or `\tau` far
            # more often than a real tab before « o » or « au », which is refused too.
            lost = inside or known
        else:
            lost = True
        if lost:
            return f"\\{command}" if known else ""
    return None


def _outside_math(pattern: re.Pattern[str]) -> _Check:
    """A check for `pattern` in the prose around `$…$`, which the board shows raw."""

    def check(_: str, prose: str | None) -> str | None:
        found = pattern.search(prose) if prose is not None else None
        return found.group() if found else None

    return check


# The string checks, in order: each a rule code, what it finds in one string, and the
# start of its message. The first check any string fails refuses the card, naming
# every string that fails it.
_STRING_CHECKS: tuple[tuple[str, _Check, str], ...] = (
    (
        "string_control",
        _lost_backslash,
        "Un caractère de contrôle a pris la place d'une barre oblique : dans le JSON, "
        "une commande LaTeX s'écrit avec deux barres (\\\\frac, \\\\text)",
    ),
    (
        "string_latex",
        _outside_math(_COMMAND),
        "Du LaTeX hors de $…$ s'affiche tel quel : mets-le entre $…$ ou dans un champ tex",
    ),
    (
        "string_script",
        _outside_math(_SCRIPT),
        "Un indice ou un exposant hors de $…$ s'affiche tel quel : mets-le entre $…$ ou dans un champ tex",
    ),
)


def _fixed(annotation: Any) -> bool:
    """Whether a field's type is a Literal, optional or not: values the schema fixes."""
    arms = get_args(annotation) if get_origin(annotation) in (Union, UnionType) else (annotation,)
    return all(get_origin(arm) is Literal for arm in arms if arm is not type(None))


@cache
def _not_prose(model: type[BaseModel]) -> frozenset[str]:
    """The fields of a card model whose strings are not prose: marked `NOT_PROSE`
    (raw LaTeX, ids, an expression), or a Literal (`kind`, a shape's `right_angle`)."""
    return frozenset(
        name
        for name, field in model.model_fields.items()
        if any(isinstance(m, NotProse) for m in field.metadata) or _fixed(field.annotation)
    )


def _strings(value: Any, path: str, raw: bool = False) -> Iterator[tuple[str, str, bool]]:
    """Every string of a card, in field order, raw LaTeX and ids included: its path,
    the string, and whether it is not prose. It walks the parsed card, not its dump:
    the model's fields say which strings are prose, whatever their name. A dict's
    keys are names, not text: a figure's points are keyed by `A_1`."""
    if isinstance(value, BaseModel):
        model = type(value)
        not_prose = _not_prose(model)
        for name in model.model_fields:
            yield from _strings(getattr(value, name), f"{path}.{name}", raw or name in not_prose)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(item, f"{path}.{key}", raw)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _strings(item, f"{path}[{i}]", raw)
    elif isinstance(value, str):
        yield path, value, raw


def _strings_refusal(card: BoardCard) -> tuple[str, str, list[str]] | None:
    """The first string check the card fails, as (rule, message, paths), or None.

    One walk over the card's strings runs every check on each, its `$…$` taken out
    once; the first check, in order, that any string fails refuses the card, naming
    every string that fails it. Checked when the tool runs rather than on a model:
    stored transcripts replay through the card model and must keep validating, and
    a refusal inside a drawing is counted under its family."""
    failed: dict[str, list[tuple[str, str]]] = {rule: [] for rule, _, _ in _STRING_CHECKS}
    for path, text, raw in _strings(card, "card"):
        prose = None if raw else MATH.sub("", text)
        for rule, check, _ in _STRING_CHECKS:
            if (what := check(text, prose)) is not None:
                failed[rule].append((path, what))
    for rule, _, message in _STRING_CHECKS:
        if found := failed[rule]:
            named = ", ".join(f"{path} ({what})" if what else path for path, what in found)
            return rule, f"{message} : {named}", [path for path, _ in found]
    return None


# No docstring: it would become the schema description and move the cached prefix
# (002 R4.5). The string checks run in `display_board`.
class DisplayBoardArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card: BoardCard


class ClearBoardArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class BoardSet:
    card: BoardCard
    marker: Marker
    # Board tools have nothing to tell the model beyond "ok".
    output: str | None = None


@dataclass(frozen=True)
class BoardCleared:
    marker: Marker
    output: str | None = None


def _wording(text: str) -> str:
    r"""Letters and digits only, compatibility-folded and lower-cased.

    What "word for word" can hold a model to: punctuation, spacing, apostrophes
    and Markdown emphasis differ between the pack and a board card without the
    wording changing, and so does notation — `$u_n$` against `uₙ`, `\neq`
    against `≠` — so LaTeX commands drop out too.
    """
    folded = unicodedata.normalize("NFKC", _COMMAND.sub("", text)).casefold()
    return "".join(c for c in folded if c.isalnum())


def _definition_refusal(card: BoardCard, pack: str | None) -> str | None:
    """Why the card's definitions cannot go on the board, or None.

    Checked when the tool runs rather than on the card model: it needs the pack,
    and a stored card must keep replaying if the pack is later edited."""
    definitions = [block for _, block in card_blocks(card) if isinstance(block, DefinitionBlock)]
    # The pack is folded only when there is something to look up in it.
    source = _wording(pack) if pack is not None and definitions else None
    for block in definitions:
        for entry in block.entries:
            if spaced(entry.term) not in spaced(entry.text):
                return (
                    f"Le terme « {entry.term} » n'apparaît pas dans sa définition. "
                    "Donne-le tel que la définition l'écrit."
                )
            if source is not None and _wording(entry.text) not in source:
                return (
                    f"La définition de « {entry.term} » ne se trouve pas dans le cours. "
                    "Un bloc definition recopie le pack mot pour mot ; une reformulation "
                    "va dans un bloc text."
                )
    return None


def _where(ctx: TurnContext) -> dict[str, Any]:
    # Ids and codes only: a drawing's labels and values are the student's material.
    return {"user_id": ctx.user_id, "chapter_id": ctx.chapter_id, "mode": ctx.mode}


def _chart_refusal(items: Sequence[tuple[str, ChartBlock]], card: BoardCard, _: TurnContext) -> Refusal | None:
    return charts_refusal([(path, block.chart) for path, block in items], exercise=isinstance(card, ExerciseCard))


def _chart_summary(items: Sequence[tuple[str, ChartBlock]]) -> dict[str, Any]:
    return {"kinds": [block.chart.kind for _, block in items]}


@dataclass(frozen=True)
class _Family:
    """A drawing family: its block, its tool rules and what its display logs."""

    block: type
    refusal: Callable[[Sequence[tuple[str, Any]], BoardCard, TurnContext], Refusal | None]
    summary: Callable[[Sequence[tuple[str, Any]]], dict[str, Any]]


# Keyed by the block's `type`, which is also its tag in a Pydantic error's loc.
# Each family logs `<type>_refused` (with the rule) and `<type>_displayed`.
_FAMILIES: dict[str, _Family] = {
    "chart": _Family(ChartBlock, _chart_refusal, _chart_summary),
    "flowchart": _Family(FlowchartBlock, flowcharts_refusal, flowcharts_summary),
    "figure": _Family(FigureBlock, figures_refusal, figures_summary),
    "plot": _Family(PlotBlock, plots_refusal, plots_summary),
}


def _family_in(loc: tuple[int | str, ...]) -> str | None:
    """The drawing family a Pydantic error's loc points into, read at its fixed place:
    the union tag right after `blocks, <i>` or after `drawing`. Any other element can
    be a name the model chose (a figure point called « chart ») or a stray key."""
    for i, part in enumerate(loc):
        if part == "blocks" and i + 2 < len(loc):
            tag = loc[i + 2]
        elif part == "drawing" and i + 1 < len(loc):
            tag = loc[i + 1]
        else:
            continue
        return tag if isinstance(tag, str) and tag in _FAMILIES else None
    return None


def log_schema_refusal(exc: ValidationError, ctx: TurnContext) -> None:
    """A drawing the card model refused (a negative value, a ninth sector) never
    reaches `display_board`; it is counted here, under the Pydantic error type, so
    the per-rule refusal counts are whole."""
    for error in exc.errors():
        if name := _family_in(error["loc"]):
            log.info(f"{name}_refused", extra={**_where(ctx), "rule": f"schema.{error['type']}"})
            return


# However many families it mixes, a card stops being a board past two drawings.
MAX_DRAWINGS_PER_CARD = 2


def _families_at(paths: Sequence[str], blocks: Sequence[tuple[str, Any]]) -> list[str]:
    """The drawing families whose blocks hold one of these string paths, each once,
    in card order. A string in a text block, or in the card itself, names none."""
    names: list[str] = []
    for at, block in blocks:
        if block.type in _FAMILIES and block.type not in names and any(p.startswith(f"card.{at}.") for p in paths):
            names.append(block.type)
    return names


def display_board(args: DisplayBoardArgs, ctx: TurnContext) -> BoardSet:
    where = _where(ctx)
    blocks = card_blocks(args.card)
    if unfit := _strings_refusal(args.card):
        rule, message, paths = unfit
        for name in _families_at(paths, blocks):
            log.info(f"{name}_refused", extra={**where, "rule": rule})
        raise ToolValidationError(message)
    if refusal := _definition_refusal(args.card, ctx.pack):
        raise ToolValidationError(refusal)
    drawn = {
        name: items
        for name, family in _FAMILIES.items()
        if (items := [(path, block) for path, block in blocks if isinstance(block, family.block)])
    }
    if sum(len(items) for items in drawn.values()) > MAX_DRAWINGS_PER_CARD:
        log.info("drawing_refused", extra={**where, "rule": "per_card"})
        raise ToolValidationError(
            f"Une carte porte au plus {MAX_DRAWINGS_PER_CARD} dessins, toutes sortes confondues ; "
            "répartis les autres sur une carte suivante."
        )
    # Every family is checked before any display is logged: a refused card logs none.
    for name, items in drawn.items():
        if refused := _FAMILIES[name].refusal(items, args.card, ctx):
            rule, message = refused
            log.info(f"{name}_refused", extra={**where, "rule": rule})
            raise ToolValidationError(message)
    for name, items in drawn.items():
        log.info(f"{name}_displayed", extra={**where, **_FAMILIES[name].summary(items)})
    return BoardSet(card=args.card, marker=args.card.marker)


def clear_board(_: ClearBoardArgs, __: TurnContext) -> BoardCleared:
    return BoardCleared(marker=CLEAR_MARKER)
