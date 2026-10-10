"""Shell hook: open a native emtk plugin as a window of the Qt main application."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def open_native_plugin(plugin_dir: str | Path) -> Any:
    """Build, show and return the window of the plugin in *plugin_dir*.

    The plugin's ``entrypoints.emtk`` app is hosted in an ``emtk.qt_host.ControlHost``
    (the Qt shell only hosts it), exactly as the plugin menus open it.

    Parameters
    ----------
    plugin_dir : str or pathlib.Path
        Folder of the plugin, holding its ``manifest.json``.

    Returns
    -------
    QWidget
        The host window; the caller keeps a reference so it is not garbage collected.
    """
    from chisurf.core.plugin import load_manifest
    from chisurf.core.plugin.registry import build_plugin_widget

    manifest = load_manifest(Path(plugin_dir) / "manifest.json")
    if manifest is None:
        raise ValueError(f"no plugin manifest in {plugin_dir}")
    widget = build_plugin_widget(manifest)
    widget.show()
    widget.raise_()
    return widget
