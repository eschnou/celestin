"""Same-origin guard for mutating API requests (004 design 3.3).

Cookie-authenticated browsers are the CSRF surface; a bearer header cannot be
forged cross-site, so bearer requests skip the check. An origin the operator
listed in CORS_ORIGINS is trusted too, otherwise that setting could never work
for a browser. Pure ASGI: it reads the scope's headers and never touches the
body, so streamed responses pass through untouched.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from fastapi.responses import JSONResponse

from app.api.locale import locale_of_scope
from app.domain.errors import CrossOrigin, DocumentTooLarge, PayloadTooLarge

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def is_same_origin(headers: dict[str, str], allowed: frozenset[str] = frozenset()) -> bool:
    if headers.get("authorization"):
        return True
    origin = headers.get("origin") or headers.get("referer")
    if origin and _origin_of(origin) in allowed:
        return True
    site = headers.get("sec-fetch-site")
    if site is not None:
        return site in ("same-origin", "none")
    if not origin:
        # Neither header: not a browser fetch (curl, tests). Browsers always send one.
        return True
    return urlsplit(origin).netloc.lower() == headers.get("host", "").lower()


def _origin_of(value: str) -> str:
    """`https://app.example.com/path` -> `https://app.example.com`, as CORS lists it."""
    parts = urlsplit(value)
    return f"{parts.scheme}://{parts.netloc}".lower() if parts.scheme else value.lower()


class SameOriginMiddleware:
    def __init__(self, app, allowed_origins: list[str] | None = None) -> None:  # noqa: ANN001
        self._app = app
        self._allowed = frozenset(_origin_of(o) for o in (allowed_origins or []))

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if (
            scope["type"] == "http"
            and scope["method"] not in SAFE_METHODS
            and scope["path"].startswith("/api/")
        ):
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
            if not is_same_origin(headers, self._allowed):
                refusal = JSONResponse(
                    status_code=CrossOrigin.status, content=CrossOrigin().body(locale_of_scope(scope))
                )
                await refusal(scope, receive, send)
                return
        await self._app(scope, receive, send)


UPLOAD_PATHS = re.compile(r"^/api/courses/[^/]+/chapters(/[^/]+/document)?/?$")
AUDIO_PATH = "/api/dictation"
WORK_PATH = re.compile(r"^/api/courses/[^/]+/work/?$")
UPLOAD_MARGIN = 65_536  # multipart boundaries and headers around the files


class _BodyTooLarge(Exception):
    pass


class BodyLimitMiddleware:
    """Refuse an oversized body before a route parses it (005 NFR 4.3.5, 006 §3.2).
    The declared `Content-Length` is checked first; the bytes actually received are
    counted as well, so a chunked body cannot slip past. Upload routes get the
    document limit, the dictation route the recording limit, everything else the JSON limit."""

    def __init__(  # noqa: ANN001
        self, app, max_bytes: int, upload_max_bytes: int, audio_max_bytes: int | None = None, work_max_bytes: int | None = None
    ) -> None:
        self._app = app
        self._max = max_bytes
        self._upload_max = upload_max_bytes
        self._audio_max = audio_max_bytes
        self._work_max = work_max_bytes

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        upload = scope["method"] in ("POST", "PUT") and bool(UPLOAD_PATHS.match(scope["path"]))
        audio = self._audio_max is not None and scope["method"] == "POST" and scope["path"] == AUDIO_PATH
        work = self._work_max is not None and scope["method"] == "POST" and bool(WORK_PATH.match(scope["path"]))
        limit = (
            self._upload_max + UPLOAD_MARGIN
            if upload
            else (self._audio_max or 0) + UPLOAD_MARGIN
            if audio
            else (self._work_max or 0) + UPLOAD_MARGIN
            if work
            else self._max
        )
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            await self._refuse(scope, receive, send, upload)
            return

        received = 0
        overflowed = False
        refused = False

        async def counting_receive():  # noqa: ANN202
            nonlocal received, overflowed
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    overflowed = True
                    raise _BodyTooLarge()
            return message

        async def guarded_send(message) -> None:  # noqa: ANN001
            # The framework may turn the exception above into its own answer (FastAPI
            # says 400 « error parsing the body »): once over the limit, ours replaces it.
            nonlocal refused
            if not overflowed:
                await send(message)
            elif not refused:
                refused = True
                await self._refuse(scope, receive, send, upload)

        try:
            await self._app(scope, counting_receive, guarded_send)
        except _BodyTooLarge:
            pass
        if overflowed and not refused:
            await self._refuse(scope, receive, send, upload)

    async def _refuse(self, scope, receive, send, upload: bool) -> None:  # noqa: ANN001
        error = DocumentTooLarge(self._upload_max) if upload else PayloadTooLarge()
        body = error.body(locale_of_scope(scope))
        await JSONResponse(status_code=error.status, content=body)(scope, receive, send)
