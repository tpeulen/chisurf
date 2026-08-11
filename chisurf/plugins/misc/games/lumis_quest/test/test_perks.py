"""Test character level perks and upgrades."""

from __future__ import annotations

from chisurf.plugins.misc.games.lumis_quest.api import perks as perks_api
from chisurf.plugins.misc.games.lumis_quest.test.test_overworld import game  # noqa: F401


def test_perks_unlock_by_level():
    """Higher levels unlock progressive perks."""
    lvl1 = perks_api.unlocked_perks(1)
    assert len(lvl1) == 0

    lvl2 = perks_api.unlocked_perks(2)
    assert len(lvl2) == 1
    assert lvl2[0].key == "swift_step"

    lvl7 = perks_api.unlocked_perks(7)
    assert len(lvl7) == len(perks_api.PERKS)


def test_perks_menu_and_status(game):
    """PERKS tab displays unlocked and locked perks properly."""
    assert "PERKS" in game.TABS
    game.menu_open = True
    game.menu_tab = game.TABS.index("PERKS")
    rows = game._menu_rows()
    assert len(rows) == len(perks_api.PERKS)
    assert "[✓]" in rows[0] or "[🔒" in rows[0]

