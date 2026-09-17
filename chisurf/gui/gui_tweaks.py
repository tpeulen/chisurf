from __future__ import annotations

import os
import pathlib
import sys
import tempfile

import chisurf as cs


def _sanitize_qt_plugin_path() -> None:
    """Pin Qt's plugin search path to the running interpreter's own Qt build.

    A common breakage: a launcher (e.g. PyCharm, or a shell that stack-activated
    a *base* conda env underneath the project env) inherits a ``QT_PLUGIN_PATH``
    that points at a *different* Qt installation than the one PyQt5 actually
    links against. When ``QApplication`` is created, Qt loads the platform
    plugin (``libqcocoa``) from that foreign path; if its version differs from
    the loaded ``libQt5Core`` the process aborts at the C level with::

        Cannot mix incompatible Qt library (5.15.8) with this library (5.15.15)

    This is a hard ``qFatal``/``SIGABRT`` that cannot be caught in Python, so we
    correct the environment *before* any ``QApplication`` is constructed.

    ``QLibraryInfo.PluginsPath`` is compiled into the exact ``libQt5Core`` that
    is loaded, so it always names the matching plugin directory regardless of a
    poisoned ``QT_PLUGIN_PATH``. We fall back to ``<sys.prefix>/plugins`` (the
    conda layout) if QtCore cannot be imported yet.
    """
    plugin_dir = None
    try:
        from qtpy.QtCore import QLibraryInfo

        # PyQt5/PySide2 expose ``location``; Qt6 bindings use ``path``.
        if hasattr(QLibraryInfo, "location"):
            plugin_dir = QLibraryInfo.location(QLibraryInfo.PluginsPath)
        elif hasattr(QLibraryInfo, "path"):
            plugin_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)
    except Exception:
        plugin_dir = None

    if not plugin_dir or not os.path.isdir(plugin_dir):
        fallback = os.path.join(sys.prefix, "plugins")
        plugin_dir = fallback if os.path.isdir(fallback) else None

    if not plugin_dir:
        return

    # Only override when the inherited value disagrees with the real build, so
    # correctly-configured environments are left untouched.
    if os.environ.get("QT_PLUGIN_PATH") != plugin_dir:
        os.environ["QT_PLUGIN_PATH"] = plugin_dir
    platforms_dir = os.path.join(plugin_dir, "platforms")
    if os.path.isdir(platforms_dir):
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = platforms_dir


#: Platform plugins that mean "nobody is looking at this window": a test run or
#: a headless screenshot, never a session whose layout is worth keeping.
_QA_PLATFORMS = frozenset({"offscreen", "minimal", "vnc"})

#: Opt out of :func:`isolate_qsettings_for_qa` — for the rare headless run that
#: really is meant to write the user's preferences.
_ALLOW_REAL_QSETTINGS_VAR = "CHISURF_ALLOW_REAL_QSETTINGS"

_TRUTHY = {"1", "true", "yes", "on"}


def qa_run_reason() -> str | None:
    """Say why this process counts as QA, or ``None`` when it is a real session.

    Returns
    -------
    str or None
        A short phrase naming the evidence — the offscreen platform plugin, or
        pytest driving the process — suitable for a log line.
    """
    if os.environ.get(_ALLOW_REAL_QSETTINGS_VAR, "").strip().lower() in _TRUTHY:
        return None
    platform = os.environ.get("QT_QPA_PLATFORM", "").split(":", 1)[0].strip().lower()
    if platform in _QA_PLATFORMS:
        return f"QT_QPA_PLATFORM={platform}"
    if "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules:
        return "running under pytest"
    return None


def isolate_qsettings_for_qa() -> str | None:
    """Point ``QSettings`` at a scratch directory when this is a QA run.

    Every widget that remembers something — the main window's dock layout, each
    tool's last-used paths — persists it through ``QSettings(org, app)``, and
    those two-argument constructions write the *user's* real preferences. A test
    or a headless screenshot builds the same widgets, and closing them saves:
    ``Main.closeEvent`` calls ``_save_window_state`` unconditionally. So a suite
    run in an 800×600 offscreen window would overwrite the developer's dock
    layout with the collapsed arrangement that window happened to have, and the
    next real start would restore it.

    Redirecting one seam covers all of them, and the seam is the class rather
    than ``setDefaultFormat``. ``setPath`` only ever applied to ini files — the
    native macOS backend is ``CFPreferences``, which is keyed to the logged-in
    user and ignores both ``setPath`` and ``$HOME`` — so the format has to change
    too. ``setDefaultFormat`` is documented to do that for the two-argument
    constructor and *does not* on the Qt build here: after setting it,
    ``QSettings("ChiSurf", "MainWindow").format()`` is still ``NativeFormat`` and
    the file is still the plist. Measure it before trusting it; a redirection
    that quietly fails looks exactly like one that worked.

    So ``qtpy.QtCore.QSettings`` is replaced with a subclass that rewrites the
    organization/application forms into an explicit ``IniFormat`` construction.
    Call sites are untouched: they say ``QtCore.QSettings(...)`` and get the
    subclass. A call that already names its own file is left alone — it was
    never writing the user's preferences.

    Call before the first ``QSettings`` is constructed *and* before the modules
    that do ``from qtpy.QtCore import QSettings`` are imported, which is why this
    runs from :mod:`chisurf.gui.gui_tweaks` at import.

    Returns
    -------
    str or None
        The directory preferences were redirected to, or ``None`` when this is a
        real session and the user's own preferences were left in place.
    """
    reason = qa_run_reason()
    if reason is None:
        return None
    try:
        from qtpy import QtCore
    except Exception:
        return None

    configured = os.environ.get("CHISURF_SETTINGS_DIR", "").strip()
    root = (
        pathlib.Path(configured)
        if configured
        else pathlib.Path(tempfile.gettempdir()) / "chisurf-qa-settings"
    )
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None

    base = QtCore.QSettings
    if getattr(base, "_chisurf_qa_root", None) is not None:
        return base._chisurf_qa_root

    for scope in (base.UserScope, base.SystemScope):
        base.setPath(base.IniFormat, scope, str(root))
    base.setDefaultFormat(base.IniFormat)

    class _QaQSettings(base):
        """``QSettings`` that cannot reach the user's real preferences."""

        _chisurf_qa_root = str(root)

        def __init__(self, *args, **kwargs):
            parent = kwargs.pop("parent", None)
            if args and isinstance(args[-1], QtCore.QObject):
                parent, args = args[-1], args[:-1]

            if _names_a_file(args):
                super().__init__(*args, **kwargs)
            else:
                organization, application = _organization_and_application(args, base)
                super().__init__(
                    base.IniFormat,
                    base.UserScope,
                    organization,
                    application,
                )
            if parent is not None:
                self.setParent(parent)

    QtCore.QSettings = _QaQSettings
    return str(root)


