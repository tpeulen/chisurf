"""Native LUT scientific workflow, persistence, UI and isolation regressions."""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.tttr.tttr_lut_tools.gui.controller import LutWorkspace

ROOT = Path(__file__).resolve().parents[5]
SPC = ROOT / "test/data/tttr/BH/132/BH_SPC132.spc"


@pytest.fixture
def workspace():
    model = LutWorkspace()
    model.load_compute([SPC])
    return model


def test_channel_calibration_and_production_correction(workspace):
    from chisurf.core.fio.staging import open_tttr

    channels = workspace.compute.available_channels
    assert channels == [0, 1, 8, 9]
    workspace.bridge()
    assert sorted(workspace.channel_luts) == channels
    assert not np.array_equal(workspace.channel_luts[0], workspace.channel_luts[1])
    workspace.load_preview([SPC])
    workspace.active_channel = 0
    workspace.set_shift(3)
    tttr = open_tttr(
        SPC,
        channel_luts=workspace.channel_luts,
        channel_shifts=workspace.channel_shifts,
        apply_lut=True,
    )
    mask = np.asarray(tttr.routing_channels) == 0
    expected = np.bincount(
        np.asarray(tttr.micro_times)[mask].astype(int), minlength=len(workspace.corrected[0])
    )
    np.testing.assert_array_equal(workspace.corrected[0], expected)
    assert workspace.raw[0].sum() == workspace.corrected[0].sum()


def test_import_assign_remove_export_and_settings_roundtrip(workspace, tmp_path):
    lut_path = tmp_path / "correction.npz"
    workspace.compute.save_lut(str(lut_path))
    workspace.import_lut(lut_path)
    workspace.load_preview([SPC])
    workspace.active_channel = 1
    workspace.assign()
    np.testing.assert_array_equal(workspace.channel_luts[1], workspace.loaded_luts[lut_path.name])
    workspace.assign(True)
    assert sorted(workspace.channel_luts) == [0, 1, 8, 9]
    workspace.set_shift(-2)
    path = tmp_path / "settings.tttr.json"
    workspace.export_settings(path)
    fresh = LutWorkspace()
    fresh.import_settings(path)
    assert fresh.channel_shifts == {1: -2}
    for channel in fresh.channel_luts:
        np.testing.assert_array_equal(fresh.channel_luts[channel], workspace.channel_luts[channel])
    workspace.remove_lut()
    assert not workspace.loaded_luts
    assert workspace.channel_luts  # Removal from import list retains assignments, as Qt does.
    workspace.clear_luts()
    assert not workspace.channel_luts
    assert workspace.channel_shifts == {1: -2}


def test_export_formats_and_corrected_photon_count(workspace, tmp_path):
    from chisurf.plugins.tttr.tttr_lut_tools.api.io import load_lut_file

    for ext in ("json", "npy", "npz", "txt", "csv"):
        path = tmp_path / f"lut.{ext}"
        workspace.compute.save_lut(str(path))
        np.testing.assert_allclose(
            load_lut_file(str(path)), workspace.compute.current_table["NTAC_fract"]
        )
    for ext in ("npy", "npz", "txt", "csv"):
        path = tmp_path / f"photons.{ext}"
        workspace.compute.export_corrected(str(path))
        values = (
            np.load(path)["corrected_ntac"]
            if ext == "npz"
            else np.load(path)
            if ext == "npy"
            else np.loadtxt(path, delimiter="," if ext == "csv" else None)
        )
        assert len(values) == len(workspace.compute.micro)


def test_preferences_preserve_hand_tuned_region_selection_and_callback(workspace, tmp_path):
    applied = []
    workspace.bridge()
    workspace.load_preview([SPC])
    workspace.compute.linear_start = 1800
    workspace.compute.linear_stop = 2100
    workspace.compute.channel = "1"
    workspace.compute._select_channel()
    workspace.compute.linear_start = 1800
    workspace.compute.linear_stop = 2100
    workspace.compute.compute()
    workspace.active_channel = 1
    workspace.visible = {0, 1}
    workspace.show_lut = True
    path = tmp_path / "prefs.json"
    workspace.save_preferences(path)
    fresh = LutWorkspace(applied.append)
    fresh.set_state(json.loads(path.read_text()))
    assert fresh.compute.channel == "1"
    assert (fresh.compute.linear_start, fresh.compute.linear_stop) == (1800, 2100)
    assert fresh.active_channel == 1
    assert fresh.visible == {0, 1}
    assert fresh.show_lut
    fresh.apply()
    assert applied[0]["channel_luts"]


