"""ChiSurf's built-in games: Number Quest, Minesweeper, Tetris, Pong and Breakout.

Each game is a plugin of its own (``Tools › Games`` in the ribbon) and opens in a
dock of its own. This package only holds what the games share: the window
lifecycle and declared header row (:mod:`._base`, ``game_header.view.json``),
the audio voices (:mod:`._audio`), the header translations
(:mod:`._translations`) and the shortcut filter (:mod:`._keys`). It has no
manifest, so it is not a plugin itself.
"""
