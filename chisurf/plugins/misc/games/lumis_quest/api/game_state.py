"""Game state for Lumis Quest: XP, levels, streaks, achievements.

The game is a thin, self-contained layer over the documentation review
system. It reads and writes a single JSON state file in the per-user data
directory. XP is the source of truth; level and progress are recomputed from
it, so the state file survives deletion.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import pathlib
import random
from typing import Any

#: Where the game state lives. Mirrors the per-user data directory used by
#: the rest of ChiSurf.
STATE_DIR = pathlib.Path.home() / ".chisurf"
STATE_FILE = STATE_DIR / "lumis_quest.json"

#: Level thresholds, cumulative XP. Front-loaded so early levels come fast
#: (the hook) and later levels take sustained effort (the retention).
LEVELS: list[tuple[int, str]] = [
    (0, "Initiate"),
    (150, "Proofreader"),
    (400, "Copy Editor"),
    (850, "Senior Editor"),
    (1700, "Documentation Wizard"),
    (3200, "Sage of the Manual"),
    (5500, "Lorekeeper"),
]

#: Variable reward schedule. The reviewer does not know which roll they got
#: until they sign off — the variable-ratio schedule that sustains engagement.
#: (probability, low, high, label)
REWARD_TABLE: list[tuple[float, int, int, str]] = [
    (0.60, 30, 50, "Standard review"),
    (0.25, 60, 80, "Thorough review"),
    (0.10, 100, 120, "Deep read"),
    (0.04, 150, 180, "Critical insight"),
    (0.01, 250, 300, "Golden review"),
]

#: Difficulty multipliers for section-level review.
DIFFICULTY_MULTIPLIER: dict[str, float] = {
    "easy": 1.0,
    "medium": 1.25,
    "hard": 1.5,
    "expert": 2.0,
}

#: Achievement definitions: (id, name, condition description).
ACHIEVEMENTS: list[tuple[str, str, str]] = [
    ("first_steps", "First Steps", "Review your first page"),
    ("warming_up", "Warming Up", "3-day streak"),
    ("week_warrior", "Week Warrior", "7-day streak"),
    ("documented_devotion", "Documented Devotion", "30-day streak"),
    ("completionist", "Completionist", "Every page in one tracked directory is reviewed"),
    ("speed_reader", "Speed Reader", "Review 5 pages in one session"),
    ("mentor", "Mentor", "Review 10 pages that were AI-reviewed only"),
    ("bug_hunter", "Bug Hunter", "Submit 5 suggestions that get merged"),
    ("renaissance_scholar", "Renaissance Scholar", "Review at least one page in every tracked directory"),
    ("stale_slayer", "Stale Slayer", "Re-review 20 stale pages"),
    ("equation_whisperer", "Equation Whisperer", "Review 10 sections tagged 'equations'"),
    ("derivation_master", "Derivation Master", "Review 5 sections tagged 'derivations'"),
    ("well_rounded", "Well-Rounded", "Review at least one section of every difficulty"),
    ("lorekeeper", "Lorekeeper", "Reach level 7"),
]


@dataclasses.dataclass
class StreakState:
    current: int = 0
    best: int = 0
    last_review_date: str = ""
    grace_days_used: list[str] = dataclasses.field(default_factory=list)
    grace_window_start: str = ""


@dataclasses.dataclass
class SessionState:
    start_time: str = ""
    reviews_this_session: int = 0


@dataclasses.dataclass
class GameState:
    reviewer: str = "anonymous"
    xp: int = 0
    streak: StreakState = dataclasses.field(default_factory=StreakState)
    session: SessionState = dataclasses.field(default_factory=SessionState)
    achievements: list[dict[str, str]] = dataclasses.field(default_factory=list)
    quests_completed: list[str] = dataclasses.field(default_factory=list)
    total_pages_reviewed: int = 0
    total_suggestions_merged: int = 0
    sections_reviewed: dict[str, int] = dataclasses.field(default_factory=dict)

    # -- level helpers -----------------------------------------------------

    @property
    def level(self) -> int:
        """1-based level for the current XP."""
        for i, (threshold, _) in enumerate(LEVELS):
            if self.xp < threshold:
                return i
        return len(LEVELS)

    @property
    def level_title(self) -> str:
        return LEVELS[self.level - 1][1]

    @property
    def level_progress(self) -> tuple[int, int]:
        """(xp into current level, xp needed for next level)."""
        if self.level >= len(LEVELS):
            return (0, 0)
        current_threshold = LEVELS[self.level - 1][0]
        next_threshold = LEVELS[self.level][0]
        return (self.xp - current_threshold, next_threshold - current_threshold)

    # -- persistence -------------------------------------------------------

    def save(self) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps(self.as_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "reviewer": self.reviewer,
            "xp": self.xp,
            "streak": dataclasses.asdict(self.streak),
            "session": dataclasses.asdict(self.session),
            "achievements": self.achievements,
            "quests_completed": self.quests_completed,
            "total_pages_reviewed": self.total_pages_reviewed,
            "total_suggestions_merged": self.total_suggestions_merged,
            "sections_reviewed": self.sections_reviewed,
        }

    @classmethod
    def load(cls, reviewer: str = "anonymous") -> "GameState":
        if not STATE_FILE.exists():
            return cls(reviewer=reviewer)
        try:
            raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return cls(reviewer=reviewer)
        streak = StreakState(**raw.get("streak", {}))
        session = SessionState(**raw.get("session", {}))
        return cls(
            reviewer=raw.get("reviewer", reviewer),
            xp=int(raw.get("xp", 0)),
            streak=streak,
            session=session,
            achievements=raw.get("achievements", []),
            quests_completed=raw.get("quests_completed", []),
            total_pages_reviewed=int(raw.get("total_pages_reviewed", 0)),
            total_suggestions_merged=int(raw.get("total_suggestions_merged", 0)),
            sections_reviewed=raw.get("sections_reviewed", {}),
        )

    # -- game actions ------------------------------------------------------

    def record_review(
        self,
        *,
        difficulty: str = "easy",
        is_first_ever: bool = False,
        is_stale: bool = False,
        in_session: bool = True,
    ) -> dict[str, Any]:
        """Award XP for one review and update streak/session/achievements.

        Returns a dict describing what happened, for the UI to celebrate.
        """
        base = self._roll_xp()
        multiplier = DIFFICULTY_MULTIPLIER.get(difficulty, 1.0)
        if is_first_ever:
            multiplier *= 1.5
        if is_stale:
            multiplier *= 0.75
        xp = int(round(base * multiplier))

        # Session tracking: 5th review in a session gets a flow bonus.
        today = datetime.date.today().isoformat()
        if self.session.start_time != today:
            self.session = SessionState(start_time=today, reviews_this_session=0)
        self.session.reviews_this_session += 1
        if self.session.reviews_this_session == 5:
            xp *= 2

        self.xp += xp
        self.total_pages_reviewed += 1
        self.sections_reviewed[difficulty] = self.sections_reviewed.get(difficulty, 0) + 1

        # Streak update.
        if self.streak.last_review_date == today:
            pass  # already reviewed today; streak holds
        elif self._is_consecutive(self.streak.last_review_date, today):
            self.streak.current += 1
        else:
            self.streak.current = 1
        self.streak.last_review_date = today
        self.streak.best = max(self.streak.best, self.streak.current)

        unlocked = self._check_achievements()
        self.save()
        return {
            "xp": xp,
            "base": base,
            "multiplier": multiplier,
            "label": self._label_for(base),
            "level": self.level,
            "level_title": self.level_title,
            "streak": self.streak.current,
            "unlocked": unlocked,
        }

    def record_suggestion_merged(self) -> dict[str, Any]:
        """Award the flat quality bonus for a merged suggestion."""
        self.xp += 100
        self.total_suggestions_merged += 1
        unlocked = self._check_achievements()
        self.save()
        return {"xp": 100, "unlocked": unlocked}

    # -- internals ---------------------------------------------------------

    def _roll_xp(self) -> int:
        r = random.random()
        cumulative = 0.0
        for prob, low, high, _ in REWARD_TABLE:
            cumulative += prob
            if r <= cumulative:
                return random.randint(low, high)
        return random.randint(30, 50)

    def _label_for(self, base: int) -> str:
        for _, low, high, label in REWARD_TABLE:
            if low <= base <= high:
                return label
        return "Standard review"

    @staticmethod
    def _is_consecutive(last: str, today: str) -> bool:
        if not last:
            return False
        try:
            last_d = datetime.date.fromisoformat(last)
            today_d = datetime.date.fromisoformat(today)
            return (today_d - last_d).days == 1
        except ValueError:
            return False

    def _check_achievements(self) -> list[str]:
        """Return the ids of any newly unlocked achievements."""
        have = {a["id"] for a in self.achievements}
        newly: list[str] = []
        today = datetime.date.today().isoformat()

        def unlock(aid: str, name: str) -> None:
            if aid not in have:
                self.achievements.append({"id": aid, "name": name, "unlocked": today})
                newly.append(aid)

        if self.total_pages_reviewed >= 1:
            unlock("first_steps", "First Steps")
        if self.streak.current >= 3:
            unlock("warming_up", "Warming Up")
        if self.streak.current >= 7:
            unlock("week_warrior", "Week Warrior")
        if self.streak.current >= 30:
            unlock("documented_devotion", "Documented Devotion")
        if self.session.reviews_this_session >= 5:
            unlock("speed_reader", "Speed Reader")
        if self.total_suggestions_merged >= 5:
            unlock("bug_hunter", "Bug Hunter")
        if self.sections_reviewed.get("hard", 0) >= 10:
            unlock("equation_whisperer", "Equation Whisperer")
        if self.sections_reviewed.get("hard", 0) >= 5:
            unlock("derivation_master", "Derivation Master")
        if len(self.sections_reviewed) >= 4:
            unlock("well_rounded", "Well-Rounded")
        if self.level >= 7:
            unlock("lorekeeper", "Lorekeeper")
        return newly
