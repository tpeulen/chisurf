"""Tests for the comprehensive Phacq Settings dock (grouped settings & JSON editor).
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel, DOCKS
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

SIZE = (1500, 950)


def test_settings_dock_presence_in_docks():
    dock_keys = [key for key, _title, _region in DOCKS]
    assert "settings" in dock_keys
    docks_dict = {key: (title, region) for key, title, region in DOCKS}
    title, region = docks_dict["settings"]
    assert title == "Settings"
    # The operator moved Settings into the central workspace; it stays Advanced-only
    # (its visibility is pinned by test_settings_dock_only_shown_in_advanced_mode).
    assert region == "main"


def test_settings_dock_only_shown_in_advanced_mode(tmp_path):
    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    # Default is simple mode
    assert not model.advanced
    app = RecordApp(model)
    ui = Driver(app, SIZE)
    try:
        ui.draw(2)
        # In simple mode, settings dock must NOT be visible or focusable
        assert not app.docks.windows["settings"].visible
        assert not app.docks.is_shown("settings")
        app.focus_dock("settings")
        ui.draw(2)
        assert not app.docks.windows["settings"].visible
        assert not app.docks.is_shown("settings")

        # Switch to Advanced mode -> settings dock becomes visible and focusable
        model.ui_mode = "advanced"
        model.ui_mode_changed()
        ui.draw(2)
        assert app.docks.windows["settings"].visible
        app.focus_dock("settings")
        ui.draw(2)
        assert app.docks.is_shown("settings")
        assert "Settings" in " ".join(ui.strings())

        # Backward compatibility alias 'phacq' focuses settings
        app.focus_dock("phacq")
        assert app.docks.is_shown("settings")

        # Switch back to Simple mode -> settings dock is hidden again
        model.ui_mode = "simple"
        model.ui_mode_changed()
        ui.draw(2)
        assert not app.docks.windows["settings"].visible
        assert not app.docks.is_shown("settings")
    finally:
        app.close()


def test_settings_dock_renders_grouped_settings_like_chisurf(tmp_path):
    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    model.ui_mode = "advanced"
    model.ui_mode_changed()
    app = RecordApp(model)
    try:
        app.focus_dock("settings")
        ui = Driver(app, SIZE)
        ui.draw(3)

        strings = " ".join(ui.strings())
        assert "Settings" in strings
        assert "Find a setting" in strings
        assert "device" in strings
        assert "sync" in strings
        assert "inputs" in strings
        assert "timing" in strings
        assert "scanner" in strings
        assert "Hardware Presets" in strings
        assert "NIM (-50mV)" in strings
        assert "TTL (+1.5V)" in strings
        assert "SPAD (-80mV)" in strings
        assert "Zero Delays" in strings
        assert "Edit source (JSON)" in strings
    finally:
        app.close()


def test_laser_devices_enumeration_and_selection(tmp_path):
    """The Settings dock's laser chooser: every laser system connected to this computer shows
    up, and picking one makes it the session's laser (idle-only)."""
    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    keys = [e["key"] for e in model.laser_devices()]
    assert "auto" in keys
    assert "simulated" in keys

    # Picking one connects it (the simulator needs no hardware) and marks its row in use
    ok, why = model.select_laser_device("simulated")
    assert ok, why
    assert model.laser_kind == "simulated"
    assert model.laser_connected
    row = next(e for e in model.laser_devices() if e["key"] == "simulated")
    assert row["connected"]

    # Switching while a recording runs is refused, idle-only
    model.session = SimpleNamespace(running=True)
    ok, why = model.select_laser_device("auto")
    assert not ok
    assert "running" in why.casefold()
    model.session = None
    model.disconnect_laser()
    assert not model.laser_connected


