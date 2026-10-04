"""Authenticated encryption for the one secret the database holds (spec 013 §3.3).

AES-256-GCM through `cryptography`. A fresh random nonce per message; `context` is the
associated data, so a ciphertext only decrypts for the purpose it was made for. Anything
that does not decrypt (a changed byte, another key, another context, a truncated token)
is the same `CipherError`: callers treat it as "not readable", never as another value.
"""

from __future__ import annotations

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_BYTES = 32
NONCE_BYTES = 12


class CipherError(ValueError):
    """The token cannot be decrypted with this key and context."""


class Cipher:
    def __init__(self, key: bytes) -> None:
        if len(key) != KEY_BYTES:
            raise ValueError(f"the encryption key must be {KEY_BYTES} bytes")
        self._aead = AESGCM(key)

    def encrypt(self, plaintext: str, *, context: str) -> str:
        nonce = os.urandom(NONCE_BYTES)
        sealed = self._aead.encrypt(nonce, plaintext.encode("utf-8"), context.encode("utf-8"))
        return base64.urlsafe_b64encode(nonce + sealed).decode("ascii")

    def decrypt(self, token: str, *, context: str) -> str:
        try:
            raw = base64.urlsafe_b64decode(token.encode("ascii"))
            if len(raw) <= NONCE_BYTES:
                raise CipherError("token too short")
            plain = self._aead.decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], context.encode("utf-8"))
            return plain.decode("utf-8")
        except (InvalidTag, binascii.Error, UnicodeError) as exc:
            raise CipherError("token cannot be decrypted") from exc
