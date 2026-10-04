"""Photographed work wire DTO."""

from __future__ import annotations

from pydantic import BaseModel


class WorkReadResponse(BaseModel):
    """What the model read of the photo, to be corrected by the student before it is sent. Empty when
    nothing was written there: the browser says so, the call is not an error."""

    text: str
