"""Toolkit-free game list shared by the Qt and native hubs."""

GAME_PANELS = [
    {"name": "Number Quest", "icon": "🔢", "description": "Guess the hidden number in seven tries.",
     "class_path": "chisurf.plugins.misc.games.number_quest.gui.tool", "class_name": "NumberQuestWidget",
     "emtk": "chisurf.plugins.misc.games.number_quest.app:make_app",
     "keys": "Left/Right dial · Q/E steps of ten · Enter submit · R new round"},
    {"name": "Minesweeper", "icon": "💣", "description": "Clear a minefield without triggering a mine; board size is configurable.",
     "class_path": "chisurf.plugins.misc.games.minesweeper.gui.tool", "class_name": "MinesweeperWidget",
     "emtk": "chisurf.plugins.misc.games.minesweeper.gui.app:make_app",
     "keys": "Arrows move · Enter scan · F flag · Q/E board size · R reset"},
    {"name": "Tetris", "icon": "🟦", "description": "Classic falling-block puzzle with line clearing and score tracking.",
     "class_path": "chisurf.plugins.misc.games.tetris.tetris", "class_name": "Tetris",
     "emtk": "chisurf.plugins.misc.games.tetris.app:make_app",
     "keys": "Left/Right move · Down soft drop · Up rotate · Space drop · P pause · R reset"},
    {"name": "Pong", "icon": "🏓", "description": "Classic Pong against a CPU opponent, with sound and particle effects.",
     "class_path": "chisurf.plugins.misc.games.pong.pong", "class_name": "Pong",
     "emtk": "chisurf.plugins.misc.games.pong.app:make_app",
     "keys": "Up/Down paddle · W/S second player · P pause · M mode · R reset"},
    {"name": "Breakout", "icon": "🧱", "description": "Classic Breakout with progressive difficulty and multiple brick types.",
     "class_path": "chisurf.plugins.misc.games.breakout.breakout", "class_name": "Breakout",
     # emtk port incomplete (audit-all: the draw did not terminate); listed, not playable yet.
     "emtk": None,
     "keys": "Left/Right paddle · Space launch · P pause · R reset"},
]
