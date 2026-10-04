"""Chart blocks (008 design 4.1).

A chart is statistics, never geometry: the board draws it from categories, values
or class bounds and their counts, and computes nothing a course defines its own
way. Only rules that never change live here (types, enums, bounds, non-negative
values); the rules that could (lengths, order, sums) run in `display_board`, so a
stored card keeps replaying (R4.7).
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


Value = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Coord = Annotated[float, Field(allow_inf_nan=False)]
Label = Annotated[str, Field(min_length=1, max_length=40)]
AxisTitle = Annotated[str, Field(min_length=1, max_length=80)]
Caption = Annotated[str, Field(min_length=1, max_length=200)]
Measure = Literal["effectif", "frequence", "pourcentage"]
# `left` is [a ; b[, `right` is ]a ; b].
Closed = Literal["left", "right"]

MAX_POINTS = 20
MAX_SECTORS = 8
MAX_BOXES = 4


class _Shown(_Model):
    show_values: bool = False
    caption: Caption | None = None


class _Counts(_Shown):
    measure: Measure


class BarChart(_Counts):
    kind: Literal["bars"] = "bars"
    categories: Annotated[list[Label], Field(min_length=1, max_length=MAX_POINTS)]
    values: Annotated[list[Value], Field(min_length=1, max_length=MAX_POINTS)]
    x_title: AxisTitle | None = None
    y_title: AxisTitle


class StickChart(_Counts):
    kind: Literal["sticks"] = "sticks"
    x: Annotated[list[Coord], Field(min_length=1, max_length=MAX_POINTS)]
    values: Annotated[list[Value], Field(min_length=1, max_length=MAX_POINTS)]
    polygon: bool = False
    x_title: AxisTitle
    y_title: AxisTitle


class _Classes(_Counts):
    """A grouped series: n classes between n + 1 bounds."""

    bounds: Annotated[list[Coord], Field(min_length=2, max_length=MAX_POINTS + 1)]
    # Descriptions reach the model with the schema: a pack may list the heights or
    # the cumulated points of the course's chart, and either would be drawn wrong.
    values: Annotated[
        list[Value],
        Field(
            min_length=1,
            max_length=MAX_POINTS,
            description="Un effectif ou une fréquence par classe, tel quel : ni cumulé, ni une hauteur de rectangle.",
        ),
    ]
    closed: Closed
    x_title: AxisTitle
    y_title: AxisTitle


class Histogram(_Classes):
    kind: Literal["histogram"] = "histogram"
    reference_amplitude: Annotated[
        float,
        Field(
            gt=0,
            allow_inf_nan=False,
            description="Pour des classes d'amplitudes inégales : le tableau calcule lui-même les hauteurs.",
        ),
    ] | None = None
    bars: bool = True
    polygon: Literal["none", "open", "closed"] = "none"


class CumulativePolygon(_Classes):
    kind: Literal["cumulative"] = "cumulative"
    direction: Literal["increasing", "decreasing"]


class PieChart(_Counts):
    kind: Literal["pie"] = "pie"
    categories: Annotated[list[Label], Field(min_length=1, max_length=MAX_SECTORS)]
    values: Annotated[list[Value], Field(min_length=1, max_length=MAX_SECTORS)]


class Box(_Model):
    label: Label | None = None
    minimum: Coord
    q1: Coord
    median: Coord
    q3: Coord
    maximum: Coord


class BoxPlot(_Shown):
    kind: Literal["box"] = "box"
    boxes: Annotated[list[Box], Field(min_length=1, max_length=MAX_BOXES)]
    x_title: AxisTitle | None = None


Chart = Annotated[
    Union[BarChart, StickChart, Histogram, CumulativePolygon, PieChart, BoxPlot],
    Field(discriminator="kind"),
]


class ChartBlock(_Model):
    """A statistical chart drawn by the board from data. Give statistics, never
    coordinates or drawings."""

    type: Literal["chart"] = "chart"
    chart: Chart
