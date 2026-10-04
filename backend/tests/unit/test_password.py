from __future__ import annotations

import pytest

from app.domain.password import check_password


@pytest.mark.parametrize(
    ("password", "email", "name", "refused"),
    [
        ("court", "lea@example.be", "Léa", True),
        ("dix-caracteres", "lea@example.be", "Léa", False),
        ("lea-est-la-plus-forte", "lea@example.be", "Léa", True),
        ("Amandine-2026!", "lea@example.be", "Amandine", True),
        ("ab-est-partout-ici", "ab@example.be", "Ab", False),  # too short to count as personal
    ],
)
def test_policy(password: str, email: str, name: str, refused: bool) -> None:
    assert (check_password(password, email, name) is not None) is refused
