"""Dictation wire DTO."""

from __future__ import annotations

from pydantic import BaseModel


class DictationResponse(BaseModel):
    """What was said, trimmed. Empty when nothing intelligible was: the browser says so, the call is not an
    error."""

    text: str
