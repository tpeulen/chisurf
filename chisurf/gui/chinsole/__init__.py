"""chinsole -- ChiSurf's console widget.

The one console in the application. It replaces three separate implementations:
the qtconsole ``RichJupyterWidget`` in the main window, chimol's hand-rolled
command bar, and the code editor's output panel. The only structural difference
between those was where input lives, which is a :class:`ConsoleRole` rather than
three widgets.

Quick start
-----------
>>> from chisurf.gui import chinsole                      # doctest: +SKIP
>>> console = chinsole.Chinsole()                         # doctest: +SKIP
>>> console.push({"np": numpy, "cs": chisurf})            # doctest: +SKIP
>>> console.execute("np.arange(3)")                       # doctest: +SKIP

Public surface
--------------
- Widget: :class:`Chinsole`, configured by :class:`ConsoleConfig` and
  :class:`ConsoleRole`.
- Command languages: the :class:`CommandDispatcher` protocol.
- Themes: :func:`resolve_theme`, :data:`THEMES`, :class:`ConsoleTheme`.
- Magics: :func:`register_magic`, to add one from a plugin.

The interpreter behind it is :mod:`chisurf.core.console`, which imports no Qt
and can be driven head-lessly.
"""

from __future__ import annotations

from chisurf.core.console.magics import register_magic
from chisurf.gui.chinsole.theme import (
    LEGACY_ALIASES,
    THEMES,
    ConsoleTheme,
    resolve_theme,
    theme_from_settings,
)
from chisurf.gui.chinsole.widget import (
    Chinsole,
    CommandDispatcher,
    ConsoleConfig,
    ConsoleRole,
)

__all__ = [
    "Chinsole",
    "CommandDispatcher",
    "ConsoleConfig",
    "ConsoleRole",
    "ConsoleTheme",
    "LEGACY_ALIASES",
    "THEMES",
    "register_magic",
    "resolve_theme",
    "theme_from_settings",
]
