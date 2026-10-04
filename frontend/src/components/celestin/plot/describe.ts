import { m } from "@/paraglide/messages";
import { FRENCH, type Notation } from "../charts/format";
import { plainText } from "./labels";
import type { Legend, Scene } from "./layout";
import type { CleanPlot } from "./sanitise";

/**
 * The plot in words, for a screen reader. It says only what the drawing shows as
 * text or as a named shape: the axes and their graduations, which curves,
 * sequences, lines and points there are, by name. `PlotView` cannot tell whether
 * it sits on an open exercise, so it assumes it might: never an expression, a
 * domain or its brackets, an endpoint's kind or place, a sequence's range of n,
 * a line's vertices, nor a point's coordinates unless Célestin writes them.
 */

export function ariaLabel(plot: CleanPlot): string {
  const y = plainText(plot.y_title);
  const x = plainText(plot.x_title);
  if (x && y) return m.describe_plot_label_both({ y, x });
  return y || x ? m.describe_plot_label_titled({ title: y || x }) : m.describe_plot_label();
}

function axis(
  name: "horizontal" | "vertical",
  title: string,
  [a, b]: [number, number],
  step: number,
  notation: Notation,
) {
  const named = plainText(title);
  const input = { from: notation.number(a), to: notation.number(b), step: notation.number(step) };
  if (name === "horizontal")
    return named
      ? m.describe_plot_axis_horizontal_titled({ ...input, title: named })
      : m.describe_plot_axis_horizontal(input);
  return named
    ? m.describe_plot_axis_vertical_titled({ ...input, title: named })
    : m.describe_plot_axis_vertical(input);
}

function group({ label, curves, sequences, lines }: Legend): string[] {
  const name = label ? plainText(label) : null;
  const out: string[] = [];
  if (curves > 0) {
    out.push(
      name
        ? m.describe_plot_curves_named({ name, count: curves })
        : m.describe_plot_curves({ count: curves }),
    );
  }
  if (sequences > 0) {
    out.push(
      name
        ? m.describe_plot_sequence_named({ name })
        : m.describe_plot_sequences({ count: sequences }),
    );
  }
  if (lines > 0) {
    out.push(name ? m.describe_plot_line_named({ name }) : m.describe_plot_lines({ count: lines }));
  }
  return out;
}

export function describe(plot: CleanPlot, scene: Scene, notation: Notation = FRENCH): string {
  const out: string[] = [];
  if (plot.orthonormal) out.push(m.describe_plot_orthonormal());
  out.push(axis("horizontal", plot.x_title, plot.x_range, scene.xAxis.step, notation));
  out.push(axis("vertical", plot.y_title, plot.y_range, scene.yAxis.step, notation));
  for (const entry of scene.legend) out.push(...group(entry));

  let unnamed = 0;
  for (const i of scene.points) {
    const p = plot.points[i];
    if (!p) continue;
    const coords = p.show_values ? notation.pair(p.x, p.y) : "";
    if (p.label) {
      const label = plainText(p.label);
      out.push(
        coords
          ? m.describe_plot_point_named_coords({ label, coords })
          : m.describe_plot_point_named({ label }),
      );
    } else if (coords) out.push(m.describe_plot_point_coords({ coords }));
    else unnamed += 1;
  }
  if (unnamed > 0) out.push(m.describe_plot_points_marked({ count: unnamed }));

  const named = scene.dashed.filter((d): d is string => d !== null);
  for (const label of named) out.push(m.describe_plot_dashed_named({ label: plainText(label) }));
  const plain = scene.dashed.length - named.length;
  if (plain > 0) out.push(m.describe_plot_dashed({ count: plain }));

  if (!scene.drawable) out.push(m.describe_plot_empty());
  return out.join(" ");
}