def _names_a_file(args: tuple) -> bool:
    """Whether a ``QSettings`` argument list already points at its own file.

    Those calls — ``QSettings(path, QSettings.IniFormat)`` — were never writing
    the user's preferences and are passed through untouched. ``QSettings(org,
    app)`` has the same arity, so the second argument is what separates them: a
    format enum there, an application name in the organization form.
    """
    return (
        len(args) >= 2 and isinstance(args[0], (str, os.PathLike)) and not isinstance(args[1], str)
    )


def _organization_and_application(args: tuple, base) -> tuple[str, str]:
    """Pull organization and application out of the remaining constructor forms.

    Handles ``()``, ``(organization,)``, ``(organization, application)`` and
    ``(format, scope, organization, application)``; anything the application did
    not supply falls back to what ``QCoreApplication`` was given, exactly as Qt
    itself would.
    """
    from qtpy import QtCore

    if len(args) >= 4 and not isinstance(args[0], str):
        organization, application = args[2], args[3]
    else:
        strings = [a for a in args if isinstance(a, str)]
        organization = strings[0] if strings else QtCore.QCoreApplication.organizationName()
        application = strings[1] if len(strings) > 1 else QtCore.QCoreApplication.applicationName()
    return organization or "ChiSurf", application or "ChiSurf"


# Run as a side effect of import. ``chisurf.gui`` imports this module before it
# imports ``qtpy`` and long before ``QApplication`` is created, so the corrected
# paths are in place when Qt first reads them.
_sanitize_qt_plugin_path()
isolate_qsettings_for_qa()


def apply_platform_window_tweaks(window) -> None:
    """Apply small, non-invasive tweaks to a top-level window frame.

    Currently this enables a dark titlebar on supported Windows
    versions using the DWM "immersive dark mode" attribute, so the
    outer chrome looks less like a stock bright Windows app while
    retaining native move/resize/snap behavior.
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return

    # Obtain the native HWND for this top-level window.
    try:
        hwnd = int(window.winId())
    except Exception:
        return

    try:
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20  # Windows 10 1809+
        value = ctypes.c_int(1)
        dwmapi = ctypes.windll.dwmapi

        def _set_attr(attr_id: int) -> bool:
            try:
                res = dwmapi.DwmSetWindowAttribute(
                    wintypes.HWND(hwnd),
                    ctypes.c_uint(attr_id),
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                )
                return res == 0
            except Exception:
                return False

        if not _set_attr(DWMWA_USE_IMMERSIVE_DARK_MODE):
            # Older builds used 19 for the same attribute; try as a
            # best-effort fallback.
            _set_attr(19)
    except Exception:
        # If anything goes wrong, silently fall back to the default
        # system chrome rather than risking a broken window frame.
        return


def apply_dock_tab_colors(window) -> None:
    try:
        from qtpy import QtGui, QtWidgets
    except Exception:
        return
    try:
        pass
    except Exception:
        return
    try:
        gui_cfg = getattr(cs.core.settings, "gui", {})
    except Exception:
        gui_cfg = {}
    if not isinstance(gui_cfg, dict):
        return
    try:
        hex_by_title = gui_cfg.get("dock_tab_colors")
    except Exception:
        hex_by_title = None
    if not isinstance(hex_by_title, dict) or not hex_by_title:
        return
    color_by_title = {}
    for title, value in hex_by_title.items():
        color = None
        if isinstance(value, str):
            c = QtGui.QColor(value)
            if c.isValid():
                color = c
        elif isinstance(value, (tuple, list)) and len(value) >= 3:
            try:
                r, g, b = (int(value[0]), int(value[1]), int(value[2]))
                c = QtGui.QColor(r, g, b)
                if c.isValid():
                    color = c
            except Exception:
                color = None
        if color is not None:
            color_by_title[str(title)] = color
    if not color_by_title:
        return
    try:
        tab_bars = window.findChildren(QtWidgets.QTabBar)
    except Exception:
        tab_bars = []
    for tabbar in tab_bars:
        try:
            count = tabbar.count()
        except Exception:
            continue
        for i in range(count):
            try:
                title = tabbar.tabText(i)
            except Exception:
                continue
            color = color_by_title.get(title)
            if color is not None:
                try:
                    tabbar.setTabTextColor(i, color)
                except Exception:
                    pass


# The pyqtgraph >= 0.14 ``PlotWidget.autoRangeEnabled`` compatibility shim moved
# to the chiplot pyqtgraph backend (chisurf/gui/chiplot/backends/
# pyqtgraph_backend.py), where it is applied on backend load — covering full GUI
# startup, tests, and scripts alike, without gui_tweaks importing pyqtgraph.
