"""Keep this directory runnable on its own.

``chisurf/plugins/conftest.py`` builds the session ``QApplication`` and its own
comment assumes ``QT_QPA_PLATFORM=offscreen`` is already set — which the pixi
test tasks do. Run this directory directly on macOS without it and the cocoa
platform plugin aborts the interpreter inside that fixture, which reads as a
crash in whichever test happened to be first to need a widget.

``setdefault``, so a caller that deliberately asks for a real platform (the
chimol GL tests do) still gets one.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
