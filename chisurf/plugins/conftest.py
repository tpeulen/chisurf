import os
import pathlib
import sys

# Matplotlib must not open windows during a test run. The default backend on
# macOS is ``macosx``, a native GUI backend, so any test that draws a figure
# pops a real window onto the user's screen — and a run that is meant to be
# headless becomes interactive, can block on a window manager, and scatters
# windows over whatever else is happening. Qt is already muzzled by
# ``QT_QPA_PLATFORM=offscreen``; that setting does nothing for matplotlib, which
# picks its own backend. Set before any import pulls matplotlib in, because the
# backend is resolved at first import and cannot be changed afterwards.
os.environ.setdefault("MPLBACKEND", "Agg")

_topdir = pathlib.Path(__file__).resolve().parents[2]
if str(_topdir) not in sys.path:
    sys.path.insert(0, str(_topdir))

# No ``qapp`` fixture here: plugins import no Qt, and the few legacy tests that still ask
# for a QApplication get pytest-qt's ``qapp`` (a test dependency in pixi.toml/pyproject).

