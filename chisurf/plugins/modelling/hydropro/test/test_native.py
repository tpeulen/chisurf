"""Qt-free tests for the native HYDROPRO EMTK app."""

from __future__ import annotations

import pytest
from emtk.testing import RecordingPainter

from ..app import HydroProApp, make_app
from ..core import HydroProSettings


def test_native_settings_conversion_matches_qt_model():
    app = HydroProApp()
    app.indmode = "2"
    s = app.to_settings()
    assert s.indmode == 2
    assert isinstance(s.aer, float) and s.aer == 2.9


def test_native_state_roundtrip():
    app = HydroProApp()
    app.exe_path = "/opt/hydro++10.exe"
    app.struct_files = "a.pdb, b.pdb"
    app.indmode = "4"
    app.settings.aer = 6.1
    app.settings.nsig = 8
    app.settings.idif = 0
    state = app.export_settings()

    fresh = HydroProApp()
    fresh.restore_settings(state)
    assert fresh.exe_path == "/opt/hydro++10.exe"
    assert fresh.struct_files == "a.pdb, b.pdb"
    assert fresh.indmode == "4"
    assert fresh.settings.aer == 6.1
    assert fresh.settings.nsig == 8
    assert fresh.settings.idif == 0
    assert isinstance(fresh.settings, HydroProSettings)


def test_native_run_guards():
    app = HydroProApp()
    app._run()
    assert "structural file" in app.status
    app.struct_files = "missing.pdb"
    app._run()
    assert "executable" in app.status


def test_native_renders_all_controls():
    app = make_app()
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 760, 780)
    for expected in (
        "HYDROPRO / HYDRO++",
        "Executable",
        "Structures",
        "INDMODE",
        "AER",
        "NSIG",
        "SIGMIN",
        "SIGMAX",
        "Full diffusion tensor",
        "Run",
        "Log",
    ):
        assert expected in painter.strings, expected


def test_native_narrow_render():
    app = make_app()
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 430, 780)
    for expected in ("Executable", "INDMODE", "Run", "Log"):
        assert expected in painter.strings, expected


def test_native_tooltips_in_all_locales(monkeypatch):
    from emtk import im
    from emtk.i18n import get_locale, set_locale

    previous = get_locale()
    app = make_app()
    tips: list[str] = []
    original = im.set_item_tooltip

    def capture(text, *args, **kwargs):
        tips.append(str(text))
        return original(text, *args, **kwargs)

    monkeypatch.setattr(im, "set_item_tooltip", capture)
    try:
        for locale in ("en", "de", "fr", "es", "pt", "ru"):
            set_locale(locale)
            tips.clear()
            app.draw(RecordingPainter(), 0, 0, 760, 780)
            # 2 inputs + 5 primary + 5 solvent + 5 optional + toggle + run.
            assert len(tips) >= 18, (locale, tips)
            assert all(tip.strip() for tip in tips), locale
    finally:
        set_locale(previous)
