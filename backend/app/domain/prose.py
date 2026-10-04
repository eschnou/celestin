"""Which strings of a board card are prose: all of them, but the fields marked here."""

from __future__ import annotations


class NotProse:
    """`Annotated` metadata on a board model's field whose strings are not prose:
    raw LaTeX (`tex`), ids, an expression in our own grammar. The board's string
    checks (LaTeX or a subscript outside `$…$`, a newline or a tab that ate a
    backslash) read such a field as raw. A Literal field is never prose either,
    and needs no marker: its values are the schema's, not the model's.

    It goes on the field itself (`Annotated[list[NodeId], Field(...), NOT_PROSE]`,
    `Annotated[NonEmpty | None, NOT_PROSE]`), where Pydantic keeps it in the
    field's metadata; inside a list or an optional arm it would not be seen. It
    adds nothing to the JSON schema the model receives."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "NOT_PROSE"


NOT_PROSE = NotProse()