def test_settings_dock_renders_laser_chooser(tmp_path):
    """The Lasers category of the Settings dock lists the connected laser systems with a Use
    button each, and marks the one in use."""
    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    model.ui_mode = "advanced"
    model.ui_mode_changed()
    app = RecordApp(model)
    try:
        app.phacq_settings.category = "lasers"
        app.focus_dock("settings")
        ui = Driver(app, SIZE)
        ui.draw(3)

        strings = " ".join(ui.strings())
        assert "Connected Laser Systems" in strings
        assert "Detect automatically" in strings
        assert "Simulated laser" in strings
        assert "Use" in strings

        # The chooser acts: a Use button calls select_laser_device with its row's key.
        # The UI test observes the wiring only -- no hardware is opened from here (the
        # instrument is measuring), so the selection itself is patched out.
        picked: list[str] = []
        orig = RecordModel.select_laser_device
        RecordModel.select_laser_device = (
            lambda self, key: (picked.append(key), (True, "picked"))[1])
        try:
            ui.click_text("Use", last=True)
            ui.draw(2)
        finally:
            RecordModel.select_laser_device = orig
        rows = [e["key"] for e in model.laser_devices()]
        assert picked and picked[-1] in rows
        assert picked[-1] != "auto", "the clicked Use must belong to a concrete row"

        # A model-level selection is marked in use by the chooser
        model.select_laser_device("simulated")
        ui.draw(2)
        strings = " ".join(ui.strings())
        assert "in use" in strings
    finally:
        app.close()


def test_phacq_settings_lasers_roundtrip_through_json(tmp_path):
    """The laser chooser's scalars ride the grouped JSON document both ways."""
    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    model.ui_mode = "advanced"
    model.ui_mode_changed()
    app = RecordApp(model)
    try:
        panel = app.phacq_settings
        data = panel._build_grouped_data()
        assert data["lasers"]["kind"] == model.laser_kind
        assert data["lasers"]["address"] == (model.laser_address or "")

        # a real switch: away from the current kind, then apply
        model.disconnect_laser()
        model.laser_kind = "cmc_sim"
        data["lasers"]["kind"] = "simulated"
        data["lasers"]["address"] = ""
        panel._apply_grouped_data(data)
        assert model.laser_kind == "simulated"
        assert model.laser_connected
    finally:
        app.close()


def test_phacq_json_editor_mode_and_apply(tmp_path):
    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    model.ui_mode = "advanced"
    model.ui_mode_changed()
    app = RecordApp(model)
    try:
        panel = app.phacq_settings
        panel.source_mode = True
        app.focus_dock("phacq")
        ui = Driver(app, SIZE)
        ui.draw(3)

        strings = " ".join(ui.strings())
        assert "Apply to Hardware" in strings
        assert "Format JSON" in strings
        assert "Reset to Hardware" in strings

        # Edit JSON text directly
        custom_cfg = {
            "device": {"index": "Simulation", "mode": "T3"},
            "sync": {"divider": 8, "level_mv": -75, "edge": 0, "offset_ps": 150},
            "inputs": {
                "channel_0": {"enabled": True, "level_mv": -60, "edge": 0, "offset_ps": 200, "dead_time_ps": 850},
                "channel_1": {"enabled": False, "level_mv": -50, "edge": 0, "offset_ps": 0, "dead_time_ps": 800},
            },
            "timing": {"binning": 3, "offset_ns": 5},
            "scanner": {"raster_start_marker": 3, "raster_stop_marker": 4, "marker_holdoff_ns": 100},
        }
        panel._json_text = json.dumps(custom_cfg, indent=2)
        panel._apply_grouped_data(custom_cfg)

        # Verify values propagated to model.device_values
        assert model.device_values["sync_divider"] == 8
        assert model.device_values["sync_level_mv"] == -75
        assert model.device_values["sync_offset_ps"] == 150
        assert model.device_values["input_enable[0]"] is True
        assert model.device_values["input_level_mv[0]"] == -60
        assert model.device_values["input_dead_time_ps[0]"] == 850
        assert model.device_values["input_enable[1]"] is False
        assert model.device_values["binning"] == 3
        assert model.device_values["offset_ns"] == 5
        assert model.device_values["raster_start_marker"] == 3
        assert model.device_values["raster_stop_marker"] == 4
        assert model.device_values["marker_holdoff_ns"] == 100
    finally:
        app.close()


def test_phacq_json_validation_and_error_handling(tmp_path):
    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    app = RecordApp(model)
    try:
        panel = app.phacq_settings
        # Valid JSON
        panel._json_text = '{"sync": {"divider": 2}}'
        assert panel.validate() is True
        assert panel._json_error == ""

        # Invalid JSON
        panel._json_text = '{"sync": {broken'
        assert panel.validate() is False
        assert "Validation error" in panel._json_error or "JSON" in panel._json_error

        # Non-dict root
        panel._json_text = '["array", "root"]'
        assert panel.validate() is False
        assert panel._json_error != ""
    finally:
        app.close()


