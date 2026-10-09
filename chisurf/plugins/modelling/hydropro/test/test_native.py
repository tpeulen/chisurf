"""Qt-free tests of the native HYDROPRO app (rewritten for the upgraded app; the earlier stream's checks that still hold are kept)."""

from __future__ import annotations

from emtk.testing import RecordingPainter

from ..app import HydroProApp, make_app
from ..core import HydroProSettings
from ..gui.model import HydroProModel


def test_native_settings_conversion_matches_qt_model():
    m = HydroProModel()
    m.indmode = "2"
    s = m.to_settings()
    assert s.indmode == 2 and isinstance(s.aer, float) and s.aer == 2.9


def test_native_state_roundtrip():
    app = HydroProApp()
    app.model.exe_path = "/opt/hydro++10.exe"
    app.model.indmode = "4"
    app.model.aer = 6.1
    app.model.nsig = 8
    app.model.idif = False
    fresh = HydroProApp()
    fresh.restore_settings(app.export_settings())
    m = fresh.model
    assert (m.exe_path, m.indmode, m.aer, m.nsig, m.idif) == (
        "/opt/hydro++10.exe",
        "4",
        6.1,
        8,
        False,
    )
    assert isinstance(m.to_settings(), HydroProSettings)


def test_native_run_guards():
    m = HydroProModel()
    m.run()
    assert m.notices[-1][0] == "No files"
    m.struct_files = "missing.pdb"
    m.run()
    assert m.exe_prompt and not m.running


def test_native_renders_all_controls():
    painter = RecordingPainter()
    for _ in range(3):
        painter = RecordingPainter()
        make_app().draw(painter, 0, 0, 1200, 800)
    for expected in (
        "Executable",
        "Structures",
        "INDMODE",
        "AER",
        "NSIG",
        "SIGMIN",
        "SIGMAX",
        "Full diffusion tensor",
        "Run",
        "Save CSV",
        "Select files…",
    ):
        assert expected in painter.strings, expected


def test_native_every_section_button_and_column_has_a_description():
    from ..app import _walk, build_spec

    spec = build_spec()
    for part in spec.values():
        for section in _walk(part):
            if section.get("type") in (
                "value",
                "choice",
                "toggle",
                "info",
                "progress",
                "custom",
                "button_row",
            ):
                assert str(section.get("description", "")).strip(), section
            for button in section.get("buttons", []):
                assert button["description"].strip(), button
            opts = section.get("options", {})
            if isinstance(opts, dict):
                for column in opts.get("columns", []):
                    assert column["tooltip"].strip(), column
