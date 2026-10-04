import { m } from "@/paraglide/messages";
import { FRENCH, type Notation } from "../charts/format";
import { nameText } from "./geometry";
import { boundText, groupLabel, groupNotation, groups } from "./line";
import type { CleanFigure, CleanLine, CleanPlane, CleanSets, CleanShape } from "./sanitise";

/**
 * What a figure shows, in the interface language, for a screen reader. The notation inside
 * (coordinates, intervals, numbers) is the course's, from `charts/format.ts`. The same withholding as
 * the drawing: coordinates, radii and the closures of intervals are said only
 * when Célestin sets `show_values`, so a reading exercise is not read out. Lines may
 * hold `$…$` from Célestin's labels; the view renders them as MathML.
 */

/** Message functions, not strings: the language is read when a description is built. */
const KIND: Record<CleanFigure["kind"], () => string> = {
  plane: m.describe_figure_kind_plane,
  number_line: m.describe_figure_kind_number_line,
  sets: m.describe_figure_kind_sets,
};

/**
 * The figure's name for its `role="img"`. The caption is not repeated here: the
 * figcaption's MathML copy reads it, with its maths as maths.
 */
export function ariaLabel(fig: CleanFigure | null): string {
  if (!fig) return m.describe_figure_empty();
  return fig.kind === "plane" && fig.axes
    ? m.describe_figure_plane_axes({ kind: KIND.plane() })
    : KIND[fig.kind]();
}

const names = (of: string[]) => of.map(nameText).join("");
const POLYGONS: Record<number, (input: { names: string }) => string> = {
  3: m.describe_figure_polygon_3,
  4: m.describe_figure_polygon_4,
};

function shapeText(shape: CleanShape, fig: CleanPlane, notation: Notation): string {
  const [a = "", b = "", c = ""] = shape.of.map(nameText);
  switch (shape.draw) {
    case "segment":
      return m.describe_figure_segment({ a, b });
    case "line":
      return m.describe_figure_line({ a, b });
    case "ray":
      return m.describe_figure_ray({ a, b });
    case "vector":
      return m.describe_figure_vector({ a, b });
    case "polygon":
      return (POLYGONS[shape.of.length] ?? m.describe_figure_polygon_n)({ names: names(shape.of) });
    case "circle":
      if (shape.radius !== null) {
        return fig.showValues
          ? m.describe_figure_circle_radius({ a, radius: notation.number(shape.radius) })
          : m.describe_figure_circle({ a });
      }
      return m.describe_figure_circle_through({ a, b });
    case "arc":
      return m.describe_figure_arc({ a, b, c });
    case "angle":
      return m.describe_figure_angle({ a, b, c });
    case "right_angle":
      return m.describe_figure_right_angle({ b });
  }
}

function codage(shape: CleanShape): string {
  if (shape.marks <= 0) return "";
  return shape.draw === "segment"
    ? m.describe_figure_marks_segment({ count: shape.marks })
    : m.describe_figure_marks_arc({ count: shape.marks });
}

function plane(fig: CleanPlane, notation: Notation): string[] {
  const lines: string[] = [];
  if (fig.axes) lines.push(fig.grid ? m.describe_figure_axes_grid() : m.describe_figure_axes());
  else if (fig.grid) lines.push(m.describe_figure_grid());
  if (fig.points.length) {
    const points = fig.points.map((p) =>
      fig.showValues ? `${nameText(p.name)}${notation.pair(p.at[0], p.at[1])}` : nameText(p.name),
    );
    lines.push(m.describe_figure_points({ list: points.join(", ") }));
  }
  for (const shape of fig.shapes) {
    const style =
      shape.style === "highlight"
        ? ` ${m.describe_figure_style_highlight()}`
        : shape.style === "dashed"
          ? ` ${m.describe_figure_style_dashed()}`
          : "";
    const label = shape.label ? m.describe_figure_shape_label({ label: shape.label }) : "";
    lines.push(`${shapeText(shape, fig, notation)}${codage(shape)}${style}${label}`);
  }
  return lines;
}

/**
 * What the course says of a number line: the numbers placed and the intervals,
 * a bound by its mark's label when one sits there, as the drawing writes it.
 * Not the graduations: their range and step follow the board's width, and the
 * aria-label already says « Droite graduée ».
 */