def test_actual_factory_is_qt_free(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "tools/emtk_migration/check_native.py",
            "--factory",
            "chisurf.plugins.tttr.tttr_lut_tools.gui.app:create_app",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(result.stdout.splitlines()[-1])
    assert record["qt_modules"] == []


def test_populated_both_stages_render_with_tooltips_in_all_languages(workspace, caplog):
    from emtk import i18n
    from emtk.testing import RecordingPainter

    from chisurf.plugins.tttr.tttr_lut_tools.gui.app import LutToolsApp
    from chisurf.plugins.tttr.tttr_lut_tools.gui.translations import _ROWS, tr

    workspace.bridge()
    workspace.load_preview([SPC])
    app = LutToolsApp()
    app.model = workspace
    try:
        for locale in ("en", "de", "fr", "es", "pt", "ru"):
            i18n.set_locale(locale)
            for row in _ROWS.strip().splitlines():
                source, *translations = row.split("|")
                assert tr(source) == (
                    source
                    if locale == "en"
                    else translations[("de", "fr", "es", "pt", "ru").index(locale)]
                )
            for stage in (0, 1):
                app.stage = stage
                app.model.show_lut = True
                for size in ((1200, 800), (800, 600)):
                    painter = RecordingPainter()
                    app.draw(painter, 0, 0, *size)
                    assert painter.strings
        assert not [r for r in caplog.records if r.levelname == "ERROR"]
        assert {"Save LUT", "Load LUT", "Assign selected", "Save JSON", "Shift"} <= set(
            app.item_rects
        )
    finally:
        app.close()
        i18n.set_locale("en")


def test_photon_container_is_accepted_like_vendor_file(workspace, tmp_path):
    from chisurf.core.fio.pto import Measurement

    with Measurement.create(SPC, out_dir=tmp_path) as container:
        container_path = container.path
    model = LutWorkspace()
    model.load_compute([container_path])
    np.testing.assert_array_equal(model.compute.counts, workspace.compute.counts)
    model.load_preview([container_path])
    assert sorted(model.raw) == [0, 1, 8, 9]


def test_tooltip_hover_and_context_removal_are_real_input(workspace):
    from emtk import i18n
    from emtk.app import LEFT_BUTTON, RIGHT_BUTTON
    from emtk.im_core import Style
    from emtk.testing import RecordingPainter

    from chisurf.plugins.tttr.tttr_lut_tools.gui.app import LutToolsApp

    i18n.set_locale("en")
    app = LutToolsApp()
    app.model = workspace
    app.model.bridge()
    app.stage = 1
    app.style = Style(tooltip_delay=0)
    try:
        app.draw(RecordingPainter(), 0, 0, 1200, 900)
        x, y, w, h = app.item_rects["Load LUT"]
        app.hover(x + w / 2, y + h / 2)
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 1200, 900)
        assert any("Import a cumulative LUT" in str(item) for item in painter.strings)
        name = app.model.selected_lut
        x, y, w, h = app.item_rects["lut:" + name]
        app.pointer_press(x + w / 2, y + h / 2, RIGHT_BUTTON)
        app.draw(RecordingPainter(), 0, 0, 1200, 900)
        app.pointer_release(x + w / 2, y + h / 2, RIGHT_BUTTON)
        app.draw(RecordingPainter(), 0, 0, 1200, 900)
        states = [
            value
            for key, value in app.storage.items()
            if isinstance(key, tuple)
            and key[0] == "__state__"
            and isinstance(key[1], tuple)
            and key[1][0] == "context_popup"
            and isinstance(value, dict)
            and value.get("popup")
        ]
        assert len(states) == 1
        popup = states[0]["popup"]
        assert popup.entries[0].label == "Remove LUT"
        assert "retain assignments" in popup.entries[0].tooltip
        entry, rect = popup._rows[0]
        x, y, w, h = rect
        app.pointer_press(x + w / 2, y + h / 2, LEFT_BUTTON)
        app.draw(RecordingPainter(), 0, 0, 1200, 900)
        app.pointer_release(x + w / 2, y + h / 2, LEFT_BUTTON)
        app.draw(RecordingPainter(), 0, 0, 1200, 900)
        assert name not in app.model.loaded_luts
        assert app.model.channel_luts
    finally:
        app.close()


def test_json_preview_can_copy_and_close_with_pointer_input(monkeypatch):
    from emtk import clipboard, i18n
    from emtk.testing import RecordingPainter

    from chisurf.plugins.tttr.tttr_lut_tools.gui.app import LutToolsApp

    i18n.set_locale("en")
    copied = []
    monkeypatch.setattr(clipboard, "copy", copied.append)
    app = LutToolsApp()
    app.model.receive_computed_lut("example", [0, 1, 2, 3], 0)
    app.show_json = True
    try:
        for label in ("Copy JSON", "Close"):
            app.draw(RecordingPainter(), 0, 0, 1200, 900)
            x, y, w, h = app.item_rects[label]
            app.press(x + w / 2, y + h / 2)
            app.draw(RecordingPainter(), 0, 0, 1200, 900)
            app.release()
            app.draw(RecordingPainter(), 0, 0, 1200, 900)
        assert json.loads(copied[0])["channel_luts"]["0"] == [0, 1, 2, 3]
        assert not app.show_json
    finally:
        app.close()
