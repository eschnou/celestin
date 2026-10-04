"""Spec 012: registration modes, the enabled flag, the admin routes, the password change."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from app.config import Settings
from tests.conftest import SAME_ORIGIN, build_app, http_client, sign_in

REGISTER = {"email": "lea@example.be", "password": "mot-de-passe-solide", "name": "Léa"}
LOGIN = {"email": REGISTER["email"], "password": REGISTER["password"]}


def _app(settings: Settings, engine: Engine, mode: str = "open"):
    return build_app(settings, engine, registration_mode=mode)


_http = http_client


# ------------------------------------------------------------------ modes


@pytest.mark.parametrize("mode", ["open", "closed", "verification"])
async def test_config_tells_the_signed_out_pages_the_mode(settings, db_engine, mode) -> None:
    async with _http(_app(settings, db_engine, mode)) as ac:
        r = await ac.get("/api/auth/config")
    assert r.status_code == 200 and r.json() == {"registration": mode, "setup_required": False}


async def test_open_mode_signs_the_new_student_in(settings, db_engine) -> None:
    async with _http(_app(settings, db_engine, "open")) as ac:
        r = await ac.post("/api/auth/register", json=REGISTER, headers=SAME_ORIGIN)
        assert r.status_code == 201 and "celestin_session=" in r.headers["set-cookie"]
        assert (await ac.get("/api/auth/me")).status_code == 200


async def test_closed_mode_refuses_registration(settings, db_engine) -> None:
    app = _app(settings, db_engine, "closed")
    async with _http(app) as ac:
        r = await ac.post("/api/auth/register", json=REGISTER, headers=SAME_ORIGIN)
    assert r.status_code == 403 and r.json()["code"] == "registration_closed"
    assert app.state.repos.users.by_email(REGISTER["email"]) is None


async def test_closed_mode_still_lets_existing_accounts_in(settings, db_engine) -> None:
    app = _app(settings, db_engine, "closed")
    sign_in(app, lesson=False)  # an account made before the door closed
    async with _http(app) as ac:
        r = await ac.post(
            "/api/auth/login",
            json={"email": "lea@example.be", "password": "mot-de-passe-solide"},
            headers=SAME_ORIGIN,
        )
    assert r.status_code == 200


async def test_verification_mode_creates_a_disabled_account_without_a_session(settings, db_engine) -> None:
    app = _app(settings, db_engine, "verification")
    async with _http(app) as ac:
        r = await ac.post("/api/auth/register", json=REGISTER, headers=SAME_ORIGIN)
        assert r.status_code == 202
        assert r.json()["pending"] is True and r.json()["user"]["email"] == "lea@example.be"
        assert "set-cookie" not in r.headers
        assert (await ac.get("/api/auth/me")).status_code == 401
    assert app.state.repos.users.by_email("lea@example.be").user.enabled is False


async def test_a_disabled_account_cannot_sign_in_but_only_a_right_password_says_so(settings, db_engine) -> None:
    app = _app(settings, db_engine, "verification")
    async with _http(app) as ac:
        await ac.post("/api/auth/register", json=REGISTER, headers=SAME_ORIGIN)
        wrong = await ac.post(
            "/api/auth/login", json={**LOGIN, "password": "pas-le-bon-mot-de-passe"}, headers=SAME_ORIGIN
        )
        right = await ac.post("/api/auth/login", json=LOGIN, headers=SAME_ORIGIN)
    assert wrong.status_code == 401 and wrong.json()["code"] == "invalid_credentials"
    assert right.status_code == 403 and right.json()["code"] == "account_disabled"
    assert "set-cookie" not in right.headers


# ------------------------------------------------------------------ admin routes


@pytest.fixture
def app(settings, db_engine):
    return _app(settings, db_engine, "verification")


async def _register_pending(app, email: str = "lea@example.be", name: str = "Léa") -> str:
    async with _http(app) as ac:
        r = await ac.post(
            "/api/auth/register",
            json={"email": email, "password": "mot-de-passe-solide", "name": name},
            headers=SAME_ORIGIN,
        )
    return r.json()["user"]["id"]


async def test_admin_lists_accounts_waiting_first(app) -> None:
    await _register_pending(app, "zoe@example.be", "Zoé")
    _, student = sign_in(app, email="ana@example.be", name="Ana", lesson=False)
    admin, headers = sign_in(app, email="admin@example.be", name="Admin", role="admin")
    async with _http(app, headers) as ac:
        r = await ac.get("/api/admin/users")
        body = r.json()
        assert r.status_code == 200
        assert [u["email"] for u in body["users"]][0] == "zoe@example.be"  # not enabled: first
        assert body["counts"] == {"total": 4, "enabled": 3, "disabled": 1}  # the idle account counts
        assert body["total"] == 4 and body["registration_mode"] == "verification"
        assert set(body["users"][0]) == {
            "id", "email", "name", "role", "locale", "enabled", "created_at", "last_seen_at"
        }  # no hash, ever
        waiting = (await ac.get("/api/admin/users", params={"status": "disabled"})).json()
        assert [u["email"] for u in waiting["users"]] == ["zoe@example.be"] and waiting["total"] == 1
        found = (await ac.get("/api/admin/users", params={"q": "AN"})).json()
        assert [u["email"] for u in found["users"]] == ["ana@example.be"]
        assert (await ac.get("/api/admin/users", params={"q": "%"})).json()["total"] == 0  # a literal, not a wildcard
        page = (await ac.get("/api/admin/users", params={"limit": 1, "offset": 1})).json()
        assert len(page["users"]) == 1 and page["total"] == 4
    assert student  # the second account existed


async def test_admin_enables_an_account_which_can_then_sign_in(app) -> None:
    user_id = await _register_pending(app)
    _, headers = sign_in(app, email="admin@example.be", name="Admin", role="admin")
    async with _http(app, headers) as ac:
        r = await ac.patch(f"/api/admin/users/{user_id}", json={"enabled": True})
    assert r.status_code == 200 and r.json()["user"]["enabled"] is True
    async with _http(app) as ac:
        login = await ac.post("/api/auth/login", json=LOGIN, headers=SAME_ORIGIN)
        assert login.status_code == 200
        assert (await ac.get("/api/auth/me")).status_code == 200


async def test_disabling_signs_the_user_out_everywhere(app) -> None:
    student, student_headers = sign_in(app, lesson=False)
    _, headers = sign_in(app, email="admin@example.be", name="Admin", role="admin")
    async with _http(app, student_headers) as ac:
        assert (await ac.get("/api/auth/me")).status_code == 200
        async with _http(app, headers) as admin_ac:
            r = await admin_ac.patch(f"/api/admin/users/{student['id']}", json={"enabled": False})
            assert r.status_code == 200 and r.json()["user"]["enabled"] is False
        assert (await ac.get("/api/auth/me")).status_code == 401  # the live session is gone


async def test_a_disabled_user_with_a_surviving_session_is_refused(app) -> None:
    """The flag is read on every request, not only at sign-in."""
    student, student_headers = sign_in(app, lesson=False)
    with app.state.repos.users._factory() as s:  # flipped behind the service's back
        from app.db.models import UserRow

        s.get(UserRow, student["id"]).enabled = False
        s.commit()
    async with _http(app, student_headers) as ac:
        assert (await ac.get("/api/auth/me")).status_code == 401


async def test_an_admin_cannot_disable_themselves(app) -> None:
    admin, headers = sign_in(app, email="admin@example.be", name="Admin", role="admin")
    async with _http(app, headers) as ac:
        r = await ac.patch(f"/api/admin/users/{admin['id']}", json={"enabled": False})
        assert r.status_code == 409 and r.json()["code"] == "own_account"
        again = await ac.patch(f"/api/admin/users/{admin['id']}", json={"enabled": True})
        assert again.status_code == 200
        assert (await ac.post(f"/api/admin/users/{admin['id']}/reset-password")).status_code == 409


async def test_reset_password_returns_one_working_password_and_ends_sessions(app) -> None:
    student, student_headers = sign_in(app, lesson=False)
    _, headers = sign_in(app, email="admin@example.be", name="Admin", role="admin")
    async with _http(app, headers) as ac:
        r = await ac.post(f"/api/admin/users/{student['id']}/reset-password")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    password = r.json()["password"]
    assert len(password) == 14 and password.isalnum() and not set(password) & set("0O1lI")
    assert "hash" not in r.text
    async with _http(app, student_headers) as ac:
        assert (await ac.get("/api/auth/me")).status_code == 401
    async with _http(app) as ac:
        old = await ac.post(
            "/api/auth/login",
            json={"email": student["email"], "password": "mot-de-passe-solide"},
            headers=SAME_ORIGIN,
        )
        new = await ac.post(
            "/api/auth/login", json={"email": student["email"], "password": password}, headers=SAME_ORIGIN
        )
    assert old.status_code == 401 and new.status_code == 200


async def test_each_reset_gives_a_different_password(app) -> None:
    student, _ = sign_in(app, lesson=False)
    _, headers = sign_in(app, email="admin@example.be", name="Admin", role="admin")
    async with _http(app, headers) as ac:
        first = (await ac.post(f"/api/admin/users/{student['id']}/reset-password")).json()["password"]
        second = (await ac.post(f"/api/admin/users/{student['id']}/reset-password")).json()["password"]
    assert first != second


async def test_unknown_user_is_404(app) -> None:
    _, headers = sign_in(app, email="admin@example.be", name="Admin", role="admin")
    async with _http(app, headers) as ac:
        assert (await ac.patch("/api/admin/users/" + "0" * 32, json={"enabled": True})).status_code == 404
        assert (await ac.post("/api/admin/users/" + "0" * 32 + "/reset-password")).status_code == 404


async def test_extra_fields_are_refused(app) -> None:
    """The route enables or disables: it cannot be talked into changing a role."""
    student, _ = sign_in(app, lesson=False)
    _, headers = sign_in(app, email="admin@example.be", name="Admin", role="admin")
    async with _http(app, headers) as ac:
        r = await ac.patch(f"/api/admin/users/{student['id']}", json={"enabled": True, "role": "admin"})
    assert r.status_code == 422
    assert app.state.repos.users.by_id(student["id"]).role == "student"


@pytest.mark.parametrize("role", ["student", "parent"])
async def test_only_admins_reach_the_admin_routes(app, role) -> None:
    other, headers = sign_in(app, email=f"{role}@example.be", name="Autre", role=role, lesson=False)
    async with _http(app, headers) as ac:
        assert (await ac.get("/api/admin/users")).status_code == 403
        assert (await ac.patch(f"/api/admin/users/{other['id']}", json={"enabled": True})).status_code == 403
        assert (await ac.post(f"/api/admin/users/{other['id']}/reset-password")).status_code == 403


async def test_signed_out_is_401_on_the_admin_routes(app) -> None:
    async with _http(app) as ac:
        assert (await ac.get("/api/admin/users")).status_code == 401


async def test_an_admin_does_not_reach_a_students_courses(app) -> None:
    _, headers = sign_in(app, email="admin@example.be", name="Admin", role="admin")
    async with _http(app, headers) as ac:
        assert (await ac.get("/api/courses")).status_code == 403


# ------------------------------------------------------------------ own password


async def test_a_user_changes_their_own_password(settings, db_engine) -> None:
    app = _app(settings, db_engine)
    async with _http(app) as ac:
        await ac.post("/api/auth/register", json=REGISTER, headers=SAME_ORIGIN)
        other = await ac.post("/api/auth/login", json=LOGIN, headers=SAME_ORIGIN)  # a second session
        other_token = other.cookies["celestin_session"]
        ac.cookies.clear()
        await ac.post("/api/auth/login", json=LOGIN, headers=SAME_ORIGIN)
        bad = await ac.post(
            "/api/auth/password",
            json={"current_password": "pas-le-bon", "new_password": "un-autre-mot-de-passe"},
            headers=SAME_ORIGIN,
        )
        weak = await ac.post(
            "/api/auth/password",
            json={"current_password": REGISTER["password"], "new_password": "court"},
            headers=SAME_ORIGIN,
        )
        ok = await ac.post(
            "/api/auth/password",
            json={"current_password": REGISTER["password"], "new_password": "un-autre-mot-de-passe"},
            headers=SAME_ORIGIN,
        )
        assert bad.status_code == 422 and bad.json()["code"] == "wrong_password"
        assert weak.status_code == 422 and weak.json()["code"] == "weak_password"
        assert ok.status_code == 204
        assert (await ac.get("/api/auth/me")).status_code == 200  # this session stays
        gone = await ac.get("/api/auth/me", headers={"authorization": f"Bearer {other_token}"})
        assert gone.status_code == 401  # the others end
        ac.cookies.clear()
        login = await ac.post(
            "/api/auth/login",
            json={**LOGIN, "password": "un-autre-mot-de-passe"},
            headers=SAME_ORIGIN,
        )
        assert login.status_code == 200


# ------------------------------------------------------------------ review follow-ups


async def test_two_admins_cannot_disable_each_other(app) -> None:
    a, headers_a = sign_in(app, email="a@example.be", name="Alpha", role="admin")
    b, headers_b = sign_in(app, email="b@example.be", name="Beta", role="admin")
    async with _http(app, headers_a) as ac_a, _http(app, headers_b) as ac_b:
        first = await ac_a.patch(f"/api/admin/users/{b['id']}", json={"enabled": False})
        assert first.status_code == 200
        # B's session went with the disabling; A is the last one standing and cannot be removed.
        second = await ac_b.patch(f"/api/admin/users/{a['id']}", json={"enabled": False})
        assert second.status_code == 401
    assert app.state.repos.users.by_id(a["id"]).enabled is True


async def test_the_last_enabled_admin_cannot_be_disabled_by_the_repository(app) -> None:
    from app.domain.errors import LastAdmin

    a, _ = sign_in(app, email="a@example.be", name="Alpha", role="admin")
    with pytest.raises(LastAdmin):
        app.state.repos.users.set_enabled(a["id"], False)
    assert app.state.repos.users.by_id(a["id"]).enabled is True


async def test_last_seen_survives_signing_out_and_a_reset(app) -> None:
    student, headers = sign_in(app, lesson=False)  # opening a session marks the account as seen
    _, admin_headers = sign_in(app, email="admin@example.be", name="Admin", role="admin")
    async with _http(app, headers) as ac:
        await ac.post("/api/auth/logout")  # by bearer: the session row is deleted
    async with _http(app, admin_headers) as ac:
        await ac.post(f"/api/admin/users/{student['id']}/reset-password")
        users = (await ac.get("/api/admin/users", params={"q": "lea"})).json()["users"]
    assert users[0]["last_seen_at"] is not None


async def test_search_ignores_case_on_accented_names(app) -> None:
    sign_in(app, email="elodie@example.be", name="Élodie", lesson=False)
    _, headers = sign_in(app, email="admin@example.be", name="Admin", role="admin")
    async with _http(app, headers) as ac:
        for needle in ("élodie", "ÉLODIE", "Élo"):
            found = (await ac.get("/api/admin/users", params={"q": needle})).json()
            assert [u["name"] for u in found["users"]] == ["Élodie"], needle


async def test_password_change_is_throttled(settings, db_engine) -> None:
    app = _app(settings.model_copy(update={"auth_attempts_per_window": 3}), db_engine)
    async with _http(app) as ac:
        await ac.post("/api/auth/register", json=REGISTER, headers=SAME_ORIGIN)
        codes = []
        for _ in range(5):
            r = await ac.post(
                "/api/auth/password",
                json={"current_password": "pas-le-bon-mot", "new_password": "un-autre-mot-de-passe"},
                headers=SAME_ORIGIN,
            )
            codes.append(r.status_code)
    assert codes == [422, 422, 422, 429, 429]
