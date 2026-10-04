"""Spec 013 §3.3: authenticated encryption of the stored API key."""

from __future__ import annotations

import base64
import os

import pytest

from app.services.cipher import Cipher, CipherError

CONTEXT = "celestin:openai_api_key:v1"


def test_round_trip() -> None:
    cipher = Cipher(os.urandom(32))
    token = cipher.encrypt("sk-secret-value", context=CONTEXT)
    assert "sk-secret-value" not in token
    assert cipher.decrypt(token, context=CONTEXT) == "sk-secret-value"


def test_two_encryptions_of_one_plaintext_differ() -> None:
    cipher = Cipher(os.urandom(32))
    assert cipher.encrypt("same", context=CONTEXT) != cipher.encrypt("same", context=CONTEXT)


def test_a_changed_byte_is_refused() -> None:
    cipher = Cipher(os.urandom(32))
    raw = bytearray(base64.urlsafe_b64decode(cipher.encrypt("sk-secret", context=CONTEXT)))
    raw[-1] ^= 1
    with pytest.raises(CipherError):
        cipher.decrypt(base64.urlsafe_b64encode(bytes(raw)).decode(), context=CONTEXT)


def test_another_key_is_refused() -> None:
    token = Cipher(os.urandom(32)).encrypt("sk-secret", context=CONTEXT)
    with pytest.raises(CipherError):
        Cipher(os.urandom(32)).decrypt(token, context=CONTEXT)


def test_another_context_is_refused() -> None:
    cipher = Cipher(os.urandom(32))
    token = cipher.encrypt("sk-secret", context=CONTEXT)
    with pytest.raises(CipherError):
        cipher.decrypt(token, context="celestin:something_else:v1")


@pytest.mark.parametrize("token", ["", "!!!not base64!!!", "AAAA", base64.urlsafe_b64encode(b"x" * 12).decode()])
def test_malformed_tokens_are_refused(token: str) -> None:
    with pytest.raises(CipherError):
        Cipher(os.urandom(32)).decrypt(token, context=CONTEXT)


def test_the_key_must_be_32_bytes() -> None:
    with pytest.raises(ValueError):
        Cipher(b"short")
