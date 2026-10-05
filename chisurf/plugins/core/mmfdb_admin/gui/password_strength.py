"""Password strength: the score and the missing requirements an MMFDB password dialog shows (Qt-free).

Shared by the Qt ``PasswordChangeDialog`` and the native admin's password dialog, so
both grade a password, and refuse a weak administrator password, the same way.
"""

from __future__ import annotations

#: Characters that count as "special".
SPECIAL_CHARS = "!@#$%^&*()_+-=[]{}|;':\",./<>?"

#: Score at or above which an administrator password is accepted ("medium").
ADMIN_MIN_SCORE = 4


def score_password(password: str) -> tuple[int, list[str]]:
    """Return ``(score 0-5, missing requirements)`` for *password*."""
    score = 0
    feedback: list[str] = []
    if len(password) >= 8:
        score += 1
    else:
        feedback.append("at least 8 characters")
    if any(char.islower() for char in password):
        score += 1
    else:
        feedback.append("one lowercase letter")
    if any(char.isupper() for char in password):
        score += 1
    else:
        feedback.append("one uppercase letter")
    if any(char.isdigit() for char in password):
        score += 1
    else:
        feedback.append("one number")
    if any(char in SPECIAL_CHARS for char in password):
        score += 1
    else:
        feedback.append("one special character")
    return score, feedback


def strength_label(password: str, score: int) -> str:
    """``"Enter a password"`` / ``"Strength: Weak"`` / ``"Medium"`` / ``"Strong"``."""
    if not password:
        return "Enter a password"
    if score <= 2:
        return "Strength: Weak"
    if score <= 4:
        return "Strength: Medium"
    return "Strength: Strong"
