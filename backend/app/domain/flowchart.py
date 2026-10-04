"""Flowchart blocks (organigrammes).

A flowchart is a graph, never a picture: nodes with a kind and a text, and each
node's exits. The board lays it out and draws it; the model never gives a
position, a colour or a style (`extra="forbid"` refuses them). Only rules that
never change live here (types, enums, sizes); the graph rules (ids, exits,
reachability, width, the path, where `hidden` may go, leaks) run in
`display_board` (`app/services/tools/flowcharts.py`), so a stored card keeps
replaying if a rule tightens (008 R4.7).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.prose import NOT_PROSE


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


MAX_NODES = 12
# A question answers oui / non. Three cases are two nested questions: how the
# course draws them, and what fits the board at phone width.
MAX_EXITS = 2
MAX_HIDDEN = 4

NodeId = Annotated[str, Field(min_length=1, max_length=16)]
NodeText = Annotated[str, Field(min_length=1, max_length=80)]
ExitLabel = Annotated[str, Field(min_length=1, max_length=16)]
Caption = Annotated[str, Field(min_length=1, max_length=200)]
# `io` is the course's « Lire » / « Afficher » box. `start` and `end` are optional
# shapes: the first node is the root whatever its kind.
FlowNodeKind = Literal["start", "end", "step", "decision", "io"]


# Named Flow* so their $defs keys never collide with another block's `Node`/`Exit`.
class FlowExit(_Model):
    to: Annotated[NodeId, NOT_PROSE]
    label: ExitLabel | None = None


class FlowNode(_Model):
    id: Annotated[NodeId, NOT_PROSE]
    kind: FlowNodeKind = "step"
    text: NodeText
    next: Annotated[list[FlowExit], Field(max_length=MAX_EXITS)] = []


class FlowchartBlock(_Model):
    """A flowchart (organigramme) the board lays out itself from nodes and their
    exits, never positions. The first node is where it starts."""

    # Required, unlike the older blocks' `type`: a card's `drawing` picks its member
    # by this tag, and one without it is read from its keys (board.py `Drawing`) only
    # to be refused for the missing tag: every drawing block after the chart says
    # what it is.
    type: Literal["flowchart"]
    nodes: Annotated[list[FlowNode], Field(min_length=2, max_length=MAX_NODES)]
    # Descriptions reach the model with the schema: without them `path` reads as a
    # file path and `hidden` as "not drawn at all".
    path: Annotated[
        list[NodeId],
        Field(
            max_length=2 * MAX_NODES,
            description="Nœuds déjà parcourus, dans l'ordre des flèches ; le dernier est l'étape en cours.",
        ),
        NOT_PROSE,
    ] = []
    hidden: Annotated[
        list[NodeId],
        Field(
            max_length=MAX_HIDDEN,
            description="Sur le drawing d'un exercise : nœuds affichés « ? », à retrouver.",
        ),
        NOT_PROSE,
    ] = []
    caption: Caption | None = None
