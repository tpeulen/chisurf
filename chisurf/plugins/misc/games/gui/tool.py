"""Navigation-panel hub for the built-in games."""

from __future__ import annotations

from chisurf.gui.widgets.navigation import NavigationPanelTool

GAME_PANELS = [
    {
        "name": "Number Quest",
        "icon": "🔢",
        "description": "Guess the hidden number in seven tries.",
        "class_path": "chisurf.plugins.misc.games.number_quest.gui.tool",
        "class_name": "NumberQuestWidget",
    },
    {
        "name": "Minesweeper",
        "icon": "💣",
        "description": "Clear a minefield without triggering a mine; board size is configurable.",
        "class_path": "chisurf.plugins.misc.games.minesweeper.gui.tool",
        "class_name": "MinesweeperWidget",
    },
    {
        "name": "Tetris",
        "icon": "🟦",
        "description": "Classic falling-block puzzle with line clearing and score tracking.",
        "class_path": "chisurf.plugins.misc.games.tetris.tetris",
        "class_name": "Tetris",
    },
    {
        "name": "Pong",
        "icon": "🏓",
        "description": "Classic Pong against a CPU opponent, with sound and particle effects.",
        "class_path": "chisurf.plugins.misc.games.pong.pong",
        "class_name": "Pong",
    },
    {
        "name": "Breakout",
        "icon": "🧱",
        "description": "Classic Breakout with progressive difficulty and multiple brick types.",
        "class_path": "chisurf.plugins.misc.games.breakout.breakout",
        "class_name": "Breakout",
    },
    {
        "name": "Lumis Quest",
        "icon": "📜",
        "description": "A top-down RPG where the documentation is the world: collect real fluorophores, craft optics, and improve the docs you explore.",
        "class_path": "chisurf.plugins.misc.games.lumis_quest.gui.tool",
        "class_name": "LumisQuestWidget",
    },
]


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
