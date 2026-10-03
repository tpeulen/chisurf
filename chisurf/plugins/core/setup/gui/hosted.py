"""Factories of destinations that need a different construction when the Settings hub hosts them."""

from __future__ import annotations


def make_updates():
    """The updater, as the Qt hub embeds it: the check on start stays quiet (no "Update Available" popup)."""
    from chisurf.emtk.i18n import install
    from chisurf.plugins.core.updater.gui.app import UpdaterApp
    from chisurf.plugins.core.updater.gui.model import UpdaterModel

    install()
    return UpdaterApp(UpdaterModel(suppress_initial_notification=True))
