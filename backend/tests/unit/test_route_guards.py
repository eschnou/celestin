"""004 R2.4: no route without an explicit list of admitted roles."""

from __future__ import annotations

from fastapi.dependencies.models import Dependant
from sqlalchemy import Engine

from app.config import Settings
from app.main import create_app
from tests.conftest import iter_api_routes

# `logout` is public on purpose: it must clear a dead cookie too (004 §5).
# `/api/setup` creates the first administrator, and only while no account exists (spec 013).
PUBLIC = {
    "/api/health",
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/config",
    "/api/setup",
}


def _has_role_marker(dependant: Dependant) -> bool:
    if getattr(dependant.call, "__celestin_roles__", None):
        return True
    return any(_has_role_marker(sub) for sub in dependant.dependencies)


def test_every_route_declares_its_roles(settings: Settings, db_engine: Engine) -> None:
    app = create_app(settings, engine=db_engine)
    routes = list(iter_api_routes(app))
    # FastAPI 0.141 nests included routers; a walk that finds nothing would pass for ever.
    assert len(routes) > 30 and PUBLIC <= {path for path, _ in routes}
    unguarded = [
        f"{','.join(route.methods or [])} {path}"
        for path, route in routes
        if path not in PUBLIC and not _has_role_marker(route.dependant)
    ]
    assert unguarded == [], unguarded


async def test_wrong_role_is_forbidden(settings: Settings, db_engine: Engine) -> None:
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import sign_in

    app = create_app(settings, engine=db_engine)
    _, headers = sign_in(app, email="parent@example.be", name="Parent", role="parent")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as ac:
        assert (await ac.get("/api/auth/me")).status_code == 200
        r = await ac.get("/api/courses")
    assert r.status_code == 403 and r.json()["code"] == "forbidden"
