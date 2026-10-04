"""Text shared by the board rules: how the board's RichText finds maths, and how
two labels compare."""

from __future__ import annotations

import re

# Whitespace as the board's RichText reads it: JavaScript's `\s`, spelled out,
# because Python's `\s` differs (it has U+0085 and U+001C–U+001F, and not U+FEFF).
# A figure label's width must be the same number on both sides (`figure/labels.ts`
# spells out the same class).
JS_SPACE = "\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"

# The maths RichText renders: `$$…$$`, or `$…$` neither opening nor closing on
# whitespace. Group 1 holds a display formula's TeX, group 2 an inline one's; see
# `math_tex`. The one declaration of these delimiters on the backend.
MATH = re.compile(r"\$\$(.+?)\$\$|\$(?![" + JS_SPACE + r"])([^$]*?)(?<![" + JS_SPACE + r"])\$", re.DOTALL)


def math_tex(found: re.Match[str]) -> str:
    """The TeX between the dollars of a `MATH` match."""
    display, inline = found.groups()
    return display if display is not None else inline


def spaced(text: str) -> str:
    """Lower-cased with runs of whitespace as one space: two labels that read the
    same, and how the board finds a term in its definition."""
    return " ".join(text.casefold().split())
