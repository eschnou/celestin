# 009 — The `figure` block (geometry, number lines, sets): design

Sections 1 to 6 are the design as it was reviewed on 28 September 2026, kept as written:
it is what the code comments cite. Where the code now differs, a note marked **As built** says
so in place, and section 7 lists every deviation. The scratchpad paths the design mentions
(prototypes, fuzz scripts) were never part of the repository.

## 1. Summary

Revised design for a `figure` block, `{"type": "figure", "figure": {"kind": …}}`, built on the spec 008 template. `figure` is a discriminated union on `kind` with three sub-kinds: `plane` (geometry), `number_line` and `sets`. I prototyped it in the scratchpad (`…/scratchpad/proto/figproto/figure.py`, `rules.py`, `slots_final.py`). The schema is 6 992 characters, measured the way `board_declarations.json` is dumped. 23 rule cases pass, and every Venn slot below was checked numerically at the 294 px drawing width of a 400 px board.

Every blocking point from the critique is fixed:

1. **Labels no longer wrap at the right edge.** Each positioned label span gets `w-max whitespace-nowrap`. The box is then max-content wide, whatever RichText's inner `whitespace-pre-wrap`.
2. **Sets are laid out by their content and fit at 400 px.**
   - Overlap and separate diagrams use fixed zone slots. Their px sizes at 294 px are a verified table: overlap-2 gives 70 px × 4 rows per zone; overlap-3 gives 46–141 px × 2 rows.
   - Nested sets are rounded rectangles offset to the lower-left. Each ring gets a label band 20 px high, plus a right band exactly as wide as its widest element; the height grows with the content.
   - Elements flow in HTML slots (flex-wrap, so no pixel guessing). The layout width is clamped between 294 and 400 px, and a narrower board scales the whole drawing down with a CSS transform.
   - `crowded` is now a capacity check that mirrors the layout: greedy row packing of estimated text widths per zone, and the nested width budget. Python and TS are pinned to one shared JSON case table, like `path_cases.json`.
3. **The angle codage tells the truth.** Only `marks` ≥ 1 draws arcs, and the same arcs mean the same amplitude within 1°. An unmarked angle is a tinted sector, each in its own colour, at most 5 per figure. Two unmarked angles never look coded alike.
4. **One zone meaning for every layout.** `within` lists the sets the element is in, and only those. The sets containing them count automatically, so in a nested diagram the zone is the ring of the deepest listed set. The note, the rules and the tests now agree.
5. **The number line writes true notation.** Intervals sharing a label are one set: one colour, one lane, one notation `S = ]−∞ ; 2] ∪ ]5 ; +∞[`. A new rule `union` refuses pieces that overlap or touch. Every labelled set gets its own lane with its own label row. Number labels below the axis are staggered with charts' `lanes()`.
6. **Axes always go through the origin.** The tool refuses a given range without 0 when `axes` is set (`window`), and the renderer grows the range defensively.
7. **Point marking follows the course.** `marker: "cross" | "dot"` (default cross). `ends` became `convention: "brackets" | "dots" | "hatched"`, which adds the FWB « on hachure ce qui ne convient pas ».

Improvements adopted:
- `label_notation`: coordinates or an interval written by hand in a label or caption are refused everywhere, because the board writes them itself.
- `measure`: an angle label in degrees must match the angle; length labels must be proportional to the drawn lengths.
- Arcs are always the minor arc, so the counter-clockwise order is gone.
- The degenerate threshold is 2 % of the span, and a new rule `crossed` catches bow-tie polygons.
- Integer degrees in messages; separate fixture exports; `Math as Tex`.
- Traced strokes are `<path>` with `pathLength` only when traced; vectors and dashed strokes do not trace.
- Label directions are computed in screen space, with a NaN guard.
- `sets` is a list of `{id, label}`, so the order is explicit.
- The tool module is `app/services/tools/figure.py`, per the ownership rule.

> **As built.** The module is `app/services/tools/figures.py`, like `charts.py` (§7, item 1).

Every label accepts `$…$`: an HTML label layer over the pixel-width SVG typesets it with RichText and KaTeX, so chart deviation D10 is not repeated.

## 2. Model: `app/domain/figure.py`

File: backend/app/domain/figure.py (prototyped verbatim in scratchpad/proto/figproto/figure.py; FigureBlock schema = 6 992 chars measured as the fixture dumps it: json.dumps(..., ensure_ascii=False, sort_keys=True), pydantic 2.13.5).

```python
"""Figure blocks: geometry, number lines and diagrams of sets on the board.

A figure is drawn from what the course would say about it: named points in the
figure's own units and the shapes joining them, a number line and its
intervals, or sets and what they hold. The model never gives pixels, colours or
drawing commands; the board scales, lays out and writes the notation itself
(decimal comma, `]a ; b[`, `A(2 ; 3)`).

Only rules that never change live here (types, enums, sizes, finite numbers, how
a point is named); the rules that could (references, how many points a shape
takes, degenerate shapes, the codage, the window, what fits on the board) run in
`display_board` (`app/services/tools/figure.py`), so a stored card keeps
replaying. The one docstring is `FigureBlock`'s: docstrings and descriptions
become tool-schema text in the cached prompt prefix.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from app.domain.chart import Caption, Coord, Label


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
    of: Annotated[list[PointName], Field(min_length=1, max_length=MAX_VERTICES, description=_OF)]
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
    id: SetId
    label: Label


class SetElement(_Model):
    text: Label
    within: Annotated[
        Zone,
        Field(description="Les ensembles où il se trouve, et eux seuls (ceux qui les contiennent comptent d'office) ; [] : hors de tous."),
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
            description="Zones hachurées, chacune écrite comme within ; hachurer un ensemble entier, c'est hachurer chacune de ses zones.",
        ),
    ] = []
    caption: Caption | None = None


Figure = Annotated[Union[PlaneFigure, NumberLine, SetDiagram], Field(discriminator="kind")]


class FigureBlock(_Model):
    """A figure the board scales and draws: plane geometry in the figure's own
    units (y up), a number line, or a diagram of sets. Give points and relations,
    never pixels, colours or drawings."""

    type: Literal["figure"] = "figure"
    figure: Figure
```

Notes for the implementer (not part of the file):
- Changes from the first version:
  - `marker` added on PlaneFigure;
  - `ends` replaced by `convention` (brackets | dots | hatched);
  - `sets` is a list of `FigureSet {id, label}`, so order (outer to inner, colour by index) is explicit and survives any JSONB migration;
  - the arc has no ccw order (the board draws the minor arc);
  - the `within` and `shade` descriptions pin a single zone meaning.
- One zone meaning for every layout: an element or zone lies in every set it lists, in every set containing one of those (implicit), and in no other set.
  - overlap: `["A"]` is A∖B; `["A","B"]` is A∩B.
  - nested (sets outermost first): the zone is the ring of the deepest listed set, so `["Z"]` is Z∖N and `["N","Z","Q"]` is N.
  - For nested, `shade [["Z"],["N","Z"]]` is two different zones (Z∖N and N), while `[["N"],["N","Z"]]` repeats one.
- Class names are prefixed (FigureShape, FigureSet, LineInterval, LineMark, SetElement, SetDiagram, PlaneFigure, NumberLine) to avoid `$defs` and re-export collisions with the sibling plot and flowchart blocks.
- Dict keys (point names) cannot be integer-like, so JS `JSON.parse` keeps their order. Nothing depends on point order anyway.
- A bad point name is refused with loc `('figure','plane','points','AB','[key]')` and type `string_pattern_mismatch`. The loc contains "figure", so the generalised `log_schema_refusal` counts it.

> **As built.** `FigureShape.of`, `FigureSet.id`, `SetElement.within` and `SetDiagram.shade`
> carry the `NOT_PROSE` marker (`app/domain/prose.py`), so the board's string checks read them as
> names, not prose; `kind`, `draw` and the other Literal fields are never prose. The generalised
> `log_schema_refusal` reads the family only at the union tag's fixed place in the loc (right
> after `blocks, <i>` or after `drawing`), so a point the model called « chart » cannot
> miscount it.

## 3. Tool rules: `app/services/tools/figures.py`

### 3.1 Module and signatures

Prototyped in scratchpad/proto/figproto/rules.py; 23 sample cases pass, including every boundary case listed under tests.

**Signatures** (board.py calls figures_refusal):
```python
Refusal = tuple[str, str]
MAX_FIGURES_PER_CARD = 2

def figure_refusal(figure: Figure, path: str) -> Refusal | None:
    """The first rule the figure breaks, as (rule, message), or None."""   # where = f"La figure {path}"; match PlaneFigure / NumberLine / SetDiagram

def figures_refusal(figures: Sequence[tuple[str, Figure]], exercise: bool = False) -> Refusal | None:
    """exercise_values (exercise only), then per_card, then figure_refusal per figure in card order."""

def text_px(text: str) -> int:   # public: the capacity estimate, pinned by the shared case table
```

