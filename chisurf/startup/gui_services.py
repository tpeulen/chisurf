"""GUI startup service entrypoints for the ChiSurf app lifecycle.

These functions are referenced by JSON config files in
``chisurf/startup/services.d/`` and receive an ``AppStartupContext``.
"""

from __future__ import annotations

import chisurf as cs
from chisurf.gui import dialogs


def _get_window(context):
    """Return the main window from context dependencies."""
    return context.dependencies.get("startup_interface")


def gui_imports(context) -> None:
    """Import core GUI modules needed for the main window scaffold."""
    if cs.core.settings.exceptions_on_gui:
        pass


def setup_ipython(context) -> None:
    """Create the IPython console widget."""
    cs.console = cs.gui.widgets.ipython.QIPythonWidget()
    cs.console.history_widget = None


def startup_interface(context) -> object:
    """Create the main window and return it via context.dependencies."""
    from chisurf.gui.main import Main

    window = Main()
    cs.cs = window
    cs.core.base.set_safe_import_notify(
        lambda title, text: dialogs.information(window, title, text)
    )
    return window


def setup_logging(context) -> None:
    """Attach logging widgets to the main window status bar."""
    from chisurf.gui import setup_logging_widgets

    window = _get_window(context)
    if window is not None:
        setup_logging_widgets(window)


def init_setups(context) -> None:
    """Initialize detector setups on the main window."""
    window = _get_window(context)
    if window is not None:
        window.init_setups()


def restore_setup_defaults(context) -> None:
    """Restore saved setup defaults."""
    window = _get_window(context)
    if window is not None:
        window._restore_setup_defaults()


def define_actions(context) -> None:
    """Define actions on the main window."""
    window = _get_window(context)
    if window is not None:
        window.define_actions()


def load_tools(context) -> None:
    """Load tools on the main window."""
    window = _get_window(context)
    if window is not None:
        window.load_tools()


def init_executors(context) -> None:
    """Initialize GUI executors."""
    try:
        from chisurf.gui import initialize_gui_executors

        initialize_gui_executors()
    except Exception:
        pass


def arrange_widgets(context) -> None:
    """Arrange widgets on the main window."""
    window = _get_window(context)
    if window is not None:
        window.arrange_widgets()


def setup_style(context) -> None:
    """Apply the configured stylesheet."""
    from qtpy import QtWidgets

    from chisurf.gui import set_app_style

    app = QtWidgets.QApplication.instance()
    if app is not None:
        set_app_style(app)
    from chisurf.gui import setup_gui

    qt_app = QtWidgets.QApplication.instance()
    if qt_app is not None:
        try:
            setup_gui(app=qt_app, stage="setup_style")
        except Exception:
            pass


def deferred_gui_imports(context) -> None:
    """Import heavy functional submodules."""


def populate_plugins(context) -> None:
    """Populate the plugin menu."""
    from chisurf.gui import setup_gui

    window = _get_window(context)
    if window is not None:
        from qtpy import QtWidgets

        try:
            setup_gui(
                app=QtWidgets.QApplication.instance(), stage="populate_plugins", window=window
            )
        except Exception:
            pass


def check_updates(context) -> None:
    """Check for application updates."""
    from chisurf.gui import setup_gui

    window = _get_window(context)
    if window is not None:
        from qtpy import QtWidgets

        try:
            setup_gui(app=QtWidgets.QApplication.instance(), stage="check_updates", window=window)
        except Exception:
            pass


def warmup_imports(context) -> None:
    """Preload modules for a snappier first interaction."""
    try:
        from chisurf.gui.misc_helpers import warmup_imports as _warmup

        _warmup()
    except Exception:
        pass
