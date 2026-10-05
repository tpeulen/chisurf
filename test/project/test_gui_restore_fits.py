"""Presentation restoration remains optional for scientific session restore."""

from __future__ import annotations

import chisurf as cs


def test_restore_gui_requires_qapplication(monkeypatch):
    """Headless project loading must not require a QApplication or main window."""
    from chisurf.macros.core_fit import restore_gui_from_fits

    monkeypatch.setattr(cs, "cs", None, raising=False)
    restore_gui_from_fits(["fit-that-is-not-present"])
