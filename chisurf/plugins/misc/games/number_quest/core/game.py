"""Pure game rules for Number Quest."""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum


class GuessStatus(str, Enum):
    """The possible outcomes of a guess."""

    ACTIVE = "active"
    WON = "won"
    LOST = "lost"


@dataclass(frozen=True)
class GuessResult:
    """A snapshot returned after each guess."""

    message: str
    status: GuessStatus
    attempts_remaining: int
    score: int


class NumberQuestGame:
    """Guess a hidden number from 1 through 100 in a limited number of turns."""

    minimum = 1
    maximum = 100
    max_attempts = 7

    def __init__(self, target: int | None = None) -> None:
        self.reset(target)

    def reset(self, target: int | None = None) -> None:
        """Start a new round, optionally using a deterministic target for tests."""
        self.target = target if target is not None else random.randint(self.minimum, self.maximum)
        if not self.minimum <= self.target <= self.maximum:
            raise ValueError(f"target must be between {self.minimum} and {self.maximum}")
        self.attempts_used = 0
        self.status = GuessStatus.ACTIVE

    @property
    def attempts_remaining(self) -> int:
        """Return how many guesses remain in the current round."""
        return self.max_attempts - self.attempts_used

    @property
    def score(self) -> int:
        """Return the round score, reduced for each attempt used."""
        return max(0, 1_000 - self.attempts_used * 100)

    def guess(self, value: int) -> GuessResult:
        """Evaluate *value* and return the current game snapshot."""
        if not self.minimum <= value <= self.maximum:
            raise ValueError(f"guess must be between {self.minimum} and {self.maximum}")
        if self.status is not GuessStatus.ACTIVE:
            return self._result("Start a new round to play again.")

        self.attempts_used += 1
        if value == self.target:
            self.status = GuessStatus.WON
            return self._result(f"You found it! The number was {self.target}.")
        if self.attempts_remaining == 0:
            self.status = GuessStatus.LOST
            return self._result(f"Out of turns — the number was {self.target}.")
        hint = "Higher" if value < self.target else "Lower"
        return self._result(f"{hint}! Try again.")

    def _result(self, message: str) -> GuessResult:
        return GuessResult(
            message=message,
            status=self.status,
            attempts_remaining=self.attempts_remaining,
            score=self.score,
        )
