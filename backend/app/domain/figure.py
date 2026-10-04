"""Figure blocks: geometry, number lines and diagrams of sets on the board.

A figure is drawn from what the course would say about it: named points in the
figure's own units and the shapes joining them, a number line and its
intervals, or sets and what they hold. The model never gives pixels, colours or
drawing commands; the board scales, lays out and writes the notation itself
(decimal comma, `]a ; b[`, `A(2 ; 3)`).

Only rules that never change live here (types, enums, sizes, finite numbers, how
a point is named); the rules that could (references, how many points a shape
takes, degenerate shapes, the codage, the window, what fits on the board) run in
`display_board` (`app/services/tools/figures.py`), so a stored card keeps
replaying. The one docstring is `FigureBlock`'s: docstrings and descriptions
become tool-schema text in the cached prompt prefix.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from app.domain.chart import Caption, Coord, Label
from app.domain.prose import NOT_PROSE


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# [x, y] in the figure's own units (y up), or a range's [min, max].
Pair = Annotated[list[Coord], Field(min_length=2, max_length=2)]
# A point as a course names it: A, B', M'', A_1. Typeset by KaTeX as maths.
PointName = Annotated[str, Field(pattern=r"^[A-Z]('{1,2}|_[0-9]{1,2})?$")]
SetId = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9]?$")]

MAX_POINTS = 26
MAX_SHAPES = 30
MAX_VERTICES = 12
MAX_INTERVALS = 4
MAX_MARKS = 12
MAX_SETS = 5
MAX_ELEMENTS = 24
MAX_ZONES = 8

Draw = Literal["segment", "line", "ray", "vector", "polygon", "circle", "arc", "angle", "right_angle"]

# The model cannot guess how many points each shape takes, nor their order.
_OF = (
    "Les points par leur nom. segment, line : 2 points ; vector : origine puis extrémité ; "
    "ray : origine puis un point ; polygon : les sommets dans l'ordre du tour ; circle : le "
    "centre (avec radius) ou le centre puis un point du cercle ; arc : une extrémité, le centre, "
    "l'autre extrémité ; angle, right_angle : A, B, C pour l'angle en B."
)


class FigureShape(_Model):
    draw: Draw
    of: Annotated[list[PointName], Field(min_length=1, max_length=MAX_VERTICES, description=_OF), NOT_PROSE]
    radius: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None = None
    marks: Annotated[
        int,
        Field(ge=0, le=3, description="Codage : traits sur un segment, arcs sur un angle ; même codage, même mesure."),
    ] = 0
    label: Label | None = None
    style: Literal["dashed", "highlight"] | None = None


class _Shown(_Model):
    show_values: bool = False
    caption: Caption | None = None


class PlaneFigure(_Shown):
    kind: Literal["plane"] = "plane"
    points: Annotated[dict[PointName, Pair], Field(max_length=MAX_POINTS)] = {}
    shapes: Annotated[list[FigureShape], Field(max_length=MAX_SHAPES)] = []
    x_range: Pair | None = None
    y_range: Pair | None = None
    axes: bool = False
    grid: bool = False
    marker: Literal["cross", "dot"] = "cross"


class LineInterval(_Model):
    start: Annotated[Coord | None, Field(description="null : −∞")] = None
    end: Annotated[Coord | None, Field(description="null : +∞")] = None
    closed: Literal["both", "left", "right", "neither"]
    label: Label | None = None


class LineMark(_Model):
    x: Coord
    label: Label | None = None


class NumberLine(_Shown):
    kind: Literal["number_line"] = "number_line"
    intervals: Annotated[list[LineInterval], Field(max_length=MAX_INTERVALS)] = []
    marks: Annotated[list[LineMark], Field(max_length=MAX_MARKS)] = []
    convention: Annotated[
        Literal["brackets", "dots", "hatched"],
        Field(description="hatched : on hachure ce qui ne convient pas."),
    ] = "brackets"


# The sets an element or a hatched zone lies in; [] is outside them all.
Zone = Annotated[list[SetId], Field(max_length=MAX_SETS)]


class FigureSet(_Model):
    id: Annotated[SetId, NOT_PROSE]
    label: Label


class SetElement(_Model):
    text: Label
    within: Annotated[
        Zone,
        Field(description="Les ensembles où il se trouve, et eux seuls (ceux qui les contiennent comptent d'office) ; [] : hors de tous."),
        NOT_PROSE,
    ] = []


class SetDiagram(_Model):
    kind: Literal["sets"] = "sets"
    layout: Literal["nested", "overlap", "separate"]
    sets: Annotated[
        list[FigureSet],
        Field(min_length=1, max_length=MAX_SETS, description="Pour nested, du plus grand au plus petit."),
    ]
    universe: Label | None = None
    elements: Annotated[list[SetElement], Field(max_length=MAX_ELEMENTS)] = []
    shade: Annotated[
        list[Zone],
        Field(
            max_length=MAX_ZONES,
            description=(
                "Zones hachurées, chacune écrite comme within ; hachurer un ensemble entier, c'est "
                'hachurer chacune de ses zones (tout A, qui chevauche B : [["A"], ["A", "B"]]).'
            ),
        ),
        NOT_PROSE,
    ] = []
    caption: Caption | None = None


Figure = Annotated[Union[PlaneFigure, NumberLine, SetDiagram], Field(discriminator="kind")]


class FigureBlock(_Model):
    """A figure the board scales and draws: plane geometry in the figure's own
    units (y up), a number line, or a diagram of sets. Give points and relations,
    never pixels, colours or drawings."""

    # Required: a card's `drawing` reads a missing tag from its keys (board.py
    # `Drawing`), and refuses it for the missing tag.
    type: Literal["figure"]
    figure: Figure
