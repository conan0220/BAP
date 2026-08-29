"""Validation rules shared by the Desktop App and Backend."""

from __future__ import annotations

import re


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{5,64}$")
_LETTER = re.compile(r"[A-Za-z]")
_DIGIT = re.compile(r"[0-9]")


def validate_username(username: str) -> bool:
    """Return whether a Username follows the public BAP rule."""

    return USERNAME_PATTERN.fullmatch(username) is not None


def validate_password(password: str) -> bool:
    """Return whether a password follows the public BAP rule."""

    return 8 <= len(password) <= 128 and bool(_LETTER.search(password)) and bool(_DIGIT.search(password))
