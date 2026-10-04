"""The one reading of `$…$` every board rule shares: `app/services/tools/text.py`."""

from __future__ import annotations

import json

import pytest

from app.domain.errors import ToolValidationError
from app.services.tools import board, figures, flowcharts, registry
from app.services.tools.board import BoardSet
from app.services.tools.text import MATH, math_tex
from scripts import probe
from tests.fixtures.curricula import ctx_for

# JavaScript's `\s` (ECMAScript WhiteSpace and LineTerminator), written out here
# rather than read from `text.JS_SPACE`: what the board's RichText never opens or
# closes a `$…$` on.
JS_WHITESPACE = [
    "\t",
    "\n",
    "\v",
    "\f",
    "\r",
    " ",
    "\u00a0",
    "\u1680",
    "\u2000",
    "\u2005",
    "\u200a",
    "\u2028",
    "\u2029",
    "\u202f",
    "\u205f",
    "\u3000",
    "\ufeff",
]
# Whitespace to Python's `\s` (or looking like it) but not to JavaScript's: RichText
# opens maths on it.
NOT_JS_WHITESPACE = ["\x85", "\x1c", "\x1d", "\x1e", "\x1f", "\u200b", "\u180e"]


@pytest.mark.parametrize(
    "text,found",
    [
        ("$x$", ["x"]),
        ("$$S_n = 1$$", ["S_n = 1"]),
        ("de $u_n$ à $u_{n+1}$", ["u_n", "u_{n+1}"]),
        # Spaces inside are the formula's own; a display formula may span lines.
        ("$a + b$", ["a + b"]),
        ("$$\n\\frac{1}{2}\n$$", ["\n\\frac{1}{2}\n"]),
        # A dollar that opens or closes on a space is a price, not maths.
        ("30 $ et $x^2$", ["x^2"]),
        ("$ x$", []),
        ("$x $", []),
        ("Prix : 5 $", []),
    ],
)
def test_math_is_what_the_board_renders_as_maths(text: str, found: list[str]) -> None:
    assert [math_tex(m) for m in MATH.finditer(text)] == found


@pytest.mark.parametrize("space", JS_WHITESPACE, ids=lambda c: f"U+{ord(c):04X}")
def test_maths_never_opens_or_closes_on_javascript_whitespace(space: str) -> None:
    assert MATH.search(f"${space}x$") is None
    assert MATH.search(f"$x{space}$") is None
    assert MATH.fullmatch(f"$a{space}b$") is not None


@pytest.mark.parametrize("char", NOT_JS_WHITESPACE, ids=lambda c: f"U+{ord(c):04X}")
def test_maths_opens_on_what_only_python_calls_whitespace(char: str) -> None:
    assert MATH.fullmatch(f"${char}x$") is not None
    assert MATH.fullmatch(f"$x{char}$") is not None


def test_every_rule_reads_maths_with_the_one_declaration() -> None:
    """The board's string checks, the flowchart rules, a figure label's width and
    the probes: one `$…$`, so they can never disagree on what is maths."""
    assert board.MATH is flowcharts.MATH is figures.MATH is probe.MATH is MATH


def test_the_board_refuses_latex_that_its_rich_text_would_show_raw() -> None:
    """A byte-order mark after the `$` is whitespace to RichText: the formula shows
    raw, so the board refuses its LaTeX; without it, the same formula is maths."""
    ctx = ctx_for()

    def show(text: str) -> object:
        card = {"kind": "explanation", "title": "Fractions", "blocks": [{"type": "text", "text": text}]}
        return registry.execute("display_board", json.dumps({"card": card}), ctx)

    with pytest.raises(ToolValidationError) as exc:
        show("La moitié : $\ufeff\\frac{1}{2}$.")
    assert exc.value.message.startswith("Du LaTeX hors de $…$")
    assert exc.value.message.endswith("card.blocks[0].text (\\frac)")
    assert isinstance(show("La moitié : $\\frac{1}{2}$."), BoardSet)
