"""Board cards (design 4.2).

The shapes the tutor may put on the whiteboard, one per existing card component.
Constraints live here rather than in the prompt: a violation is a tool error the
model is asked to fix (R4.6).

Inline maths inside any prose field uses `$…$`; `tex` fields are raw LaTeX. A field
whose strings are not prose (LaTeX, ids) carries `NOT_PROSE`; see `app/domain/prose.py`.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from app.domain.chart import ChartBlock
from app.domain.figure import FigureBlock
from app.domain.flowchart import FlowchartBlock
from app.domain.locale import DEFAULT_LOCALE, Locale
from app.domain.marker import Marker
from app.domain.plot import PlotBlock
from app.domain.prose import NOT_PROSE

NonEmpty = Annotated[str, Field(min_length=1, max_length=2000)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Card(_Model):
    """A card the tutor can put on the board.

    `marker` is the label the transcript shows (French as a string, re-rendered in the
    request's language at the edge). It lives on the card so the union stays the single
    place a kind is declared: a new card kind cannot ship without its label (design 3.2,
    10.3).
    """

    marker: ClassVar[Marker]


class TextBlock(_Model):
    type: Literal["text"] = "text"
    text: NonEmpty


class FormulaBlock(_Model):
    type: Literal["formula"] = "formula"
    tex: Annotated[NonEmpty, NOT_PROSE]
    caption: str | None = None


class QuoteBlock(_Model):
    """Something quoted verbatim from the course, in the highlighter style.

    A definition is prose and a rule is a formula, and the course highlights both,
    so this takes exactly one of the two. Prose put through `tex` comes out of
    KaTeX with every accent detached from its letter.
    """

    type: Literal["quote"] = "quote"
    text: NonEmpty | None = None
    tex: Annotated[NonEmpty | None, NOT_PROSE] = None
    caption: NonEmpty

    @model_validator(mode="after")
    def _exactly_one_body(self) -> QuoteBlock:
        if (self.text is None) == (self.tex is None):
            raise ValueError("a quote needs exactly one of text (prose) or tex (a formula)")
        return self


class NoteBlock(_Model):
    type: Literal["note"] = "note"
    label: NonEmpty
    text: NonEmpty


class DefinitionEntry(_Model):
    term: Annotated[str, Field(min_length=1, max_length=120)]
    text: NonEmpty


class DefinitionBlock(_Model):
    """Definitions quoted word for word from the course pack, one entry per term.

    `term` is the word being defined and must appear in `text`, where the board
    sets it in bold. Related terms go in one block, not one block each.
    """

    type: Literal["definition"] = "definition"
    entries: Annotated[list[DefinitionEntry], Field(min_length=1, max_length=6)]


Block = Annotated[
    Union[
        TextBlock,
        FormulaBlock,
        QuoteBlock,
        NoteBlock,
        DefinitionBlock,
        ChartBlock,
        FlowchartBlock,
        FigureBlock,
        PlotBlock,
    ],
    Field(discriminator="type"),
]


# What a drawing without `type` holds, first match wins: the key only one block has.
_DRAWING_KEYS = (
    ("chart", "chart"),
    ("figure", "figure"),
    ("nodes", "flowchart"),
    ("x_range", "plot"),
    ("y_range", "plot"),
    ("curves", "plot"),
)


def _drawing_type(value: Any) -> str | None:
    """A drawing's block type. 008 let a chart drawing leave `type` out (its default
    filled it), so a drawing without it is read from its keys, a chart when none
    tells. Every later drawing block declares `type` as required: read as itself, it
    is refused for the missing tag, with its own block's error, never a chart's."""
    if isinstance(value, dict):
        if "type" in value:
            return value["type"]
        return next((tag for key, tag in _DRAWING_KEYS if key in value), "chart")
    return getattr(value, "type", None)


# What a worked example or an exercise draws under its statement: one drawing, of
# any family. A callable discriminator: `Field(discriminator="type")` would refuse a
# chart drawing without `type`, which 008 accepted.
Drawing = Annotated[
    Union[
        Annotated[ChartBlock, Tag("chart")],
        Annotated[FlowchartBlock, Tag("flowchart")],
        Annotated[FigureBlock, Tag("figure")],
        Annotated[PlotBlock, Tag("plot")],
    ],
    Discriminator(_drawing_type),
]


class Step(_Model):
    tex: Annotated[NonEmpty, NOT_PROSE]
    note: str | None = None


class Option(_Model):
    id: Annotated[str, Field(min_length=1, max_length=8), NOT_PROSE]
    text: NonEmpty


class TitleCard(_Card):
    kind: Literal["title"] = "title"
    marker: ClassVar[Marker] = Marker("marker.title")
    eyebrow: NonEmpty
    title: NonEmpty
    objective: NonEmpty


class ExplanationCard(_Card):
    kind: Literal["explanation"] = "explanation"
    marker: ClassVar[Marker] = Marker("marker.explanation")
    title: NonEmpty
    blocks: Annotated[list[Block], Field(min_length=1, max_length=12)]


class WorkedExampleCard(_Card):
    kind: Literal["worked_example"] = "worked_example"
    marker: ClassVar[Marker] = Marker("marker.worked_example")
    title: NonEmpty
    statement: NonEmpty
    drawing: Drawing | None = None
    steps: Annotated[list[Step], Field(min_length=1, max_length=8)]


class ExerciseCard(_Card):
    kind: Literal["exercise"] = "exercise"
    marker: ClassVar[Marker] = Marker("marker.exercise")
    title: NonEmpty
    statement: NonEmpty
    drawing: Drawing | None = None
    hint: str | None = None


class CheckQuestionCard(_Card):
    kind: Literal["check_question"] = "check_question"
    marker: ClassVar[Marker] = Marker("marker.check_question")
    question: NonEmpty
    options: Annotated[list[Option], Field(min_length=2, max_length=4)]
    correct_option_id: Annotated[NonEmpty, NOT_PROSE]
    feedback: NonEmpty

    @model_validator(mode="after")
    def _correct_option_exists(self) -> CheckQuestionCard:
        ids = [o.id for o in self.options]
        if self.correct_option_id not in ids:
            raise ValueError(f"correct_option_id must be one of {ids}")
        if len(set(ids)) != len(ids):
            raise ValueError("option ids must be unique")
        return self


class RecapCard(_Card):
    kind: Literal["recap"] = "recap"
    marker: ClassVar[Marker] = Marker("marker.recap")
    acquired: Annotated[list[NonEmpty], Field(min_length=1, max_length=6)]
    watch: Annotated[list[NonEmpty], Field(max_length=6)] = []
    next: NonEmpty


BoardCard = Annotated[
    Union[
        TitleCard,
        ExplanationCard,
        WorkedExampleCard,
        ExerciseCard,
        CheckQuestionCard,
        RecapCard,
    ],
    Field(discriminator="kind"),
]


def card_blocks(card: BoardCard) -> list[tuple[str, Block]]:
    """The card's blocks in card order, each with the path a tool message names:
    an explanation's `blocks`, a worked example's or exercise's `drawing`. The one
    place that knows where a block can sit on a card."""
    if isinstance(card, ExplanationCard):
        return [(f"blocks[{i}]", block) for i, block in enumerate(card.blocks)]
    if isinstance(card, (WorkedExampleCard, ExerciseCard)) and card.drawing is not None:
        return [("drawing", card.drawing)]
    return []


CLEAR_MARKER = Marker("marker.cleared")

_CARD = TypeAdapter(BoardCard)


def marker_for(name: str, arguments: dict[str, Any], locale: Locale = DEFAULT_LOCALE) -> str | None:
    """The label a board call shows in the transcript, from the call alone, in `locale`.

    A live turn reads it off the tool outcome; a stored discussion has only the
    recorded arguments, so it asks here rather than keeping a second copy of the
    wording (007 design 4.3).
    """
    if name == "clear_board":
        return CLEAR_MARKER.render(locale)
    if name != "display_board":
        return None
    try:
        return _CARD.validate_python(arguments.get("card")).marker.render(locale)
    except ValidationError:
        return None
