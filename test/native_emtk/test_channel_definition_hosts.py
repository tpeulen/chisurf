"""Actual native factories own the shared reference-calibration surface and its lifetime."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
import shutil
import socket
import time
from pathlib import Path

import pytest
from emtk.app import ImApp
from emtk.testing import Driver

# Actual HEAD-backed factories exercise sixteen constructor sites and the three
# controller bindings; the imaging factory owns the shared editor mixin.
HOSTS = [
    ("imaging-mixin", "chisurf.plugins.microscopy.img_pixel_intensity.gui.app:make_app", "editor"),
    ("burst-fcs", "chisurf.plugins.burst.burst_fcs_correlator.gui.app:create_app", "setup"),
    ("accurate-fret-controller", "chisurf.plugins.burst.accurate_fret.gui.app:create_app", "controller.channel_definition"),
    ("burst-setup", "chisurf.plugins.burst.burst_analysis.gui.setup_selection_app:make_app", "page"),
    ("burst-selection", "chisurf.plugins.burst.burst_selection.gui.native:create_app", "editor"),
    ("background-controller", "chisurf.plugins.burst.burst_background.gui.app:create_app", "controller.channel_definition"),
    ("h2mm", "chisurf.plugins.burst.burst_h2mm.gui.native:create_app", "editor"),
    ("burst-mle", "chisurf.plugins.burst.burst_mle_analysis.gui.native:create_app", "editor"),
    ("fcs-filter", "chisurf.plugins.fcs.fcs_filter_calculator.gui.app:create_app", "setup"),
    ("setup-direct", "chisurf.plugins.core.setup_channel_definition.gui.app:make_app", "page"),
    ("intensity-trace", "chisurf.plugins.tttr.intensity_trace.gui.app:make_app", "editor"),
    ("image-browser", "chisurf.plugins.tttr.tttr_image_browser.gui.app:make_app", "editor"),
    ("trace-browser", "chisurf.plugins.tttr.trace_browser.gui.app:make_app", "editor"),
    ("count-rate-controller", "chisurf.plugins.tttr.tttr_count_rate_analysis.gui.controller:create_app", "tool.channel_editor"),
    ("microtime-histogram", "chisurf.plugins.tttr.microtime_histogram.gui.app:create_app", "editor"),
    ("audifier", "chisurf.plugins.tttr.audifier.gui.app:create_app", "editor"),
]
REPO = Path(__file__).resolve().parents[2]
SAMPLE = REPO / "test/data/tttr/BH/132/BH_SPC132.spc"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Keep settings/stores in scratch and reject even native ZMQ connection attempts."""
    for name, suffix in {"CHISURF_SETTINGS_DIR": "settings", "MMFDB_SETTINGS_DIR": "mmfdb",
                         "MMFDB_DATABASE_PATH": "mmfdb.sqlite", "MMFDB_OBJECT_STORE_ROOT": "objects",
                         "MMFDB_OBJECT_STORE": "objects", "XDG_CACHE_HOME": "cache"}.items():
        monkeypatch.setenv(name, str(tmp_path / suffix))
    monkeypatch.chdir(tmp_path)
    attempted = []

    def forbidden(*args, **kwargs):
        attempted.append(str(args))
        raise AssertionError("Native detector host attempted an external connection")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    import zmq

    monkeypatch.setattr(zmq.Socket, "connect", forbidden)
    monkeypatch.setattr(zmq.Socket, "bind", forbidden)
    from chisurf.core import settings, setup_channel_definition
    from chisurf.core.data_io import detector_setups
    from chisurf.core.fio.lut_context import clear_active_setup_lut

    monkeypatch.setattr(settings, "chisurf_settings_path", tmp_path / "settings")
    # Imported canonical paths must follow each test's scratch settings too.
    monkeypatch.setattr(detector_setups, "DETECTOR_SETUPS_FILE", tmp_path / "settings/detector_setups.json")
    monkeypatch.setattr(setup_channel_definition.CONFIG, "canonical_file", tmp_path / "settings/detector_setups.json")
    monkeypatch.setitem(settings.cs_settings, "mmfdb", {
        "mode": "embedded", "database_path": str(tmp_path / "mmfdb.sqlite"),
        "default_user_id": "host-validation-owner",
    })
    yield
    clear_active_setup_lut()
    assert not attempted, attempted


def _make(case):
    """Construct the real public factory and find its actual owned widget."""
    _, route, attribute = case
    module, name = route.split(":")
    app = getattr(importlib.import_module(module), name)()
    widget = app
    for part in attribute.split("."):
        widget = getattr(widget, part)
    return app, widget


def _cleanup(app, widget):
    """Close real owners; explicitly clean leaked children after a failing ownership assertion."""
    try:
        app.close()
    finally:
        widget.close()


@pytest.mark.parametrize("case", HOSTS, ids=[case[0] for case in HOSTS])
def test_every_actual_constructor_and_controller_binding_has_its_real_app(case):
    """A shared child must be attached to its real ImApp, including delayed controller bindings."""
    from chisurf.emtk.channel_definition import ChannelDefinitionWidget

    app, widget = _make(case)
    try:
        assert isinstance(app, ImApp), type(app)
        assert isinstance(widget, ChannelDefinitionWidget), type(widget)
        assert widget.host_app is app
    finally:
        _cleanup(app, widget)


