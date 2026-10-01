"""Navigation-panel hub for the built-in games."""

from __future__ import annotations

from chisurf.gui.widgets.navigation import NavigationPanelTool

from .registry import GAME_PANELS


class GamesWidget(NavigationPanelTool):
    """Group the small games in the shared navigation-panel shell."""

    name = "Games"

    def __init__(self, parent=None) -> None:
        super().__init__(
            title="Games",
            panels=GAME_PANELS,
            parent=parent,
            # The arcade games are fixed-size (up to 800x650); keep the panel
            # area large enough to show them without clipping.
            minimum_size=(1020, 700),
            initial_size=(1060, 730),
            navigation_width=180,
            searchable=False,
            settings_key="games",
        )
