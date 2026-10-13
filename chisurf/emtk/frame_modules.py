"""What an emtk frame imports lazily, imported on the UI thread before any worker can start.

One thread at a time imports a module for the first time (:mod:`chisurf._import_gate`): that is what
keeps a worker and the frame loop from deadlocking on CPython's module locks. Its price is a wait: a
frame that first-imports a module while a worker is inside an import waits for the worker's whole
import. emtk imports its font, glyph, tooltip, maths-text and table modules lazily, from inside the
first frames, so :func:`import_frame_modules` imports them where an app is made -- the shell's
constructor, :func:`chisurf.emtk.plugins.load_plugin` and every worker start in
:mod:`chisurf.emtk.background_build` -- in the UI thread, before a worker exists.

The list is measured, not guessed: the modules the UI thread first-imported while each of the 120
emtk plugins drew its frames -- every emtk module among them, and the font and image modules that
ten or more plugins' first frames import anyway (about 30 ms together). What a frame still waits for
is the *gate wait* column of ``python -m build_tools.dev_utils.plugin_frame_times``.
"""

from __future__ import annotations

import importlib
import threading

#: The UI thread's lazy first imports while plugins draw: emtk's, and the font/image modules most frames need.
FRAME_MODULES = (
    "emtk.im_widgets",
    "emtk.font_render",
    "emtk.dynamic_font",
    "emtk.fonts",
    "emtk.cpp_compat",
    "emtk.offset_painter",
    "emtk.htmltext",
    "emtk.colormaps",
    "emtk.mathtext",
    "emtk.tooltip",
    "emtk.ime",
    "emtk.i18n.catalogue",
    "emtk.widgets.data_table",
    "emtk.widgets.menus",
    "emtk.widgets.table_menu",
    "emtk.widgets.markdown",
    "emtk.widgets.markers",
    "emtk.widgets.sliders",
    "emtk.widgets.text_editor",
    "emtk.widgets.text_field",
    "fontTools.ttLib",
    "fontTools.ttLib.tables._c_m_a_p",
    "fontTools.ttLib.tables._m_a_x_p",
    "fontTools.ttLib.tables._p_o_s_t",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFile",
    "PIL.features",
)

_done = False


def import_frame_modules() -> None:
    """Import :data:`FRAME_MODULES` once, on the UI thread; from any other thread do nothing.

    A worker importing them would be the wait this avoids, so only the main thread does.
    """
    global _done
    if _done or threading.current_thread() is not threading.main_thread():
        return
    _done = True
    for name in FRAME_MODULES:
        importlib.import_module(name)


__all__ = ["FRAME_MODULES", "import_frame_modules"]