REPRESENTATIVES = [next(case for case in HOSTS if case[0] == name)
                   for name in ("setup-direct", "background-controller", "imaging-mixin")]


def _show_editor(app, case):
    """Reveal the actual editor tab through its existing public docking controller."""
    if case[0] == "background-controller":
        app.bg_gui.docks.focus("channels")
    elif case[0] == "imaging-mixin":
        app.docks.focus("Detectors")


def _open_reference(app, widget, driver, tmp_path):
    """Drive a real detector action/file chooser and the compiled BH132 reference reader."""
    settings = widget.model.get_settings()
    settings.update(detectors={"reference-detector": {
        "chs": [8, 0, 3], "micro_time_ranges": [[0, 4095]], "g_factor": 1.25,
        "l1": 0.05, "l2": 0.02, "g_factor_channels": [850, 1850],
    }}, windows={"all": [0, 4095]}, tttr_reading={
        "file_type": "SPC-130", "macro_time_resolution": 25.0,
        "micro_time_resolution": 50.0, "micro_time_binning": 2,
    }, channel_luts={}, channel_shifts={}, apply_lut=False)
    widget.load_definition(settings)
    before = copy.deepcopy(widget.model.get_settings())
    preview = widget.model.preview
    driver.frame(3)
    source = tmp_path / "reference.spc"
    shutil.copy2(SAMPLE, source)
    cells = widget._detector_buttons.cells()
    target = next(box for _, row, key, box in cells if row == 0 and key == "calc")
    driver.click(target)
    assert widget.dialog is not None and widget.action == "reference_calibration"
    widget.dialog.directory = str(tmp_path)
    driver.frame(3)
    driver.click("reference.spc")
    driver.click("Open")
    deadline = time.monotonic() + 20
    while widget._reference_future is not None and time.monotonic() < deadline:
        time.sleep(0.005)
        driver.frame()
    driver.frame(3)
    assert widget._reference_future is None, widget.status
    assert widget.reference_prompt.open, widget.status
    assert widget.model.get_settings() == before and widget.model.preview is preview
    driver.click("Open calculator")
    driver.frame(3)
    child = widget.reference_app
    assert isinstance(child, ImApp)
    assert child.model.fast is not None and len(child.model.fast[0]) == 2048
    assert child.model.region == [425.0, 925.0]
    assert child.model.fp_dt_ns == pytest.approx(3.2958984375 * 2 * 0.001)
    assert widget.model.get_settings() == before
    return child, before


@pytest.mark.parametrize("case", REPRESENTATIVES, ids=[case[0] for case in REPRESENTATIVES])
def test_real_direct_controller_and_mixin_reference_child_input_and_parent_close(case, tmp_path, monkeypatch):
    """Real nested input reaches the calculator and closing its owner cancels it once."""
    app, widget = _make(case)
    try:
        _show_editor(app, case)
        driver = Driver(app, (1500, 1100))
        child, before = _open_reference(app, widget, driver, tmp_path)
        rect = widget.item_rects["reference.manual_l"]
        driver.click(rect)
        deadline = time.monotonic() + 10
        while child.job.running and time.monotonic() < deadline:
            time.sleep(0.005)
            driver.frame()
        assert child.model.manual_l and child.model.l_override == 0.0
        artifacts = os.environ.get("CHISURF_REFERENCE_HOST_ARTIFACTS")
        evidence = None
        if artifacts:
            output = Path(artifacts)
            output.mkdir(parents=True, exist_ok=True)
            driver.hover((0, 0))
            driver.frame(2)
            driver.screenshot(output / f"{case[0]}-reference-child.png")
            evidence = {
                "factory": case[1], "actual_app": f"{type(app).__module__}.{type(app).__name__}",
                "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "actual_host_identity": widget.host_app is app,
                "reference_file": str(tmp_path / "reference.spc"),
                "reference_bins": len(child.model.fast[0]), "tail": child.model.region,
                "dt_ns": child.model.fp_dt_ns, "g_factor": child.model.g_factor,
                "manual_l": child.model.manual_l, "working_definition_unchanged": widget.model.get_settings() == before,
                "child_rect": widget.reference_window.box,
                "reference_target_names": sorted(widget.item_rects),
            }
        closed = []
        prior = child.close

        def observed_close():
            closed.append(True)
            prior()

        monkeypatch.setattr(child, "close", observed_close)
        app.close()
        assert widget.reference_app is None and not widget.reference_window.open
        assert child._closed and closed == [True]
        assert widget.model.get_settings() == before
        app.close()
        assert closed == [True]
        if evidence is not None:
            evidence.update(parent_closed_child_once=True, repeated_close_kept_definition=True)
            (output / f"{case[0]}-reference-child.json").write_text(json.dumps(evidence, indent=2) + "\n")
    finally:
        _cleanup(app, widget)
