"""GUI startup service entrypoints for the ChiSurf app lifecycle.

These functions are referenced by JSON config files in
``chisurf/startup/services.d/`` and receive an ``AppStartupContext``.
"""

from __future__ import annotations

import importlib

import chisurf as cs
from chisurf.gui import dialogs

# Imported for their side effects: binding ``cs.gui.widgets`` & co. as package
# attributes, installing the exception hook. Spelled as ``import_module`` so a
# lint autofix cannot mistake them for unused imports and delete them.
_GUI_MODULES = (
    "chisurf.core.settings",
    "chisurf.core.base",
    "chisurf.core.support.common",
    "chisurf.core.curve",
    "chisurf.core.support.decorators",
    "chisurf.core.parameter",
    "chisurf.core.experiments",
    "chisurf.core.fio",
    "chisurf.gui.decorators",
    "chisurf.gui.widgets",
    "chisurf.gui.widgets.ipython",
    "chisurf.macros",
    "chisurf.core.math",
)

_DEFERRED_MODULES = (
    "chisurf.core.fitting",
    "chisurf.core.fluorescence",
    "chisurf.core.models",
    "chisurf.gui.plots",
    "chisurf.core.structure",
)


def _import_all(names) -> None:
    """Import each dotted module name in ``names`` for its side effects."""
    for name in names:
        importlib.import_module(name)


def _get_window(context):
    """Return the main window for a startup service.

    The splash phase receives the window as the ``startup_interface``
    dependency. The ``post_gui_show`` runner only passes the dependencies a
    service declares, and none of those services declared it -- so
    ``populate_plugins``, ``register_experiment_models`` and
    ``bind_history_science`` each got ``None`` and returned without doing
    anything (an empty model list for every non-global dataset). The window
    exists by then: the runner passes it as ``context.main_window``, and
    ``chisurf.cs`` is the last resort. A missing window is logged rather than
    silently skipped.
    """
    window = (
        context.dependencies.get("startup_interface")
        or getattr(context, "main_window", None)
        or getattr(cs, "cs", None)
    )
    if window is None:
        cs.logging.error("Startup service has no main window; it did nothing.")
    return window


def gui_imports(context) -> None:
    """Import core GUI modules needed for the main window scaffold."""
    _import_all(_GUI_MODULES)
    if cs.core.settings.exceptions_on_gui:
        importlib.import_module("chisurf.gui.exception_hook")


def setup_ipython(context) -> None:
    """Create the IPython console widget."""
    importlib.import_module("chisurf.gui.widgets.ipython")
    cs.console = cs.gui.widgets.ipython.QIPythonWidget()
    cs.console.history_widget = None


def startup_interface(context) -> object:
    """Create the main window and return it via context.dependencies."""
    from chisurf.gui.main import Main

    window = Main()
    cs.cs = window
    importlib.import_module("chisurf.core.base")
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


def register_experiment_models(context) -> None:
    """Resolve deferred experiment model classes on the main window.

    ``_setup_experiment`` defers model-class resolution (heavy catalogue
    imports: pda3c → scipy.stats, fcs/stopped-flow parsers) off the splash
    critical path; this service drains the pending list right after the
    window is shown, before plugins can load a dataset that needs them.
    """
    window = _get_window(context)
    if window is not None:
        window.register_experiment_models()


def bind_history_science(context) -> None:
    """Bind history science capture/publish on the main window.

    Moved out of ``_init_history_browser`` (splash critical path): the baseline
    capture in :meth:`HistoryMixin._init_history_browser` imports
    ``chisurf.core.fitting`` and costs over a second of cold-start. Must run
    before any scientific edit is possible, hence before ``populate_plugins``
    in this phase.
    """
    window = _get_window(context)
    if window is not None:
        cs.history.configure_science(
            window._capture_history_science, window._publish_history_science
        )


def start_autosave(context) -> None:
    """Start the silent project autosave on the main window.

    Reads ``project.autosave`` (``enabled``, ``interval_s``) from the settings
    and drives :meth:`ProjectMixin._autosave_tick` from a timer owned by the
    window, so it stops with it. The tick itself is Qt-free; only the clock is
    Qt here.
    """
    window = _get_window(context)
    if window is None:
        return
    from qtpy import QtCore

    from chisurf.core.project.lifecycle import Autosave

    settings = getattr(cs.core.settings, "cs_settings", {}) or {}
    config = (settings.get("project") or {}).get("autosave") or {}
    try:
        interval_s = max(1.0, float(config.get("interval_s", 120)))
    except (TypeError, ValueError):
        interval_s = 120.0
    enabled = bool(config.get("enabled", True))
    window._autosave = Autosave(interval_s=interval_s, enabled=enabled)
    previous = getattr(window, "_autosave_timer", None)
    if previous is not None:
        previous.stop()
    timer = QtCore.QTimer(window)
    timer.setInterval(int(interval_s * 1000))
    timer.timeout.connect(window._autosave_tick)
    window._autosave_timer = timer
    if enabled:
        timer.start()


def deferred_gui_imports(context) -> None:
    """Import heavy functional submodules."""
    _import_all(_DEFERRED_MODULES)


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
