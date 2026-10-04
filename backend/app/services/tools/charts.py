"""The chart rules `display_board` applies (008 design 3.3).

These run in the tool, not on the card model: they could change (a tolerance, a
limit) and a stored card must keep replaying. Each refusal is a rule code for the
logs and a French message naming the field, handed back to the model to fix.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from app.domain.chart import (
    BarChart,
    BoxPlot,
    Chart,
    CumulativePolygon,
    Histogram,
    PieChart,
    StickChart,
)
from app.services.tools.text import spaced

Refusal = tuple[str, str]

# Each fréquence is rounded to its last digit, so the total may drift by half a
# unit of that digit per value: 0,333 × 3 is a fair 1.
_FREQUENCY_SLACK = 0.005
_PERCENT_SLACK = 0.5


def _n(value: float) -> str:
    """A number as the model wrote it, for a message: no trailing `.0`."""
    return f"{value:g}"


def _same_length(first: Sequence[object], first_name: str, values: Sequence[float], where: str) -> Refusal | None:
    if len(first) != len(values):
        return ("lengths", f"{where} : {len(first)} {first_name} pour {len(values)} valeurs ; il en faut autant.")
    return None


def _classes(bounds: Sequence[float], values: Sequence[float], where: str) -> Refusal | None:
    if len(bounds) != len(values) + 1:
        return (
            "lengths",
            f"{where} : {len(values)} classes demandent {len(values) + 1} bornes, il y en a {len(bounds)}.",
        )
    return _increasing(bounds, "bounds", where)


def _increasing(values: Sequence[float], field: str, where: str) -> Refusal | None:
    for before, after in zip(values, values[1:]):
        if after <= before:
            return (
                "order",
                f"{where} : {field} doit être strictement croissant ({_n(before)} puis {_n(after)}).",
            )
    return None


def _plain_labels(labels: Sequence[str], where: str) -> Refusal | None:
    for label in labels:
        if "$" in label:
            return (
                "label_math",
                f"{where} : « {label} » est une étiquette, écrite en texte simple, sans $…$.",
            )
    return None


def _distinct(categories: Sequence[str], where: str) -> Refusal | None:
    seen: set[str] = set()
    for label in categories:
        if spaced(label) in seen:
            return ("repeated", f"{where} : la catégorie « {label} » apparaît deux fois.")
        seen.add(spaced(label))
    return _plain_labels(categories, where)


def _is_number(label: str) -> bool:
    try:
        float(label.strip().replace(",", ".").replace("−", "-"))
    except ValueError:
        return False
    return True


def _qualitative(chart: BarChart, where: str) -> Refusal | None:
    """Bars are for a qualitative variable. Categories that are all numbers are the
    values of a discrete one, which the course draws as sticks on a number axis."""
    if all(_is_number(c) for c in chart.categories):
        return (
            "numeric_categories",
            f"{where} : les catégories sont des nombres, la variable est donc discrète ; "
            "trace un diagramme en bâtons (kind « sticks », les valeurs dans x).",
        )
    return None


def _counts(chart: BarChart | StickChart | Histogram | CumulativePolygon | PieChart, where: str) -> Refusal | None:
    values = chart.values
    if chart.measure == "effectif":
        for value in values:
            if value != math.floor(value):
                return (
                    "integers",
                    f"{where} : un effectif est un nombre entier ({_n(value)}). "
                    "Pour des fréquences, mets measure à « frequence » ou « pourcentage ».",
                )
    total = sum(values)
    if total == 0:
        return ("empty", f"{where} : toutes les valeurs sont nulles, il n'y a rien à dessiner.")
    if chart.measure == "frequence" and abs(total - 1) > _FREQUENCY_SLACK * len(values):
        return ("sum", f"{where} : des fréquences totalisent 1, celles-ci font {_n(round(total, 6))}.")
    if chart.measure == "pourcentage" and abs(total - 100) > _PERCENT_SLACK * len(values):
        return ("sum", f"{where} : des pourcentages totalisent 100, ceux-ci font {_n(round(total, 6))}.")
    return None


def _boxes(chart: BoxPlot, where: str) -> Refusal | None:
    for i, box in enumerate(chart.boxes):
        if not box.minimum <= box.q1 <= box.median <= box.q3 <= box.maximum:
            return (
                "box_order",
                f"{where}, boîte {i + 1} : il faut minimum ≤ q1 ≤ médiane ≤ q3 ≤ maximum.",
            )
    return _plain_labels([box.label for box in chart.boxes if box.label], where)


def _histogram(chart: Histogram, where: str) -> Refusal | None:
    if not chart.bars and chart.polygon == "none":
        return ("layers", f"{where} : sans rectangles, un histogramme doit au moins tracer son polygone.")
    amplitudes = [b - a for a, b in zip(chart.bounds, chart.bounds[1:])]
    if chart.reference_amplitude is not None and all(
        math.isclose(a, amplitudes[0], rel_tol=1e-9) for a in amplitudes
    ):
        return (
            "reference",
            f"{where} : les classes ont toutes la même amplitude ; "
            "n'indique reference_amplitude que pour des classes inégales.",
        )
    return None


def chart_refusal(chart: Chart, path: str) -> Refusal | None:
    """The first rule the chart breaks, as (rule, message), or None. Within a kind,
    the shape comes first: every later rule reads the lists pairwise."""
    where = f"Le graphique {path}"
    match chart:
        case BarChart():
            return (
                _same_length(chart.categories, "catégories", chart.values, where)
                or _distinct(chart.categories, where)
                or _qualitative(chart, where)
                or _counts(chart, where)
            )
        case PieChart():
            return (
                _same_length(chart.categories, "catégories", chart.values, where)
                or _distinct(chart.categories, where)
                or _counts(chart, where)
            )
        case StickChart():
            return (
                _same_length(chart.x, "valeurs de x", chart.values, where)
                or _increasing(chart.x, "x", where)
                or _counts(chart, where)
            )
        case Histogram():
            return _classes(chart.bounds, chart.values, where) or _counts(chart, where) or _histogram(chart, where)
        case CumulativePolygon():
            return _classes(chart.bounds, chart.values, where) or _counts(chart, where)
        case BoxPlot():
            return _boxes(chart, where)
    return None


def charts_refusal(charts: Sequence[tuple[str, Chart]], exercise: bool = False) -> Refusal | None:
    """The first rule a card's charts break. How many drawings a card holds is
    `display_board`'s cap, across every family.

    An exercise's chart is on the board while the exercise is open, so it may not
    write its values: they are what a reading exercise asks for (R5.1). The one
    place the tool can tell; elsewhere the prompt carries the rule."""
    if exercise:
        for path, chart in charts:
            if chart.show_values:
                return (
                    "exercise_values",
                    f"Le graphique {path} accompagne un exercice ouvert : show_values reste à false, "
                    "sinon il donne la réponse. Les valeurs viendront avec la correction.",
                )
    for path, chart in charts:
        if refusal := chart_refusal(chart, path):
            return refusal
    return None