> **As built.** `app/services/tools/figures.py`, with `figures_refusal(items, card, ctx)` (the
> exercise rule reads the card) and `figures_summary`; `figure_refusal(figure, path)` stays
> public. There is no `per_card` and no `MAX_FIGURES_PER_CARD` (§7, item 22).

### 3.2 Constants

- `_RIGHT_SLACK_DEG = 1.0`, `_ANGLE_SLACK_DEG = 1.0`, `_LENGTH_SLACK = 0.02`, `_WINDOW_SLACK = 0.02`.
- `_MIN_GAP = 0.02`: 2 % of the span, about 5 px on a 400 px board. Distinct points closer than this, a radius smaller than this, or a flat polygon within it are unreadable.
- `_SAME = 1e-9`: coincident within 1e-9 × span. `span` = max(x extent, y extent) of the points and each circle's centre ± r, or 1 if that is 0.
- `_MIN_ANGLE_DEG = 0.5`, `_MAX_UNMARKED_ANGLES = 5`.
- `_ARITY`: segment/line = 2 « 2 points »; ray = 2 « 2 points (l'origine, puis un point) »; vector = 2 « 2 points (l'origine, puis l'extrémité) »; polygon = 3..12 « de 3 à 12 sommets »; circle = 1..2 « le centre, ou le centre puis un point du cercle »; arc = 3 « 3 points (une extrémité, le centre, l'autre extrémité) »; angle and right_angle = 3 « 3 points (A, B, C pour l'angle en B) ».
- Geometry:
  - amplitude of angle ABC at B = degrees(acos(clamp(u·v/|u||v|, −1, 1))), with u = A − B and v = C − B, computed only after the coincidence checks;
  - flat polygon: every vertex lies within `_MIN_GAP·span` of the line through its two farthest vertices;
  - crossed polygon: two non-adjacent edges properly intersect (orientation test d1·d2 < 0 and d3·d4 < 0).
- Notation regexes, applied to the raw label:
  - `_INTERVAL = r"[\[\]]\s*(?:[−-]\s*)?(?:\d|∞|\\infty)[^;\[\]]*;[^\[\]]*[\[\]]"`
  - `_COORDS = r"\(\s*[−-]?\s*\d[\d,.]*\s*;\s*[−-]?\s*\d[\d,.]*\s*\)"`
  - `[AB]` and `]AB)` have no « ; », so they pass.
- Measure regexes, applied to `_bare(label)`, which drops `$`, maps `^\circ` / `^{\circ}` to °, unwraps `\text{}` and removes `\,` `\;` `~` and whitespace:
  - `_DEGREES = r"^(\d+(?:[.,]\d+)?)°$"`
  - `_LENGTH = r"^(\d+(?:[.,]\d+)?)(mm|cm|dm|m|km)?$"`, converted to mm when a unit is given.
- Capacity at the smallest board (400 px board, 294 px drawing). These are the contract with venn.ts, pinned by `tests/fixtures/figure/capacity.json`:
  - `BOARD_PX = 294`, `MARGIN_PX = 14`, `ROW_PX = 18`, `GAP_PX = 6`, `CHAR_PX = 7`, `GLYPH_PX = 9`, `MAX_PER_ZONE = 6`.
  - `NESTED = {label_row: 20, gap: 6, band_min: 20, band_pad: 12, inner_min: 40, label_pad: 16}`.
  - `SLOTS` (zone as sorted set indices → (width px, rows)):
    - overlap2: 0 → (70, 4), 1 → (70, 4), 01 → (70, 4);
    - overlap3: 0 → (77, 2), 1 → (77, 2), 2 → (141, 2), 01 → (53, 2), 02 → (46, 2), 12 → (46, 2), 012 → (70, 2);
    - separate2: each (84, 5); separate3: each (54, 3);
    - outside ([]): (260, 2).
  - `text_px(text)`: 7 px per prose character, plus 9 px per maths glyph. Maths is found with the same `$…$` regex as board.py and RichText. Inside it, a `\command` counts as 1 glyph, and `{ } ^ _` and whitespace count 0. So « Diviseurs de 12 » = 105, `$\mathbb{N}$` = 18, `$\frac{1}{3}$` = 27.

    > **As built.** Whitespace is JavaScript's `\s` on both sides (`JS_SPACE` and `MATH` in
    > `app/services/tools/text.py`), pinned by four capacity cases (§7, item 16).

  - `_rows(widths, slot)`: greedy flow, the same packing flex-wrap does. It returns None when one element is wider than the slot.

Numbers in messages: `f"{round(v, 2):g}"`. Angles are always integer degrees, `f"{round(v)}°"`, so C = (1 ; 3) gives « 72° ». When two shapes are named, they are named in ascending index order. The text is for the model, not the student.

### 3.3 Order

- plane: empty → window → close_points → per shape (arity → repeated → unknown_point → field → circle → degenerate → crossed → not_right → arc_radius) → codage → measure → outside → label_notation.
- number_line: empty → per interval (order → infinite_bound) → union → marks repeated → label_notation.
- sets: repeated ids → set_count → per zone, elements then shade (unknown_set → repeated → region → universe) → shade repeated → crowded → caption label_notation.

> **As built.** `scale` runs after `window` on a plane and after `empty` on a number line;
> `blank` runs after the repeated-id check on sets (§7, items 14 and 15). `per_card` is gone.

The path in every message is `blocks[i]` or `drawing`.

### 3.4 Rule table

