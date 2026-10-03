"""Factories of destinations that need a different construction when the Settings hub hosts them."""

from __future__ import annotations


def make_updates():
    """The updater, as the Qt hub embeds it: the check on start stays quiet (no "Update Available" popup)."""
    from chisurf.emtk.i18n import install
    from chisurf.plugins.core.updater.gui.app import UpdaterApp
    from chisurf.plugins.core.updater.gui.model import UpdaterModel

    install()
    return UpdaterApp(UpdaterModel(suppress_initial_notification=True))


def make_lut_tools(settings_dir=None):
    """TTTR LUT Tools with its preferences file in the hub's settings folder (never a path resolved behind its back)."""
    from pathlib import Path

    from chisurf.plugins.tttr.tttr_lut_tools.gui.app import create_app

    if settings_dir is None:
        return create_app()
    return create_app(preferences_path=Path(settings_dir) / "tttr_lut_tools_native.json")
