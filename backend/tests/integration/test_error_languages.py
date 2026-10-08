"""Spec 010 R5.1-R5.3: an error reaches the student in the language of the request,
on every channel that carries one, with its code unchanged."""

from __future__ import annotations

from tests.conftest import LESSON, sign_in, sse_frames as frames
from tests.fixtures.fake_llm import ExplodingLLM
from app.domain.errors import ProviderRateLimited

EN = {"accept-language": "en-GB,en;q=0.9"}
FR_HEADER = {"accept-language": "fr-BE,fr;q=0.9"}


async def test_an_http_error_follows_the_browser_when_nobody_is_signed_in(anon_client) -> None:
    english = await anon_client.get("/api/auth/me", headers=EN)
    assert english.status_code == 401 and english.json()["code"] == "not_authenticated"
    assert english.json()["message"] == "Sign in to continue."
    french = await anon_client.get("/api/auth/me", headers=FR_HEADER)
    assert french.json()["message"] == "Connecte-toi pour continuer."
    nothing = await anon_client.get("/api/auth/me")
    assert nothing.json()["message"] == "Connecte-toi pour continuer."


async def test_an_http_error_follows_the_account_over_the_browser(client) -> None:
    await client.patch("/api/auth/me", json={"locale": "en"})
    missing = await client.get("/api/courses/" + "ab" * 16, headers=FR_HEADER)
    assert missing.status_code == 404 and missing.json()["code"] == "not_found"
    assert missing.json()["message"] == "This page doesn't exist."
    await client.patch("/api/auth/me", json={"locale": "fr"})
    again = await client.get("/api/courses/" + "ab" * 16, headers=EN)
    assert again.json()["message"] == "Cette page n'existe pas."


async def test_login_failure_and_rate_limit_follow_the_header(anon_client) -> None:
    bad = await anon_client.post(
        "/api/auth/login",
        json={"email": "nobody@example.be", "password": "wrong-password"},
        headers={**EN, "sec-fetch-site": "same-origin"},
    )
    assert bad.json() == {"code": "invalid_credentials", "message": "Incorrect email or password."}


async def test_a_weak_password_is_refused_in_the_visitors_language(anon_client) -> None:
    body = {"email": "ann@example.be", "password": "short", "name": "Ann"}
    r = await anon_client.post(
        "/api/auth/register", json=body, headers={**EN, "sec-fetch-site": "same-origin"}
    )
    assert r.status_code == 422 and r.json()["code"] == "weak_password"
    assert r.json()["message"] == "The password must be at least 6 characters long."
    r = await anon_client.post(
        "/api/auth/register", json=body, headers={**FR_HEADER, "sec-fetch-site": "same-origin"}
    )
    assert r.json()["message"] == "Le mot de passe doit faire au moins 6 caractères."


async def test_the_same_origin_refusal_follows_the_header(anon_client) -> None:
    r = await anon_client.post(
        "/api/auth/login",
        json={"email": "a@example.be", "password": "x"},
        headers={**EN, "sec-fetch-site": "cross-site"},
    )
    assert r.status_code == 403 and r.json() == {"code": "cross_origin", "message": "Request refused."}
    r = await anon_client.post(
        "/api/auth/login",
        json={"email": "a@example.be", "password": "x"},
        headers={"sec-fetch-site": "cross-site"},
    )
    assert r.json()["message"] == "Requête refusée."


async def test_the_body_limit_refusal_follows_the_header(make_client) -> None:
    from tests.fixtures.fake_llm import FakeLLM

    client, _ = make_client(FakeLLM([]))
    big = {**LESSON, "history": [{"kind": "learner", "text": "x" * 1_100_000}]}
    async with client:
        r = await client.post("/api/chat", json=big, headers=EN)
        assert r.status_code == 413 and r.json()["code"] == "payload_too_large"
        assert r.json()["message"] == "Your message is too long. Shorten it and send it again."
        r = await client.post("/api/chat", json=big)
        assert r.json()["message"] == "Ton message est trop long. Raccourcis-le et renvoie-le."


async def test_an_error_event_in_a_stream_follows_the_account(make_client) -> None:
    client, _ = make_client(ExplodingLLM(ProviderRateLimited()), locale="en")
    async with client:
        r = await client.post("/api/chat", json={**LESSON, "history": []}, headers=FR_HEADER)
    error = next(data for name, data in frames(r.text) if name == "error")
    assert error["code"] == "provider_rate_limited"
    assert error["message"] == "Too many requests at once. Wait a few seconds and try again."


async def test_an_error_event_in_a_stream_is_french_by_default(make_client) -> None:
    client, _ = make_client(ExplodingLLM(ProviderRateLimited()))
    async with client:
        r = await client.post("/api/chat", json={**LESSON, "history": []})
    error = next(data for name, data in frames(r.text) if name == "error")
    assert "Attends quelques secondes" in error["message"]


async def test_a_voice_route_error_follows_the_account(make_voice_client) -> None:
    from tests.integration.test_voice_endpoint import EMPTY, FakeRealtime

    async with make_voice_client(FakeRealtime(), voice_enabled=False, locale="en") as client:
        r = await client.post("/api/voice/session", json=EMPTY)
    assert r.status_code == 503 and r.json()["code"] == "voice_disabled"
    assert r.json()["message"] == "Voice isn't turned on for this installation."


async def test_a_second_account_keeps_its_own_language(client) -> None:
    _, other_headers = sign_in(client.app, email="other@example.be", name="Other", locale="en")  # type: ignore[attr-defined]
    english = await client.get("/api/courses/" + "ab" * 16, headers=other_headers)
    assert english.json()["message"] == "This page doesn't exist."
    french = await client.get("/api/courses/" + "ab" * 16)
    assert french.json()["message"] == "Cette page n'existe pas."


NL = {"accept-language": "nl-BE,nl;q=0.9"}


async def test_an_error_reaches_a_flemish_visitor_in_dutch(anon_client) -> None:
    """Spec 017 R1.3, R1.7."""
    r = await anon_client.get("/api/auth/me", headers=NL)
    assert r.status_code == 401 and r.json() == {"code": "not_authenticated", "message": "Meld je aan om verder te gaan."}
    bad = await anon_client.post(
        "/api/auth/login",
        json={"email": "nobody@example.be", "password": "wrong-password"},
        headers={**NL, "sec-fetch-site": "same-origin"},
    )
    assert bad.json() == {"code": "invalid_credentials", "message": "E-mailadres of wachtwoord is niet juist."}
    weak = await anon_client.post(
        "/api/auth/register",
        json={"email": "ann@example.be", "password": "short", "name": "Ann"},
        headers={**NL, "sec-fetch-site": "same-origin"},
    )
    assert weak.json()["code"] == "weak_password"
    assert weak.json()["message"] == "Het wachtwoord moet minstens 6 tekens lang zijn."


async def test_the_account_language_wins_over_the_browser_for_dutch_too(client) -> None:
    await client.patch("/api/auth/me", json={"locale": "nl"})
    missing = await client.get("/api/courses/" + "ab" * 16, headers=FR_HEADER)
    assert missing.status_code == 404 and missing.json()["message"] == "Deze pagina bestaat niet."
