from __future__ import annotations

import pytest
from httpx import AsyncClient


GUARDED = "/api/courses"
BODY = {"name": "Physique", "subject": "sciences"}


async def test_foreign_origin_is_refused(client: AsyncClient) -> None:
    r = await client.post(
        GUARDED,
        json=BODY,
        headers={"authorization": "", "origin": "https://evil.example", "sec-fetch-site": "cross-site"},
    )
    assert r.status_code == 403 and r.json()["code"] == "cross_origin"


@pytest.mark.parametrize(
    "headers",
    [
        {"sec-fetch-site": "same-origin"},
        {"sec-fetch-site": "none"},
        {"origin": "http://test"},
        {"referer": "http://test/classes"},
        {},
    ],
)
async def test_same_origin_variants_pass(anon_client: AsyncClient, headers: dict[str, str]) -> None:
    # Reaches the route: 401 (no session) rather than 403 (cross origin).
    r = await anon_client.post(GUARDED, json=BODY, headers=headers)
    assert r.status_code == 401


async def test_bearer_skips_the_check(client: AsyncClient) -> None:
    r = await client.post(GUARDED, json=BODY, headers={"origin": "https://evil.example"})
    assert r.status_code == 201


async def test_get_is_never_checked(anon_client: AsyncClient) -> None:
    r = await anon_client.get("/api/health", headers={"origin": "https://evil.example", "sec-fetch-site": "cross-site"})
    assert r.status_code == 200


async def test_a_configured_cors_origin_is_trusted(settings, db_engine) -> None:
    """CORS_ORIGINS has to mean something: without this the setting is dead for
    browsers, since every cross-site POST is refused before CORS applies."""
    from httpx import ASGITransport

    from app.main import create_app
    from tests.conftest import sign_in

    app = create_app(
        settings.model_copy(update={"cors_origins": ["http://localhost:8080"]}), engine=db_engine
    )
    _, headers = sign_in(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        cross = {"origin": "http://localhost:8080", "sec-fetch-site": "cross-site"}
        allowed = await ac.post(GUARDED, json=BODY, headers={**headers, **cross})
        other = await ac.post(
            GUARDED,
            json=BODY,
            headers={"origin": "https://evil.example", "sec-fetch-site": "cross-site"},
        )
    assert allowed.status_code == 201
    assert other.status_code == 403


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
async def test_every_mutating_method_is_checked(client: AsyncClient, method: str) -> None:
    from tests.conftest import LESSON

    url = f"/api/courses/{LESSON['course_id']}"
    kwargs = {"json": {"name": "x"}} if method != "delete" else {}
    r = await getattr(client, method)(
        url, headers={"authorization": "", "origin": "https://evil.example", "sec-fetch-site": "cross-site"}, **kwargs
    )
    assert r.status_code == 403 and r.json()["code"] == "cross_origin"


# --- body limit (006 design 3.2) -------------------------------------------

async def _call(app, method: str, path: str, chunks: list[bytes], declared: int | None = None):
    sent: list[dict] = []
    headers = [(b"content-type", b"application/octet-stream")]
    if declared is not None:
        headers.append((b"content-length", str(declared).encode()))
    scope = {"type": "http", "method": method, "path": path, "headers": headers}
    queue = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)]

    async def receive():
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


def _limited(max_bytes: int = 100, upload: int = 1000):
    from app.api.middleware import BodyLimitMiddleware

    async def inner(scope, receive, send):
        while True:
            message = await receive()
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return BodyLimitMiddleware(inner, max_bytes=max_bytes, upload_max_bytes=upload)


async def test_streamed_body_over_the_cap_is_refused_without_content_length() -> None:
    assert await _call(_limited(), "POST", "/api/chat", [b"x" * 60, b"x" * 60]) == 413


async def test_declared_length_over_the_cap_is_refused_up_front() -> None:
    assert await _call(_limited(), "POST", "/api/chat", [b"x"], declared=10_000) == 413


async def test_upload_routes_get_the_document_limit() -> None:
    app = _limited(max_bytes=100, upload=1000)
    assert await _call(app, "POST", "/api/courses/c1/chapters", [b"x" * 900]) == 200
    assert await _call(app, "PUT", "/api/courses/c1/chapters/h1/document", [b"x" * 900]) == 200
    assert await _call(app, "POST", "/api/courses/c1/chapters", [b"x" * 70_000]) == 413
    assert await _call(app, "PUT", "/api/courses/c1/chapters/h1/source", [b"x" * 900]) == 413
