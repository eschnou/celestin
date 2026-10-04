"""The pace tool: the tutor proposes the next step, the learner takes it.

`propose_next_step` lights the « Étape suivante » button on the board and the
tutor ends its turn. The next card comes only after she clicks it or says so in
the conversation. No server-side state: the browser owns the button.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from app.domain.language import by_language
from app.domain.marker import Marker
from app.services.tools.context import TurnContext


class ProposeNextStepArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class NextStepProposed:
    marker: Marker
    output: str | None = None


_OUTPUT = by_language(
    fr="Bouton « Étape suivante » activé. Termine ton tour et attends qu'elle clique ou réponde.",
    en="“Next step” button enabled. End your turn and wait for the student to click or answer.",
)


def propose_next_step(_: ProposeNextStepArgs, ctx: TurnContext) -> NextStepProposed:
    return NextStepProposed(marker=Marker("marker.step_ready"), output=_OUTPUT[ctx.language])