function numberLine(fig: CleanLine, notation: Notation): string[] {
  const bound = (v: number) => boundText(v, "", fig.marks, notation);
  const lines: string[] = [];
  if (fig.marks.length) {
    lines.push(
      m.describe_figure_marks({
        list: fig.marks
          .map((mark) => mark.label ?? notation.number(mark.x))
          .join(notation.separator),
      }),
    );
  }
  groups(fig.intervals, fig.convention === "hatched").forEach((g, i) => {
    const name = g.label ?? m.describe_figure_interval_n({ n: i + 1 });
    if (fig.showValues) {
      lines.push(
        g.label
          ? (groupLabel(g, fig.marks, true, notation) ?? name)
          : m.describe_figure_named({ name, text: groupNotation(g, fig.marks, notation) }),
      );
      return;
    }
    const parts = g.pieces.map((p) => {
      if (p.start === null && p.end === null) return m.describe_figure_whole_line();
      if (p.start === null) return m.describe_figure_from_left({ to: bound(p.end ?? 0) });
      if (p.end === null) return m.describe_figure_to_right({ from: bound(p.start) });
      return m.describe_figure_between({ from: bound(p.start), to: bound(p.end) });
    });
    lines.push(m.describe_figure_drawn({ name, parts: parts.join(m.describe_figure_then()) }));
  });
  if (fig.convention === "hatched" && fig.intervals.length) {
    lines.push(m.describe_figure_hatched());
  }
  return lines;
}

const LAYOUT: Record<CleanSets["layout"], () => string> = {
  nested: m.describe_figure_layout_nested,
  overlap: m.describe_figure_layout_overlap,
  separate: m.describe_figure_layout_separate,
};

/** Where a zone is. `bare` drops the lead word (« Dans … »), for a sentence that supplies its own. */
function zoneText(fig: CleanSets, zone: number[], bare = false): string {
  const label = (i: number) => fig.sets[i]?.label ?? "";
  if (zone.length === 0)
    return bare ? m.describe_figure_zone_outside_bare() : m.describe_figure_zone_outside();
  if (fig.layout === "nested") {
    const [i = 0] = zone;
    const inner = fig.sets[i + 1];
    if (inner) {
      const input = { a: label(i), b: inner.label };
      return bare
        ? m.describe_figure_zone_nested_bare(input)
        : m.describe_figure_zone_nested(input);
    }
    const input = { a: label(i) };
    return bare
      ? m.describe_figure_zone_nested_last_bare(input)
      : m.describe_figure_zone_nested_last(input);
  }
  const inside = zone.map(label);
  const only = fig.layout === "overlap" && zone.length < fig.sets.length;
  const list =
    inside.length > 1
      ? `${inside.slice(0, -1).join(", ")}${m.describe_figure_and()}${inside[inside.length - 1]}`
      : (inside[0] ?? "");
  if (only)
    return bare
      ? m.describe_figure_zone_only_bare({ list })
      : m.describe_figure_zone_only({ list });
  return bare ? m.describe_figure_zone_in_bare({ list }) : m.describe_figure_zone_in({ list });
}

function sets(fig: CleanSets): string[] {
  const lines = [
    m.describe_figure_sets_line({
      layout: LAYOUT[fig.layout](),
      sets: fig.sets.map((s) => s.label).join(", "),
    }),
  ];
  if (fig.universe) lines.push(m.describe_figure_universe({ universe: fig.universe }));
  const seen = new Map<string, { zone: number[]; items: string[] }>();
  for (const e of fig.elements) {
    const key = e.zone.join("");
    const entry = seen.get(key) ?? { zone: e.zone, items: [] };
    entry.items.push(e.text);
    seen.set(key, entry);
  }
  for (const { zone, items } of seen.values())
    lines.push(
      m.describe_figure_zone_items({ zone: zoneText(fig, zone), items: items.join(" ; ") }),
    );
  for (const zone of fig.shade)
    lines.push(m.describe_figure_shaded({ zone: zoneText(fig, zone, true) }));
  return lines;
}

/** The figure, line by line. */
export function describe(fig: CleanFigure | null, notation: Notation = FRENCH): string[] {
  if (!fig) return [m.describe_figure_empty()];
  switch (fig.kind) {
    case "plane":
      return plane(fig, notation);
    case "number_line":
      return numberLine(fig, notation);
    case "sets":
      return sets(fig);
  }
}