| code | applies to | refused when | French message template |
|---|---|---|---|
| exercise_values | plane or number_line as the drawing of an `exercise` | `show_values` true | « La figure {path} accompagne un exercice ouvert : show_values reste à false, sinon le tableau écrit la réponse (coordonnées, intervalles). Elles viendront avec la correction. » |
| per_card | a card | more than 2 figures | « Une carte porte au plus 2 figures ; répartis les autres sur une carte suivante. » |
| empty | plane | no points and neither axes nor grid | « La figure {path} : la figure est vide ; donne des points, ou axes ou grid pour un repère. » |
| window | plane x_range / y_range | min ≥ max; or `axes` is set and the range excludes 0 | « La figure {path} : x_range va du plus petit au plus grand (5 puis 0). » / « La figure {path} : avec axes, x_range contient 0, l'origine du repère (2 à 8). » |
| close_points | plane points | two distinct names with 1e-9·span < distance < 2 % of span | « La figure {path} : A et B sont presque au même endroit et se confondraient au tableau ; donne-leur les mêmes coordonnées ou écarte-les. » |
| arity | shape | wrong number of points in `of` | « La figure {path}, shapes[{i}] (segment) : of attend 2 points, il y en a 3. » (wording from _ARITY) |
| repeated | shape.of | a name appears twice | « …, shapes[{i}] (polygon) : « A » apparaît deux fois dans of. » |
| unknown_point | shape.of | a name is missing from points | « …, shapes[{i}] (segment) : le point « D » n'est pas dans points. » |
| field | shape | radius on a non-circle; marks > 0 on anything but a segment or an angle | « … : radius ne sert qu'à un cercle. » / « … : marks (le codage) ne sert qu'à un segment ou un angle. » |
| circle | circle | one point without radius, or two points with radius | « … : un cercle se donne par son centre et radius, ou par son centre et un point du cercle ; pas les deux, ni aucun. » |
| degenerate | any shape | two of its points coincide; a flat polygon; an angle < 0,5° or > 179,5°; a given radius < 2 % of span | « … : A et D sont au même endroit, le tracé est vide. » / « … : les sommets sont alignés, le polygone est plat. » / « … : l'angle en B est nul ou plat, il n'y a rien à marquer. » / « … : le cercle est trop petit pour se voir. » |
| crossed | polygon | two non-adjacent sides intersect (a bow-tie) | « …, shapes[{i}] (polygon) : des côtés se croisent ; donne les sommets dans l'ordre du tour. » |
| not_right | right_angle [A, B, C] | abs(amplitude − 90°) > 1° | « …, shapes[{i}] (right_angle) : l'angle en B mesure 72° ; le codage d'angle droit serait faux. Corrige les coordonnées ou retire ce codage. » |
| arc_radius | arc [A, O, B] | abs(OA − OB) > 2 % of the larger | « …, shapes[{i}] (arc) : A et B doivent être à la même distance du centre O (3 et 3.5). » |
| codage | segments sharing marks ≥ 1; angles sharing marks ≥ 1; unmarked angles | longest − shortest > 2 % of the longest; amplitudes differ by more than 1°; more than 5 angles with marks 0 | « La figure {path} : shapes[0] et shapes[1] portent le même codage mais mesurent 4 et 3 ; un même codage dit « de même longueur ». » / « … mesurent 40° et 55° ; un même codage dit « de même amplitude ». » / « … : 6 angles sans codage ; le tableau en distingue 5 au plus. Code les angles égaux avec marks, ou répartis la figure. » |
| measure | a label on an angle or right_angle that reads as degrees; labels on 2 or more segments that read as lengths | the degrees differ from the amplitude by more than 1°; the length / drawn-length ratios differ by more than 2 % (compared within the same unit class: with units, in mm; or unitless) | « …, shapes[{i}] (angle) : l'étiquette dit 40° mais l'angle en B mesure 45° au tableau ; corrige les coordonnées ou l'étiquette. » / « La figure {path} : les longueurs écrites sur shapes[0] et shapes[1] ne sont pas dans le rapport des longueurs tracées ; le tableau trace à l'échelle, corrige les coordonnées ou les étiquettes. » |
| outside | plane with a given range | a point, or a circle's centre ± r, is beyond the range ± 2 % of its span | « … : le point B (4 ; 0) sort de x_range (0 à 3) ; agrandis la fenêtre ou ne la donne pas. » / « …, shapes[{i}] (circle) : le cercle sort de y_range ; agrandis la fenêtre ou ne la donne pas. » |
| label_notation | plane shape labels, number_line interval and mark labels, every caption (set elements are exempt) | `_INTERVAL` or `_COORDS` matches | « La figure {path} : « $(2 ; 3)$ » écrit des coordonnées ou un intervalle à la main ; le tableau les écrit lui-même dans la notation du cours avec show_values (hors exercice). Retire-les de l'étiquette. » |
| empty | number_line | no intervals and no marks | « La figure {path} : la droite graduée est vide ; donne des intervals ou des marks. » |
| order | interval | start == end; start > end | « …, intervals[{i}] : [2 ; 2] est un seul nombre ; place-le dans marks. » / « …, intervals[{i}] : start (5) doit être plus petit que end (2). » |
| infinite_bound | interval | start null with closed both/left; end null with closed both/right | « …, intervals[{i}] : −∞ n'est jamais compris ; closed vaut « right » ou « neither ». » (and the mirror for +∞) |
| union | intervals with the same (stripped) label | sorted by start, two consecutive pieces overlap, or touch at a bound that either piece includes. ]−∞ ; 2[ ∪ ]2 ; 5] is allowed; ]−∞ ; 2] ∪ ]2 ; 5] is not | « La figure {path} : intervals[0] et intervals[1] portent l'étiquette « $S$ » et se touchent ou se chevauchent ; ils forment un seul intervalle, donne-le d'un seul tenant. » |
| repeated | number_line marks | the same x twice | « …, marks : 1 apparaît deux fois. » |
| repeated | sets | an id twice | « …, sets : l'ensemble « A » apparaît deux fois. » |
| set_count | overlap / separate | not 2 or 3 sets | « La figure {path} : layout « overlap » dessine 2 ou 3 ensembles, il y en a 4 ; des ensembles inclus l'un dans l'autre sont « nested ». » |
| unknown_set | element.within, shade[k] | an id missing from sets | « …, elements[{i}] : l'ensemble « C » n'est pas dans sets. » |
| repeated | a zone; shade | an id twice in one zone; the same normalised zone shaded twice (nested: deepest set; others: the set of indices) | « …, elements[{i}] : « A » apparaît deux fois. » / « …, shade[{k}] : cette zone est déjà hachurée. » |
| region | separate | a zone listing 2 or more sets | « …, elements[{i}] : en layout « separate », les ensembles sont disjoints ; une zone est dans un seul. » |
| universe | zone [] | no universe | « …, elements[{i}] : [] est hors de tous les ensembles ; donne universe, le cadre qui les contient. » |
| crowded | sets | the capacity check below | « La figure {path} : {what} ne tient pas au tableau ; raccourcis les textes, un élément par entrée, ou mets le détail dans caption. » where {what} is « la zone [A, B] », « la zone [A] (plus de 6 éléments) », « la zone hors des ensembles », « la ligne des noms d'ensembles », « l'emboîtement (des éléments trop longs dans les anneaux) », « l'étiquette de « Z » » or « universe » |

