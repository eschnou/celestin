"""Reading a photograph of the student's own work (the camera in the composer).

The tutor never sees the picture. A vision model (the transcription role) reads the handwriting into text, in
the conventions of the course's transcription (`[incertain: a | b]`, `[illisible]`, formulas in `$…$`); the
browser puts that text in the message field, the student reads it and corrects it, and what she sends is an
ordinary text message. So the tutor stays text-only whatever its model, a misreading is the student's to see
before it counts, and the photo is read, then forgotten: nothing is stored.
"""

from __future__ import annotations

import logging
import re
import time

from app.config import Settings
from app.domain.ai_config import priced
from app.domain.chapter import token_counts
from app.domain.language import CourseLanguage
from app.domain.usage import UsageScope, usage_scope
from app.providers.base import AiConfigSource, CompletionClient
from app.services.documents import DocumentService
from app.services.prompts import PromptLibrary

log = logging.getLogger(__name__)

# What the model is told next to the picture, per course language (it reads the prompt in that language).
_PHOTO_LABEL: dict[CourseLanguage, str] = {
    "fr": "Voici la photo du travail de l'élève.",
    "en": "Here is the photo of the student's work.",
}
_DOUBT = re.compile(r"\[(?:incertain|uncertain):")


class WorkReader:
    def __init__(
        self,
        llm: CompletionClient,
        documents: DocumentService,
        prompts: PromptLibrary,
        settings: Settings,
        ai: AiConfigSource,
    ) -> None:
        self._llm = llm
        self._documents = documents
        self._prompts = prompts
        self._s = settings
        self._ai = ai

    async def read(self, photo: bytes, language: CourseLanguage, user_id: str, course_id: str | None = None) -> str:
        """The text of the work in the photo; `DocumentInvalid` when it is not a usable image. Empty when the
        model found nothing to read."""
        started = time.monotonic()
        document = await self._documents.prepare([photo], min_pixels=self._s.work_min_pixels)
        page = document.pages[0]
        with usage_scope(UsageScope(user_id, "work_reading", course_id)):  # the usage ledger (spec 015)
            result = await self._llm.complete(
                role="transcription",
                instructions=[self._prompts.work(language)],
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": _PHOTO_LABEL[language]},
                            {"type": "input_image", "image_url": page.data_url, "detail": self._s.transcription_detail},
                        ],
                    }
                ],
                max_output_tokens=self._s.work_max_output_tokens,
            )
        text = result.text.strip()
        counts = token_counts(result.usage)
        config = self._ai.config
        priced_here = priced(
            self._s,
            config.transcription.connection if config else None,
            "transcription_price_in",
            "transcription_price_cached",
            "transcription_price_out",
        )
        cached, tokens_in, tokens_out = counts["cached_tokens"], counts["input_tokens"], counts["output_tokens"]
        cost = (
            round(
                ((tokens_in - cached) * self._s.transcription_price_in
                 + cached * self._s.transcription_price_cached
                 + tokens_out * self._s.transcription_price_out) / 1_000_000,
                5,
            )
            if priced_here
            else 0.0
        )
        # What the student wrote is never logged: only how much, and how sure the model was.
        log.info(
            "work_read",
            extra={
                "user_id": user_id,
                "language": language,
                "bytes_in": len(photo),
                "bytes_sent": len(page.jpeg),
                "chars": len(text),
                "doubts": len(_DOUBT.findall(text)),
                "input_tokens": tokens_in,
                "output_tokens": tokens_out,
                "cost_usd": cost,
                "ms": round((time.monotonic() - started) * 1000),
            },
        )
        return text
