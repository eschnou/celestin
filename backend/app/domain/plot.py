"""Plot blocks: graphs in a cartesian plane (specs/009-board-drawings/plot.md §2.1).

The model gives mathematics: a window, curves by their expression, sequences by
their general term, points and broken lines. The board samples, lays out and
draws them; it never receives pixels, colours or markup. Only rules that never
change live here (types, enums, sizes, finite numbers). Parsing an expression
and every rule that could change run in `display_board`
(`app/services/tools/plots.py`), so a stored card keeps replaying.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.prose import NOT_PROSE


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


Num = Annotated[float, Field(allow_inf_nan=False)]
# [min, max] on one axis, [a, b] for a domain, [x, y] for a vertex.
Pair = Annotated[list[Num], Field(min_length=2, max_length=2)]
Step = Annotated[float, Field(gt=0, allow_inf_nan=False)]
# A name ($f$, $\mathcal{C}_g$, $A$, « phase 2 »): it has to fit beside a curve at 400 px.
Label = Annotated[str, Field(min_length=1, max_length=24)]
AxisTitle = Annotated[str, Field(min_length=1, max_length=40)]
Caption = Annotated[str, Field(min_length=1, max_length=200)]
# Descriptions reach the model with the schema: the grammar is ours, not LaTeX, and
# the model would otherwise write `x²`, `\frac{1}{x}`, `1e-3` or `y = 2x + 1`.
Expr = Annotated[
    str,
    Field(
        min_length=1,
        max_length=120,
        description=(
            "En x ou t, pas du LaTeX : nombres à point décimal (pas de 1e-3), + - * / ^, 2x, "
            "sqrt cbrt abs exp ln log sin cos tan (radians), pi, e. Sans « y = »."
        ),
    ),
]
TermExpr = Annotated[
    str,
    Field(min_length=1, max_length=120, description="Terme général uₙ en n (pas de récurrence), écrit comme expr."),
]
Dot = Literal["none", "filled", "hollow"]

MAX_CURVES = 6
MAX_SEQUENCES = 3
MAX_POINTS = 20
MAX_LINES = 8
MAX_VERTICES = 30


class PlotCurve(_Model):
    expr: Annotated[Expr, NOT_PROSE]
    domain: Pair | None = None
    start_dot: Dot = "none"
    end_dot: Dot = "none"
    dashed: bool = False
    label: Label | None = None


class PlotSequence(_Model):
    expr: Annotated[TermExpr, NOT_PROSE]
    first: Annotated[int, Field(ge=0, le=1000)] = 1
    last: Annotated[int, Field(ge=0, le=1000)]
    label: Label | None = None


class PlotPoint(_Model):
    x: Num
    y: Num
    label: Label | None = None
    mark: Literal["filled", "hollow", "cross"] = "filled"
    guides: bool = False
    show_values: bool = False


class PlotLine(_Model):
    vertices: Annotated[list[Pair], Field(min_length=2, max_length=MAX_VERTICES)]
    dashed: bool = False
    label: Label | None = None


class PlotBlock(_Model):
    """A graph in a cartesian plane, drawn by the board in the given window: curves
    from their expression, sequences, points, broken lines. Never pixels."""

    # Required: a card's `drawing` reads a missing tag from its keys (board.py
    # `Drawing`), and refuses it for the missing tag.
    type: Literal["plot"]
    x_range: Pair
    y_range: Pair
    x_title: AxisTitle
    y_title: AxisTitle
    x_step: Step | None = None
    y_step: Step | None = None
    grid: bool = True
    orthonormal: bool = False
    curves: Annotated[list[PlotCurve], Field(max_length=MAX_CURVES)] = []
    sequences: Annotated[list[PlotSequence], Field(max_length=MAX_SEQUENCES)] = []
    points: Annotated[list[PlotPoint], Field(max_length=MAX_POINTS)] = []
    lines: Annotated[list[PlotLine], Field(max_length=MAX_LINES)] = []
    caption: Caption | None = None
