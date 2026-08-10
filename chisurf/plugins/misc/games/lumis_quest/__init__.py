"""Lumis Quest — turn documentation review into an engaging game.

A game inside ChiSurf's Games hub that layers XP, streaks, quests, and
achievements on top of the existing documentation review system
(``chisurf.plugins.core.help.api.review``). The game does not replace the
sign-off gate; it makes the act of reviewing worth doing.
"""

from __future__ import annotations

from chisurf.plugins.misc.games.lumis_quest.api.game_state import (
    GameState,
)

__all__ = ["GameState"]