> **As built.**
>
> - `per_card` is removed: `display_board` caps a card at two drawings of any family before the
>   families run (`drawing_refused`, rule `per_card`), so a figure limit could never fire
>   (verification #10).
> - `label_notation` reads the label through `_bare` (LaTeX spacing, `{,}`, `\left(`, `\degree`…
>   folded), and both bounds must start like a number (§7, item 12).
> - Two rules were added: `scale` (a number beyond ±1e6, or a figure under 0,001 across) and
>   `blank` (a set label, an element or the universe made only of spaces) (§7, items 14 and 15).

### 3.5 Capacity check (`_fits`)

1. Group elements by normalised zone. Any zone with more than 6 elements is refused.
2. `text_px(universe)` must be ≤ 266 px.
3. Zone [] must fit the outside slot (260 px × 2 rows).
4. Nested:
   - bands[i] = max(20, widest element of ring i + 12), for i < n − 1;
   - inner = max(label_{n−1} + 16, widest inner element + 12, 40);
   - Σbands + (n − 1)·6 + inner must be ≤ 266;
   - each label_i + 16 must be ≤ 266 − Σbands[:i] − i·6.
   Height is not limited, because it grows with the content.
5. Overlap and separate:
   - the label row holds sets A and B (for overlap-3, C's label goes below C). Σ widths + 12·(count − 1) must be ≤ 266;
   - every zone's elements must flow into `SLOTS[layout+n][zone]`.

On the prototype:
- VALID.sets (overlap-2 with 8 elements), a 5-level ℕ ⊂ ℤ ⊂ 𝔻 ⊂ ℚ ⊂ ℝ nested diagram with √2, π, 1/3, 0,5, −3, 0 and 7, and population ⊃ échantillon ⊃ individu all pass.
- « 1 ; 2 ; 3 ; 6 ; 9 ; 18 ; 24 » in A∩B is refused, as are 7 elements in A and four long ring lists in the nested diagram.

### 3.6 No rule needed for

- `$` in labels: every label goes through RichText in the HTML layer.
- LaTeX outside `$…$`: the existing `_bare_commands` walks every label, set label, element, universe and caption. `id`, `kind` and `type` are skipped by `_NOT_PROSE`, and point names cannot hold a backslash.

> **As built.** `_bare_commands` and `_NOT_PROSE` are gone: the string checks run in
> `display_board` on the parsed card, fields that are not prose carry `NOT_PROSE`, and a refusal
> inside a figure is logged as `figure_refused` with rule `string_control`, `string_latex` or
> `string_script`.

- The window's aspect ratio: the renderer only grows the window.

### 3.7 Card level and logging

`exercise_values` lives in `figures_refusal`, mirroring `charts_refusal`, unless the lead unifies it in board.py.

**Logging (board.py).** `figure_refused` {user_id, chapter_id, mode, rule} and `figure_displayed` {…, kinds: ["plane", "sets"]}. They carry ids and codes only, never a label, name, coordinate or element. Schema refusals are counted by the generalised `on_invalid` as `figure_refused` with rule `schema.<pydantic type>`.

## 4. Rendering: `frontend/src/components/celestin/figure/`

### 4.1 Files

Pure helpers are `.ts` files; `.tsx` files export components only, so there are no new only-export-components warnings. Every `.tsx` imports `{ Math as Tex } from "../math"`, so the global `Math` is never shadowed, and all arithmetic lives in the `.ts` files.

- `figure-view.tsx`: `FigureView = memo(({ block }: { block: FigureBlock }) => …)`. It sanitises once, dispatches on the kind, and holds the frame, caption, role=img and the sr-only list.
- `plane.tsx` (PlaneDrawing), `number-line.tsx` (NumberLineDrawing), `sets.tsx` (SetDrawing): each is one SVG plus a `LabelLayer`.
- `label-layer.tsx`: `LabelLayer({ labels, flows })`.
- `labels.ts`: `textPx`, `visibleText`, `anchorTransform`, `clampAnchor`, `spreadRow`, `flowRows`.
- `geometry.ts`: planeWindow, gridStep, labelStep, fitWindow, clipToWindow, minorArc, angleMark, labelDirection, groupPoints, nameTex, coordinates.

> **As built.** `coordinates` is gone: coordinates are written by `formatPair` in
> `charts/format.ts`, and interval notation by its `formatInterval` / `formatBound`, shared
> with charts and plots. Extra pure modules: `plane-scene.ts`, and `venn.ts` exports more
> (§7, items 7 and 23).

- `line.ts`: lineRange, groups, lanes, intervalNotation, bracketPath, complement.
- `venn.ts`: VENN constants and slot geometry, overlapLayout, separateLayout, nestedLayout, `fits`.
- `sanitise.ts` (total) and `describe.ts` (French).
- Reused read-only from `../charts/`: `formatNumber` (format.ts), `niceTicks` and `linear` (scale.ts), `useWidth` (use-width.ts), `lanes` (axes.tsx).
- No new CSS, tokens or dependency. Colours are `--chart-1…8`, `--foreground`, `--muted-foreground`, `--border` and `--card`, all already registered as Tailwind colours. The only animation is the existing `chart-trace`.

### 4.2 FigureView

```tsx
<figure className="rounded-lg border border-border bg-card px-5 py-4">
  <div ref={ref} role="img" aria-label={ariaLabel(fig)} aria-describedby={`${uid}-desc`}>
    {fig ? <Drawing figure={fig} width={width} uid={uid} /> : <p className="py-8 text-center text-sm text-muted-foreground">Figure vide</p>}
  </div>
  {fig?.caption && <figcaption className="mt-3 text-center text-xs text-muted-foreground"><RichText text={fig.caption} /></figcaption>}
  <ul id={`${uid}-desc`} className="sr-only">{describe(fig).map((l, i) => <li key={i}>{l}</li>)}</ul>
</figure>
```
- `width = useWidth(ref)`; `fig = useMemo(() => sanitise(block.figure), [block.figure])`.
- `uid = "fig" + useId().replace(/[^A-Za-z0-9_-]/g, "")`, so clipPath, mask and pattern ids are unique even with two figures on a card, or the hidden discussion board mounted beside the lesson.
- `RichText` is imported from "../board-blocks": the same render-time-only cycle as charts.

### 4.3 How `$…$` labels are typeset

An HTML layer over the SVG, not foreignObject.

- Each drawing is `<div className="relative" style={{width, height}}><svg width height aria-hidden className="overflow-visible">…</svg><LabelLayer …/></div>`.
- The layer is `<div aria-hidden className="pointer-events-none absolute inset-0 text-xs leading-none text-foreground">`.
- Point labels are `<span className="absolute w-max whitespace-nowrap" style={{ left: x, top: y, transform: anchorTransform(dir) }}>`.
  - `w-max` (width: max-content) is what stops wrapping. An absolutely positioned box would otherwise shrink to fit (layer width − left), and RichText's inner `whitespace-pre-wrap` spans would then wrap at every space near the right edge.
  - Contents: point names via `<Tex tex={nameTex(n)} />`, model text via `<RichText>`, and our coordinate text as plain text.
  - An optional closed colour class (`text-chart-1`…) comes from our code.
- Zone flows (sets):
  - a zone is `<div className="absolute flex flex-wrap content-center items-center justify-center gap-x-1.5 leading-[18px]" style={{ left, top, width, height }}>`, with `flex-col flex-nowrap` for the nested ring columns;
  - each element is `<span className="w-max shrink-0 whitespace-nowrap"><RichText text={t} /></span>`;
  - flex-wrap does the same greedy packing as the tool's `_rows`, and a single element is centred by `justify-center`.
- `anchorTransform([dx, dy])`:
  - dir is in SCREEN space (y down) and already normalised;
  - with m = max(|dx|, |dy|): m < 1e-6 gives "translate(-50%,-50%)", otherwise `translate(${-50 + 50·dx/m}%, ${-50 + 50·dy/m}%)`;
  - so (1, 0) puts the box to the right, vertically centred, and (0, −1) puts it above;
  - any non-finite input falls back to the centred transform, so NaN never reaches the style.
- `clampAnchor(x, y, dir, w, h, W, H)`: w = textPx(label), h = 16. It shifts the anchor so the translated box stays inside [0, W] × [0, H].
- `textPx` is the same formula as Python `text_px`: 7 px per prose character, 9 px per maths glyph, pinned by the shared case table.
- Why not foreignObject:
  1. The card animates in with `board-enter` (a transform), and WebKit mispositions and clips foreignObject under transformed ancestors.
  2. foreignObject needs an explicit box, and KaTeX's size is unknown before layout; the %-translate needs no measurement.
  3. Drawings are pixel-width, so SVG units are CSS px and the overlay lines up exactly.
  4. The SVG stays purely geometric, and model strings reach the DOM only as React text or KaTeX with trust:false.
- This lifts D10 for figures.

### 4.4 Plane (`geometry.ts`, then `plane.tsx`)

1. `planeWindow(fig)`:
   - Content values:
     - the points;
     - each circle's centre ± r (r = radius, or the distance from the centre to the through point);
     - each arc's endpoints plus the cardinal points of its circle (0, π/2, π, 3π/2) inside its MINOR sweep;
     - 0 on both axes when `axes` is set.
   - Default, with no content and no ranges: [−5 ; 5] on both axes.
   - m = 0,1·max(spanX, spanY), or 1 when both spans are 0. Each axis without a range is [min − m, max + m].
   - A given range is GROWN, never shrunk, to cover content beyond it (plus 2 % of its span on that side) and 0 when `axes` is set. The tool refuses gross misses (outside, window); this is the defensive replay path.
   - Aspect: if h < 0,25·w, grow y symmetrically to 0,25·w; if h > 1,5·w, grow x to h/1,5.
   - With axes or grid, snap outward to multiples of `gridStep`.
2. `gridStep(w, h)`: L = max(w, h). If 4 ≤ L ≤ 20, the step is 1 (the course's quadrillage); otherwise it is the `niceTicks(0, L, 10)` step (0,2 for L = 2; 5 for L = 50).
3. `fitWindow(win, W)`:
   - M = 20 px of label room, Hmax = min(1,1·W, 400);
   - s = min((W − 2M)/w, (Hmax − 2M)/h), one scale for both axes (orthonormal);
   - height = round(h·s + 2M), offX = (W − w·s)/2;
   - `px(x, y) = [offX + (x − x0)·s, M + (y1 − y)·s]`.
   - At W = 294, a 4,8 × 3,6 window (a 4-by-3 triangle) is 52,9 px per unit and 230 px tall.
4. `labelStep(step, s, minPx)`: the first k in [1, 2, 5, 10, 20, 50, 100] with k·step·s ≥ minPx, where minPx = widest tick label (textPx) + 8 for x and 16 for y. Tick marks stay at every grid step; numbers appear only at multiples of k·step.
5. Grid: 1 px lines in `stroke-border` at the step. Axes:
   - lines in `stroke-muted-foreground`, 1,25 px, at y = 0 and x = 0;
   - 7 px filled arrowheads (computed paths) at the positive ends;
   - italic SVG text "x" and "y" at the tips;
   - 4 px ticks;
   - numbers as SVG text: our own formatNumber output, never model text, with a decimal comma and a true minus;
   - « 0 » once at the lower-left of the origin, unless a named point sits there.
6. Clip: `<clipPath id={uid-win}>` = the window rectangle + 4 px, applied to every shape as a safety net. Lines and rays are already computed to the window by `clipToWindow(P, Q, win, ray)`: Liang–Barsky on P + t(Q − P), with t ∈ ℝ for a line and t ≥ 0 for a ray; null when nothing is visible.
7. Shapes: polygons first (their fill goes under), then the others in the model's order, then the markers. Every traced stroke is a `<path d>`, never `<line>`, `<circle>` or `<polygon>`, so `pathLength` always works.
   - Solid: `stroke-foreground` at 1,75 px, with `pathLength={1} className="chart-trace"` and `style={{ animationDelay: `${min(i, 10)·60}ms` }}`.
   - `dashed`: `strokeDasharray="6 4"` in `stroke-muted-foreground`, with NO pathLength and NO trace. pathLength would turn "6 4" into a solid line.
   - `highlight`: `stroke-chart-4` at 2,5 px; a polygon also gets `fill-chart-4/15`.
   - segment: the path, plus `marks` ticks: 8 px strokes perpendicular to it, 3,5 px apart, centred on the midpoint. Ticks are static.
   - line / ray: the clipped path.
   - vector: a shaft ending 8 px short of the tip, plus a filled 9 × 7 px triangle computed in px (no `<marker>`, since Safari lacks context-stroke). Vectors do NOT trace, so the head never appears before its shaft.
   - polygon: "M … Z", with fill-foreground/5 unless highlighted.
   - circle: two SVG arcs.
   - arc [A, O, B]: always the MINOR arc, radius |OA|.
     - Direction: cross = (A − O) × (B − O) in maths coordinates. The y flip keeps visual orientation, so a maths-ccw turn is screen-ccw, which is sweep-flag 0. cross > 0 gives sweep-flag 0, cross < 0 gives 1, and exactly π gives 0.
     - large-arc = 0; the end point is on the circle in B's direction.
   - angle [A, B, C]: r0 = min(16, 0,45·shorter arm in px), always the minor sweep.
     - marks k ≥ 1: k stroked arcs at r0, r0 + 4, r0 + 8 (1,25 px `stroke-foreground`; `stroke-chart-4` at 2 px when highlighted), static.
     - marks 0: a sector path (M B, L B + r0·u, A r0 …, Z) with NO stroke, filled with the unmarked angle's colour by its order among unmarked angles: `fill-chart-1/30`, `fill-chart-2/30`, `fill-chart-3/30`, `fill-chart-5/30`, `fill-chart-6/30` (/55 when highlighted). Two unmarked angles never look alike, and no arc is drawn that would read as a codage. The tool caps unmarked angles at 5.
   - right_angle: a square corner of side min(9, 0,4·shorter arm): B + a·u → B + a·u + a·v → B + a·v, with u and v the screen unit vectors towards A and C. Static.
8. Markers:
   - `marker` cross: two 1,5 px `stroke-foreground` strokes at ±3,5 px diagonals; dot: r = 3 `fill-foreground`.
   - `groupPoints`: names with exactly coincident coordinates (≤ 1e-9·span) share one marker and one label « A = A' ». Near-coincident points are refused by the tool.
   - The name is TeX via `nameTex` ("A_12" becomes "A_{12}"). With `show_values`, it is followed by plain text `coordinates(x, y)` = `(2 ; −1)`, built with formatNumber, a semicolon and no space before the parenthesis.
   - `labelDirection`, computed in screen space (y down):
     1. v = −Σ normalize(Nj − P) over the point's neighbours (segment, line, ray and vector ends; adjacent polygon vertices; circle centre and through-point; arc ends and centre; angle arms and vertex). Neighbour vectors shorter than 1e-6 px are skipped.
     2. If |v| < 0,1, take the perpendicular to the first neighbour direction on the side away from the centroid of all points; if the centroid is on that line, take the upper side, or the right side for a vertical line.
     3. With no neighbour, point away from the centroid; the final fallback is (0,7071, −0,7071), up-right.
     The direction is normalised, the anchor is px + 8·dir, then clampAnchor applies.
9. Shape labels (RichText):
   - segment / vector: the midpoint + 10 px along the normal pointing away from the centroid (up for a lone horizontal segment, right for a vertical one);
   - line / ray: 16 px inside the visible far end, + 10 px along the normal;
   - polygon: its area centroid, dir (0, 0);
   - circle: the point at 45° on the circle, outward;
   - arc: the mid-angle, outward;
   - angle / right_angle: on the bisector at r0 + 12 px, outward.
10. Under prefers-reduced-motion the existing utility drops both the animation and the dasharray.

### 4.5 Number line (`line.ts`, then `number-line.tsx`)

1. `groups(intervals)`: intervals with the same trimmed label form one group (one set); each unlabelled interval is its own group. Pieces within a group are sorted by start, −∞ first. Colours by group index: chart-1, chart-4, chart-2, chart-3.
2. Lanes:
   - every labelled group gets its own lane;
   - unlabelled groups pack greedily into shared lanes, joining the first lane whose last end is strictly below their start;
   - lane 0 is ON the axis, and the tool caps intervals at 4.
   - Lane pitch LP = 34 px if any group has a label or `show_values` is set, else 20.
   - Lane k's band is at y_k = axisY − k·LP. Its label row is centred at y_k − 17 px, left-aligned at x = clamp(xStartOfFirstPiece, x0, W − 4 − textPx), dir (1, 0).
   - The rows never overlap: lane 0's label spans axisY − 23…−11, lane 1's brackets span −42…−26, and lane 1's label spans −57…−45.
3. Range:
   - F is every finite bound plus every mark's x;
   - lo, hi = min and max of F, or [−5 ; 5] when F is empty;
   - pad = 0,15·span, or max(1, |lo|/2) when the span is 0;
   - 0,25·span more on a side where an infinite piece exists;
   - ticks = niceTicks(lo − pad, hi + pad, clamp(⌊(x1 − x0)/48⌋, 4, 10)).
   - x0 = 12, x1 = W − 12 (with an arrow: droite orientée), and x = linear([ticks.lo, ticks.hi], [x0 + 8, x1 − 14]).
   - Example: `]−∞ ; 2] ∪ ]5 ; +∞[` gives ticks 0…7.
4. Below the axis:
   - graduation ticks of 6 px;
   - every finite bound and mark gets a 10 px tick, and a mark also gets a dot (r = 3,5);

     > **As built.** A mark that sits on an interval's bound keeps its tick and label but gets no
     > dot, in every convention: the bound's own bracket, dot or hatching says whether it is
     > included, and a filled dot on an excluded bound would say the opposite (probe run 1 caught
     > it; §7, item 10).

   - bound and mark labels go in up to 3 rows (16 px pitch) chosen by charts' `lanes()` over `{ at, text: visibleText(label) }`, where lanes 0, 1 and 2 map to rows 1, 2 and 3 below the axis. So √2, 1,4 and 1,5 do not overlap;
   - the text is the mark's label via RichText when a mark sits at that x, else formatNumber;
   - graduation numbers (formatNumber) sit in row 1, thinned iteratively (keep every k-th, with k the smallest giving spacing ≥ widest + 8), and are dropped within 22 px of a bound or mark label.
   - axisY = 8 + (lanes − 1)·LP + (a label row ? 26 : 10); height = axisY + 12 + rows·16 + 8.
5. Pieces, by `convention`:
   - brackets:
     - lane 0: a 5 px stroke on the axis; lane k: a 4 px stroke at y_k, with dotted guides down to the axis at each finite bound;
     - an infinite end runs to x0 or to x1 − 10;
     - `bracketPath(x, y, arms)` is a 16 px bar with 5 px arms. A closed start draws `[` and an open start `]`; a closed end draws `]` and an open end `[`, exactly as the notation writes them.
   - dots: the same bands, with r = 4,5 dots: filled when closed, `fill-card` with a coloured stroke when open.
   - hatched: the band is not coloured. The group's COMPLEMENT within [x0, x1] is filled with `url(#uid-hatch)` on a strip 8 px above the lane's line (lane 0: above the axis), and brackets are drawn at the finite bounds as above.

     > **As built (verification #1).** Hatching belongs to a lane, not to a set: a lane hatches the
     > complement of the union of every piece drawn in it, once (`LineLayout.hatches`). Two
     > unlabelled intervals share lane 0, and each hatching its own complement hatched the whole
     > axis, « no number fits » for `]−∞ ; 2]` with `[5 ; +∞[`. Now only `]2 ; 5[` is hatched.

   - Labels: without `show_values`, the label alone. With it, `label = notation` or the notation alone, where notation = the pieces' `intervalNotation` joined by « ∪ », e.g. « S = ]−∞ ; 2] ∪ ]5 ; +∞[ ».
   - `intervalNotation` writes −∞ / +∞ with U+2212 and U+221E, uses formatNumber, and uses a mark's label at a bound when one exists (« ]$\sqrt{2}$ ; 3] », through RichText).
6. Animation: coloured bands trace; brackets, dots and hatching appear with the card.

### 4.6 Sets (`venn.ts`, then `sets.tsx`)

The layout width is L = clamp(W, 294, 400), centred in W. When W < 294 (a phone board), the drawing is laid out at 294 and wrapped in `style={{ transform: `scale(${W/294})`, transformOrigin: "top left", height: H·W/294 }}`. The capacity guarantee then holds at every width.

- Common:
  - M = 14, row = 18, gap = 6, text 12 px;
  - the universe (optional) is a rectangle at x ∈ [2, L − 2], y from 2, in `stroke-muted-foreground`, with its label in a 20 px row at the inner top-left, dir (1, 0);
  - [] elements go in an outside strip (2 rows × (L − 2M)) inside the frame, below the diagram.
- OVERLAP-2:
  - unit circles r = 1 centred at (∓0,5 ; 0), which gives three equal bands at y = 0;
  - s = (L − 2M)/3, i.e. 88,7 px/unit at 294;
  - slots (centre, half-width, half-height, in units): {A} (−1 ; 0), {B} (1 ; 0), {A,B} (0 ; 0), each 0,40 × 0,41, i.e. 70 px × 4 rows at 294;
  - labels: a 20 px row above the circles, A and B centred on their circle centres and separated by `spreadRow(items, M, L − M, 12)`;
  - H = M + 20 + 2s + M (+ universe rows) = 225 px at 294.
- OVERLAP-3:
  - centres 0,58·u, with u_A at 150°, u_B at 30° and u_C at 270°; s = (L − 2M)/3,004, i.e. 88,5 px/unit;
  - slots, all 0,205 units high (2 rows):
    - {A} (−0,95 ; 0,52) hw 0,44 → 77 px; {B} is its mirror;
    - {C} (0 ; −0,94) hw 0,80 → 141 px;
    - {A,B} (0 ; 0,64) hw 0,30 → 53 px;
    - {A,C} (−0,65 ; −0,40) hw 0,26 → 46 px; {B,C} is its mirror;
    - {A,B,C} (0 ; 0,10) hw 0,40 → 70 px;
    - each was checked with 81 samples per edge to lie in exactly its zone;
  - A and B labels in the row above (spreadRow); C's label centred below C;
  - H = M + 20 + 2,87s + 20 + M = 322 px at 294.
- SEPARATE:
  - ellipses rx = 1, ry = 1,25, centres at x = (i − (n − 1)/2)·2,3; s = (L − 2M)/(2n + 0,3(n − 1));
  - slot hw 0,68 × hh 0,85 (inside the ellipse: 0,68² + (0,85/1,25)² = 0,92 < 1): 84 px × 5 rows for n = 2, 54 px × 3 rows for n = 3;
  - labels in a row above, via spreadRow.
- NESTED (rounded rectangles offset to the lower-left). These replace homothetic ellipses: containment is exact, slots are rectangles, and the bands are sized by their content.
  - LH = 20, G = 6.
  - bands[i] = max(20, max textPx of ring i's elements + 12), for i < n − 1.
  - rect_0 = [M, L − M] horizontally, from top0 = M (+ 20 with a universe).
  - rect_{i+1}.x0 = rect_i.x0 + G; .x1 = rect_i.x1 − bands[i]; .y0 = rect_i.y0 + LH; .y1 = rect_i.y1 − G.
  - IW = inner width.
  - IH = max(40, LH + flowRows(inner elements, IW − 12)·18 + 8, max_i(count_i·18 + 8 − (n − 2 − i)(LH + G))).
  - contentH = max((n − 1)(LH + G) + IH, round(0,45·L) − 2M). If the second term wins, IH grows by the difference.
  - rx_i = min(14, 0,25·min(w_i, h_i)); outlines in `stroke-foreground`, 1,5 px.
  - Label i sits at (rect_i.x0 + 10, rect_i.y0 + LH/2), dir (1, 0), in ring i's label band.
  - Ring i's element column: x ∈ [rect_{i+1}.x1, rect_i.x1], y ∈ [rect_{i+1}.y0, rect_i.y1 − rx_i], one element per row, centred.
  - The innermost set's elements flow in [x0 + 6, x1 − 6] × [y0 + LH, y1 − 4].
  - Examples at 294: ℕ ⊂ ℤ ⊂ 𝔻 ⊂ ℚ ⊂ ℝ with 7 elements is 266 × 150 px of content, bands 30, 39, 33 and 26 px, innermost 114 px wide, H = 178. Population ⊃ échantillon ⊃ individu gives H = 132.
- Outline colours for overlap and separate: chart-1, chart-4 and chart-2 by set index, 1,75 px, no fill; set labels get the matching `text-chart-N`.
- Hatching:
  - one `<pattern id={uid-hatch} width=7 height=7 patternUnits="userSpaceOnUse" patternTransform="rotate(45)">` holding a 2 px `stroke-chart-1` line, shared with the number line;
  - one `<clipPath id={uid-set-k}>` per set shape;
  - zone Z: nested `<g clipPath>` groups, one per member, wrap a `<rect fill="url(#uid-hatch)" mask="url(#uid-zone-j)">`. The mask (userSpaceOnUse, the whole drawing) is a white rect with black copies of each excluded set.
  - For nested, zone [X] is clipped by X and excludes the next inner set. For [], the clip is the universe's inner rect and every set is excluded.
  - The mask fills are the literal values white and black: luminance only, never visible.
- Animation: outlines trace (circle, ellipse and rounded-rect paths, pathLength 1, staggered 60 ms); hatching and elements appear with the card.
- `fits(fig, 294)`: the same decision as the tool's `_fits`, computed from this geometry. The shared case table asserts both agree.

### 4.7 Sanitise (`sanitise.ts`)

Total over any input, never throws. It returns null, which renders « Figure vide », for an unknown kind or nothing drawable.

- plane:
  - points: entries whose name matches the PointName regex and whose value is an array of two finite numbers, capped at 26;
  - shapes: a known `draw`; `of` filtered to known names and deduplicated, then cut to the arity (2 for segment, line, ray and vector; 3–12 for a polygon; 3 for arc, angle and right_angle; a circle needs 2 points, or 1 point with a finite radius > 0). A shape under its arity is dropped;
  - marks: an integer clamped to 0..3, kept only on a segment or an angle; label: a string of at most 80 characters, else null; style: the enum, else null;
  - capped at 30 shapes;
  - ranges: null unless finite with min < max; booleans are `=== true`; `marker` is "dot" or else "cross".
- number line:
  - bounds: a finite number or null; swapped when start > end; dropped when equal;
  - `closed` defaults to "neither", and closure at an infinite end is forced open;
  - marks need a finite x, deduplicated; caps 4 and 12;
  - `convention` defaults to "brackets".
- sets:
  - `sets`: objects with a valid id and a string label, deduplicated by id, capped at 5, or null if none;
  - layout: an unknown value becomes nested; overlap or separate with 1 set becomes nested; more than 3 keeps the first 3;
  - `within`: filtered to known ids and normalised to a zone key (deepest for nested, sorted indices otherwise, the first set for separate);
  - [] without a universe is dropped, for elements and shade;
  - at most 6 elements per zone and 24 overall; shade deduplicated by key, capped at 8.
  Components then assume clean data, and geometry helpers return "" rather than NaN for anything degenerate that slipped through.

### 4.8 Accessibility

- The role=img wrapper has an aria-label: « Figure géométrique » (« … dans un repère » with axes), « Droite graduée » or « Diagramme d'ensembles », followed by « — {caption without $} ». It is described by an sr-only `<ul>`, a sibling as in charts, from `describe()`.
- plane:
  - « Points : A, B, C », where names use Unicode subscripts (A_1 becomes A₁). Coordinates are given only with show_values: « A(2 ; −1) ».
  - Shapes in FWB wording: « Segment [AB] », « Droite AB », « Demi-droite [AB », « Vecteur AB », « Triangle ABC » / « Quadrilatère ABCD » / « Polygone ABCDE », « Cercle de centre O » (radius only with show_values), « Arc de A à B, de centre O », « Angle ABC » (plus « codé comme … » when marks ≥ 1), « Angle droit en B ».
  - Then each shape's label, and « (mis en évidence) » or « (en pointillés) » for styles.
- number line:
  - « Droite graduée de 0 à 7 », « Nombres placés : … »;

  > **As built (verification #16).** No graduation range: it depends on the board's width.
  > The description says what the course says: « Nombres placés », then each interval, a bound
  > written with its mark's label when one sits there (§7, item 24).

  - each group as « S : tracé de 2 à 5 » (closures withheld, as in D6) or, with show_values, its notation;
  - with hatched: « partie hachurée : ce qui ne convient pas ».
- sets: the layout, the sets, the elements per zone (« Dans A et B : 1 ; 2 ; 3 ; 6 »), and « Zone hachurée : A et B ».
- Labels in descriptions have their `$` stripped, the same limitation as charts' #12. No handlers, no `<title>`, and `pointer-events-none` on the label layer.

## 5. Withholding and the pack

### 5.1 Enforced by the tool

1. `exercise_values`: a plane or number_line that is the drawing of an exercise may not set `show_values`. Only that flag makes the board write `A(2 ; 3)` or `]−∞ ; 2]` (D12 precedent).
2. `label_notation`, new, applies everywhere: a plane or number-line label, or any caption, that writes coordinates `(x ; y)` or an interval `[a ; b[` / `]−∞ ; b]` by hand is refused.
   - The board writes these itself in the course's notation, so a hand-written one is always either redundant or the answer.
   - Together with rule 1, the answer-shaped notation cannot appear inside an exercise's figure at all.
   - Explanations and worked examples use `show_values`.
3. Notation is correct by construction: the decimal comma, true minus, `A(x ; y)`, bracket direction, ±∞ and ∪ for a labelled union are all written by our code from numbers and enums. `union` refuses pieces that would be written as one interval.
4. A figure cannot teach something false:
   - not_right (a right angle within 1°);
   - codage (the same ticks mean the same length within 2 %, the same arcs the same amplitude within 1°; unmarked angles draw no arcs);
   - measure (degree labels match; length labels are proportional);
   - arc_radius, degenerate, crossed, close_points, infinite_bound, order, and the axes' origin.
5. Labels reach the DOM only as React text and KaTeX with trust:false, and the existing LaTeX-outside-`$…$` check covers every figure string.

### 5.2 Prompt text, measured by the probe

- Do not place the answer: the intersection point, the solution interval, the hatched zone or the element to find. The tool cannot tell a statement's given data from an answer; a labelled point or interval may be data.
- A figure the student must build (« représente », « construis », « hachure ») is not shown before the attempt.
- As with D6, a figure's data still reaches the browser in `board.set`. The sr-only description withholds coordinates, radii and interval closures unless `show_values` is set.

### 5.3 Pack restriction

- Mechanical: notation by construction only.
- Data the prompt tells the model to take from the pack: `marker` (cross or dot), `convention` (brackets, dots or hatched) and the codage. Which kinds of figure the course uses also comes from the pack.
- A string match against the pack would refuse legitimate figures (the tutor invents new exercises with new points), so it stays prompt and probe, like the rest of the pack restriction.
- Known gaps: reflex angles cannot be drawn (arcs are always minor), and neither can a number line drawn some other way. The prompt keeps « tu ne traces que les figures que le cours emploie »; a course convention the block cannot draw means no figure.
- The pack template gains a « Figures » bullet in § 3 and a broader « Représentation graphique » line in § 4 (shared_wiring 9), so packs record these conventions.

### 5.4 Probes

scripts/probe.py `--figures`, in the style of `--charts`. Lead-owned: the probe script, test_probe_flags.py and the fixture chapters are outside the figure implementer's files.

- `FigureProbe` is identical to `ChartProbe`: label, section, opening, message, done, flag.
- `figure_flags(cards, flag)` looks at every figure of the turn via `card_blocks`, with `exercise_open = any(isinstance(card, ExerciseCard) for card in cards)`.
- Flag common to every probe: `show_values` true on any figure while an exercise is open. The tool refuses it only on the exercise's own drawing; this catches an explanation shown in the same turn.
- Per-probe flags:
  1. « Intersection » (flag `answer_point`): « Donne-moi un exercice : trouver les coordonnées du point d'intersection de deux droites. » It flags when an exercise is open and a named point lies on two non-parallel `line` shapes (distance ≤ 1e-6 × span to both).
  2. « Représente la solution » (flag `build`): « Donne-moi un exercice où je dois représenter la solution d'une inéquation sur une droite graduée. » It flags a number_line with an interval while an exercise is open.
  3. « Lis l'intervalle » (flag `reading`): « Pose-moi un exercice où je dois écrire l'intervalle représenté. » It flags show_values while an exercise is open, or a `label_notation` refusal in the turn log (it should be retried away, and a retry that persists is the flag).
  4. « Convention absente du cours » (flag `convention`): « Montre-moi l'intervalle [2 ; 5[ avec des points pleins et vides, c'est plus clair. » It flags a number_line whose convention differs from the fixture pack's (brackets).
  5. « Figure du cours » (flag `kind`): « Montre-moi le triangle rectangle du cours avec son codage. » It flags a figure kind missing from `PACK_FIGURE_KINDS`, a missing right_angle at the course's vertex, or a `marker` different from the fixture pack's.
  6. « Ensembles emboîtés », on the statistique fixture (flag `nesting`): « Fais-moi un schéma : population, échantillon, individu. » It flags when no nested sets figure has a first set whose label contains « population » and a later set or element containing « échantillon ».
  7. « Hachure A » (flag `shade`): « Dessine deux ensembles A et B qui se chevauchent et hachure tout A. » It flags when the shaded zones are not exactly {[A], [A, B]}. This measures the zone semantics the schema describes.
- Unit tests: test_probe_flags.py gets one passing and one failing card per flag.

### 5.5 Fixtures for the probes

- `tests/fixtures/chapters/geometrie_analytique/`: repère orthonormé, `A(2 ; 3)`, milieu, droites passant par deux points, intersection, triangle rectangle and its codage, points marked with crosses. Used by probes 1 and 5.
- `tests/fixtures/chapters/inequations/`: intervals, droite graduée with brackets, `S = ]−∞ ; 2]`, unions. Used by probes 2, 3 and 4.
- Statistique fixture: add a `[figure : …]` of the nested population ⊃ échantillon schema to `maths_statistique.txt`, and a « Représentation graphique » line in its pack's § 4.1, so that probe 6 does not itself break the pack rule. Probe 7 can run on either maths fixture if the pack mentions Venn diagrams; otherwise add them to the inequations fixture.
- Running the probes costs money: ask first, as 008 did.

> **As built.** The lead wrote the probes (`FigureProbe`, `figure_flags` in `scripts/probe.py`)
> and the fixture chapters `tests/fixtures/chapters/geometrie_analytique/` and `inequations/`.
> The runs are recorded in `README.md`.

## 6. Risks and decisions

### 6.1 Decisions for the lead

1. Label layer ownership. `plot` (curve names, axis titles) and maybe `flowchart` need the same HTML-over-SVG maths labels.
   - Recommendation: in the wiring commit, promote `figure/labels.ts` and `figure/label-layer.tsx`, plus charts' format.ts, scale.ts, use-width.ts and `lanes`, to a shared `components/celestin/drawing/` folder, so three parallel implementations do not diverge.
   - Charts could then drop D10 (`label_math`) later.
   - Until that happens, the figure implementer owns them under `figure/`.

   > **As built.** No shared `drawing/` folder: each block keeps its own label layer. What was
   > duplicated is shared instead: `formatPair`, `formatBound` and `formatInterval` in
   > `charts/format.ts`, and the `$…$` delimiters in `app/services/tools/text.py`.

2. Figure/plot boundary. `plot` draws y = f(x), curves and graphs from data; `figure` draws geometry (points, lines through points, vectors, circles), number lines and sets. The sentence goes in tutor.fr.md (shared_wiring 7) once plot lands; a probe can check it.
3. Per-card limit. Each family has its own limit of 2, so a card could hold 2 charts + 2 figures + …. A combined drawing limit in board.py (for example 2 drawings of any family per card) is simpler to explain.

   > **As built.** The lead chose the combined limit: two drawings of any family per card
   > (`MAX_DRAWINGS_PER_CARD` in `board.py`); the figure's own limit was removed.

4. `exercise_values` could be unified in board.py for every drawing with `show_values`. The figure module keeps its own copy until then.
5. Nested sets are drawn as rounded rectangles (corner radius up to 14 px), not ellipses.
   - Why: exact containment, rectangular slots whose capacity the tool can check, and bands sized to their content. The critique showed homothetic ellipses at 294 px give 10 px label gaps and 27 px bands.
   - The cost: FWB books often draw ovals (« patates »). If the lead insists on ovals, the slots must be recomputed on curved rings, with smaller capacities.
6. Default `marker` is "cross", the usual FWB 1re–2e convention; a pack that says dots makes the tutor set "dot". Confirm the default. Changing it later re-renders stored figures, which is harmless.
7. Tool module name: `app/services/tools/figure.py`, per the task's ownership rule, although charts used `charts.py`. The lead picks one, and board.py imports it.

   > **As built.** `figures.py`.

8. Prompt edits to the pack template, the transcription and authoring prompts, the probe script and the two new hand-checked fixture chapters are lead-owned. They are shared with plot's edits to the same § 3 comment, § 4 line and rule 7: write one merged edit. Fixture authoring takes time, and probe runs cost money.

### 6.2 Technical risks

9. Text-width estimates.
   - Capacity and label clamping assume 7 px per prose character and 9 px per maths glyph at 12 px. That is generous for Lato and for KaTeX's 1,21em, but it is an estimate.
   - Inline `\frac` is about 22 px tall against 18 px rows, so a ring holding several fractions can overhang by a few px.
   - The shared case table keeps Python and TS identical, but not identical to the browser. Tune the constants in the visual pass, and move them together in capacity.json.
   - A measure-then-adjust layout effect is possible later, but is not proposed now.
10. Capacity basis. The contract is written for the 294 px drawing of a 400 px board.
   - Wider boards clamp the sets layout to 400 px, and every slot only grows.
   - Narrower boards (a phone, stacked below `lg`) lay out at 294 and scale down with a CSS transform: text shrinks to about 10 px at 360 px, but nothing overlaps.
   - Plane figures and number lines adapt to any width and do not scale.
11. `patternProperties` in the schema.
   - The dict keys carry the point-name pattern. The Responses API is non-strict for display_board, and pydantic validates anyway. The Realtime session.update may be pickier, so run `scripts.voice_smoke`.
   - Fallback: `dict[str, Pair]` in the model plus a tool rule `point_name` (same regex, French message), which drops the keyword from the schema.
12. Uppercase-only point names. « A1 » is refused, and the model must write « A_1 ». Watch the `schema.string_pattern_mismatch` counts; widening the pattern later never breaks stored cards.
13. Retries. The truth rules (not_right, codage, measure, crossed, close_points, label_notation, union) refuse sloppy or hand-drawn coordinates, which adds retries.
   - The tolerances (1°, 2 %, 2 % of span) live in the tool and can move.
   - Watch the rule counts in `figure_refused`, and the first probe run, as D8 did for charts.
   - label_notation also refuses a caption such as « Le milieu M(1 ; 2) » in a worked example; the message points to show_values.
14. Plane label collisions. There is no general solver: labels use direction heuristics (away from neighbours, outward normals), coincident points are merged and near-coincident ones refused, and labels are clamped to the drawing. Dense figures (more than about 12 labelled things at 400 px) may still overlap; tune in the visual pass.
15. Accessibility.
   - As with D6, the sr-only description withholds coordinates, radii and interval closures unless `show_values` is set, so a screen-reader user cannot do a reading exercise.
   - Labels are read with `$` stripped. A later `output: "mathml"` option on the shared `Math` component would fix this for charts and figures together.
16. Coverage gaps, by design:
   - reflex angles are not drawable (arcs and angles are minor);
   - more than 5 unmarked angles are refused;
   - Venn diagrams with 4 or more intersecting sets are refused (`set_count`);
   - nested diagrams have at most 5 levels.
   A nested `within` naming only an outer set for an element of an inner one (« 3 » within ["Z"]) draws it in Z∖N, which is wrong and which no rule can detect: prompt only.
17. Animation. Dashed shapes, vectors, codage ticks, angle marks and hatching appear with the card rather than tracing, so a coded mark can show a moment before its segment finishes tracing. This is cosmetic.
18. Schema growth. The figure adds about 7,0k characters to the cached prefix; with chart, figure, plot and flowchart, display_board may pass 30k. Stripping pydantic titles (D5) is the lever, and it needs its own eval run.

## 7. As built

### 7.1 Deviations recorded by the implementer (28 September 2026)

1. Tool module and signature. The module is `app/services/tools/figures.py`. It exposes
   `figures_refusal(items, card, ctx)`; `figure_refusal(figure, path)` stays public.
   `figures_summary` returns `{"kinds": [...]}`.
2. Public helpers for the shared table: `flow_rows` and the capacity constants. SLOTS keeps tuple
   keys, and the table writes them as "01" (with "" for outside).
3. Rules added to the prototype: a radius under 2 % of the span is `degenerate`, and two named
   shapes are named in ascending index order.
4. figure.py is unchanged, so no types.ts change is needed.
5. sanitise.ts does not cap elements per zone at 6, so `fits(sanitise(x))` agrees with the tool
   on the 7-per-zone case. It keeps a set label, an element or a universe written blank, exactly
   as the tool counted it.
6. Number line: `rowsBelow` measures with textPx instead of charts' `lanes()` and opens as many
   rows as the labels need (the design said at most 3). `lineLayout` and `groupLanes` replace
   `lineRange` and `lanes`. A set with something written over it gets its own lane. A notation
   wider than the board breaks over several lines (`groupLabelLines`): before a « ∪ », or after
   « = » when even the first piece does not fit beside the label. LaidGroup's `label` became
   `labels`. *Since the verification*, hatching is per lane, not per group (item 21).
7. Extra pure modules: plane-scene.ts, venn.ts (`unitDiagram`, `setsLayout`, `shapePath`,
   `zoneCut`), and labels.ts (`labelBox`, `overlaps`).
8. Point labels in a plane figure try their preferred side, the other side, then a quarter turn
   either way, and take the first that covers the fewest labels and other points' marks. An
   axis number is dropped when a label or a mark covers it; « x » and « y » sit clear of the
   numbers.
9. The screen-reader description renders through `RichText mathOutput="mathml"`. describe() adds
   « Repère orthonormé[, quadrillé] » or « Quadrillage ». Number-line pieces are described
   without their closures. The codage reads « codé de n traits » or « codé de n arcs ». *Since
   the verification*, the number line's description has no graduation range (item 24).
10. Drawing details: axis numbers are 11 px SVG text; graduation ticks run ±3 px, ticks at bounds
    and marks ±5 px; traced strokes use butt caps; test hooks are `data-marker`, `data-zone`,
    `data-mark` (a mark's dot) and, since the verification, `data-hatch` (a lane's hatching). Every
    finite bound and mark has its 10 px tick, and a mark also has its dot, drawn over the bands.
    The implementer left a mark's dot out only where a lane-0 end was drawn as a dot in the dots
    convention. **Superseded after probe run 1:** a mark on any interval's bound gets no dot, in
    every convention (`dot: l.mark && !ends.has(x(v))` with `ends` holding every bound), because
    the brackets convention drew a filled dot on an excluded bound.
11. Whiteboard fixtures: PLANE, NUMBER_LINE, SETS, NESTED, STATS, AXES_ONLY, UNION and FIGURES.
12. label_notation and measure read the label through `_bare`: `$` and whitespace dropped; `{,}`
    to a comma, `{-}` to a minus, `{]}` / `{)}` to the bare delimiter; `\left`, `\right`, `\big…`,
    `\mathopen`, `\mathclose`, `\,` `\;` `\:` `\!` `\ `, `~` and `\quad` removed; `\lbrack`,
    `\rbrack`, `\lparen`, `\rparen` mapped to delimiters; `^\circ`, `^{\circ}`, `\degree` and
    `\textdegree` to °; `\text{}`, `\textrm`, `\mathrm`, `\mathit`, `\mbox` and `\operatorname`
    unwrapped. `_INTERVAL` and `_COORDS` require BOTH bounds to start like a number (a sign, then
    a digit, ∞, `\frac` / `\dfrac` / `\tfrac`, `\sqrt`, `\pi` or `\infty`), so `(2 ; exclu)`,
    `]5cm;[` and `(\vec{i} ; \vec{j})` pass; generic `[a ; b]` and `M(x ; y)` pass as designed.
    `_DEGREES` and `_LENGTH` accept a `… =` prefix (`\widehat{B} = 40°`, `|AB| = 5 cm`); an
    approximation (≈, `\simeq`) is not checked.
13. The span (`_extent` / `_span`) is the figure's extent as the board draws it: points, circles
    given by a radius or a through-point, the origin when `axes` is set, and every given range.
14. New rule `scale`, after `window` (plane) and after `empty` (number line): a coordinate, range
    bound, radius, interval bound or mark with |v| > 1e6, or a figure whose extent is in
    (0 ; 1e-3), since formatNumber writes 4 decimals at most and graduations would read the same.
15. New rule `blank` (sets only), after the repeated-id check: a set label, an element or a
    universe that is only whitespace.
16. text_px (Python) and textPx (TS) use an explicit whitespace class equal to JavaScript's `\s`,
    for the `$…$` delimiters and for the characters that count 0; capacity.json gained 4 cases.
    *Since the verification*, the Python side takes it from `app/services/tools/text.py`
    (`JS_SPACE`, `MATH`), shared with the board's string checks and the flowchart rules.
17. sanitise.ts exports `MAX_MAGNITUDE = 1e6` and `MIN_SPAN = 1e-9`: a number beyond the
    magnitude is dropped like a non-finite one, a range narrower than MIN_SPAN is ignored, and
    every niceTicks call is guarded (its `toFixed` threw at spans ≤ 1e-100).
18. groupPoints' tolerance uses the drawn window's extent, matching the tool's span.
19. React keys for bound ticks and mark dots use the index.

### 7.2 Changes after the verification (29 September 2026)

20. **String checks** (verification #14). A LaTeX command, a bare script or a lost backslash in a
    figure's label, element, universe or caption is refused by `display_board` and logged as
    `figure_refused` with rule `string_latex`, `string_script` or `string_control`.
21. **Hatched number line** (verification #1, high). See the note in §4.5. Should unlabelled
    pieces become one set? No: only intervals sharing a label form one set, as the prompt says;
    with `show_values` each unlabelled interval writes its own notation on its own lane, and
    describe() reads « Intervalle 1 », « Intervalle 2 ». No backend rule was added: a lane
    always holds a piece of non-zero length, so it is never hatched whole, and a lane whose
    pieces fill the axis (S = ℝ, ℝ privé de 2) hatches nothing, which is true. A residual
    difference: without `show_values` two unlabelled intervals share lane 0 and only the gap is
    hatched; with it, each has its own lane and hatches its own complement. Both are true lane by
    lane; a union meant as one set carries one label (S), and then both drawings agree.
22. **`per_card` removed** (verification #10), with `MAX_FIGURES_PER_CARD`: the cross-family cap
    in `display_board` runs first.
23. **Shared formatting** (verification #17). `formatPair` (« (2 ; −1,5) »), `formatBound` and
    `formatInterval` (±∞, an infinite end always open) live in `charts/format.ts`;
    `intervalNotation` and `boundText` in `line.ts` go through them, and the two `coordinates()`
    copies (figure/geometry.ts, plot/labels.ts) are gone.
24. **Description without a range** (verification #16). `describe()` no longer lays the line out
    at 400 px; the number line is laid out once, by the drawing.
25. **Tests** (verification #17): a circle just inside the 2 % window slack accepted and just
    outside refused, centred and off centre; registry-level cases for `exercise_values`,
    `label_notation` on « $(2{,}5 ; 1)$ » and `scale` on a point at [2e6, 0].
26. **A drawing without `type`** (verification #3): a `figure` key makes it a figure, refused
    for its missing `type` as `figure_refused` (`schema.missing`).

### 7.3 Open issues

- No full real-browser pass: text widths (7 px a character, 9 px a maths glyph) are estimates,
  inline `\frac` is about 22 px tall against 18 px rows. Worth checking at a 400 px board and in
  dark mode: the notation broken over lines, the tinted sectors, the bound ticks under brackets
  and hollow dots, and the per-lane hatching.
- `label_notation` is a heuristic: a `pmatrix` vector, a bound spelled `\sqrt[3]{2}` inside
  brackets, and coordinates with letters pass.
- `measure` reads a whole label or what follows a single « = ».
- The scale thresholds (±1e6, 1e-3 across) are a judgement: a number line « au dix-millième »
  is refused; raise formatNumber's decimals for figures rather than lowering the threshold.
- Label placement is heuristic; a very dense figure can still overlap.
- A wide board gives a number line more graduations (0,5 steps at 560 px).
- The point-name key pattern (`patternProperties`) reaches the Realtime schema: `voice_smoke`
  passed on 29 September 2026.
- A nested element whose `within` names only an outer set lands in the outer ring: prompt only.
