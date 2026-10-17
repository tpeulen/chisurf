"""Presentation restoration remains optional for scientific session restore."""

from __future__ import annotations

import chisurf as cs


def test_restore_gui_needs_no_main_window(monkeypatch):
    """Headless project loading must not require a main window."""
    from chisurf.macros.core_fit import restore_gui_from_fits

    monkeypatch.setattr(cs, "cs", None, raising=False)
    restore_gui_from_fits(["fit-that-is-not-present"])