def test_phacq_hardware_presets_application(tmp_path):
    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    app = RecordApp(model)
    try:
        # 1. NIM Preset
        model.apply_device_preset("nim")
        assert model.device_values.get("sync_level_mv") == -50
        assert model.device_values.get("sync_edge") == 0
        assert model.device_values.get("input_level_mv[0]") == -50
        assert model.device_values.get("input_edge[0]") == 0

        # 2. TTL Preset
        model.apply_device_preset("ttl")
        assert model.device_values.get("sync_level_mv") == 1500
        assert model.device_values.get("sync_edge") == 1
        assert model.device_values.get("input_level_mv[0]") == 1500
        assert model.device_values.get("input_edge[0]") == 1

        # 3. SPAD Preset
        model.apply_device_preset("spad")
        assert model.device_values.get("sync_level_mv") == -50
        assert model.device_values.get("input_level_mv[0]") == -80
        assert model.device_values.get("input_dead_time_ps[0]") == 800

        # 4. Zero Delays Preset
        model.device_values["sync_offset_ps"] = 250
        model.device_values["input_offset_ps[0]"] = 1200
        model.apply_device_preset("zero_offsets")
        assert model.device_values.get("sync_offset_ps") == 0
        assert model.device_values.get("input_offset_ps[0]") == 0
    finally:
        app.close()


def test_phacq_sync_rate_and_channel_metrics(tmp_path):
    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    app = RecordApp(model)
    try:
        # Simulator sync rate
        rate_hz, rate_str, status = model.sync_rate_display()
        assert rate_hz > 0
        assert "MHz" in rate_str or "kHz" in rate_str
        assert status in ("ok", "warn")

        # Custom device rates
        model.device_rates_hz = [80.0e6, 250.0e3, 1.2e6, 0.0, 50.0e3]
        rate_hz, rate_str, status = model.sync_rate_display()
        assert rate_hz == 80.0e6
        assert "80.00 MHz" in rate_str
        assert status == "ok"

        # Channel info list
        ch_list = model.channel_info_list()
        assert len(ch_list) >= 4
        # Channel 0: 250 kHz -> not overloaded
        assert ch_list[0]["rate_hz"] == 250.0e3
        assert not ch_list[0]["overload"]
        # Channel 1: 1.2 MHz -> overloaded
        assert ch_list[1]["rate_hz"] == 1.2e6
        assert ch_list[1]["overload"]
        assert "1200.0 kHz" in ch_list[1]["rate_str"] or "1.2" in ch_list[1]["rate_str"]
    finally:
        app.close()


def test_settings_dock_left_groups_and_right_settings_navigation(tmp_path):
    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    model.ui_mode = "advanced"
    model.ui_mode_changed()
    app = RecordApp(model)
    try:
        app.focus_dock("settings")
        panel = app.settings_panel
        ui = Driver(app, SIZE)
        ui.draw(2)

        # 1. Left sidebar has categories/groups
        strings = " ".join(ui.strings())
        assert "Search groups" in strings or "Search groups..." in strings
        assert "TCSPC Hardware" in strings
        assert "Camera & Video" in strings
        assert "Realism & Sim" in strings or "Realism & Simulation" in strings
        assert "JSON Source Editor" in strings

        # 2. Select Camera group -> right side shows camera fields & actions
        panel.category = "camera"
        ui.draw(2)
        cam_strings = " ".join(ui.strings())
        assert "Discover" in cam_strings
        assert "Matrix Vision" in cam_strings
        assert "display_gain" in cam_strings or "camera" in cam_strings

        # 3. Select Realism group -> right side shows realism simulation fields
        panel.category = "realism"
        ui.draw(2)
        real_strings = " ".join(ui.strings())
        assert "donor_only" in real_strings
        assert "acceptor_only" in real_strings
        assert "bleaching" in real_strings

        # 4. Group search filter on the left sidebar
        panel.group_filter = "Camera"
        ui.draw(2)
        filtered_strings = " ".join(ui.strings())
        assert "Camera" in filtered_strings
    finally:
        app.close()

