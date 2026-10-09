"""Native Creator excitation candidates are computed, editable and export-neutral."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import numpy as np
import pytest
import tttrlib

from chisurf.plugins.emtk_test_input import CTRL, Driver
from chisurf.plugins.tttr.ptu_alex_creator import core
from chisurf.plugins.tttr.ptu_alex_creator.gui.app import AlexApp

SAMPLE = Path(__file__).resolve().parents[1] / "data/clsm/Leica_SP5.ptu"


def planted_file(path, size=3):
    """Write a real TTTR container with independent planted macrotime excitation phases."""
    rng = np.random.default_rng(62)
    boundaries = np.linspace(0, 8000, size + 1).astype(int)
    times, routes = [], []
    for index in range(size):
        phase = rng.integers(boundaries[index] + 80, boundaries[index + 1] - 80, 30000)
        times.append(rng.integers(1, 10000, phase.size) * 8000 + phase)
        probabilities = np.full(size, 0.1 / (size - 1))
        probabilities[index] = 0.9
        routes.append(rng.choice(size, phase.size, p=probabilities))
    macro, rc = np.concatenate(times), np.concatenate(routes)
    order = np.argsort(macro)
    source = tttrlib.TTTR(str(SAMPLE))[:0]
    source.header.set_tag("User_RegionMarker", "preserve source", 1073872895)
    source.append_events(
        macro[order].astype(np.uint64),
        np.full(macro.size, 23, dtype=np.uint16),
        rc[order].astype(np.int8),
        np.zeros(macro.size, dtype=np.int8),
        False,
        0,
    )
    source.write(str(path))
    return path


def settle(driver):
    """Drive actual worker publication until no detection or preview remains pending."""
    until = time.monotonic() + 30
    while driver.app.running and time.monotonic() < until:
        time.sleep(0.01)
        driver.draw(1)
    assert not driver.app.running
    return driver.draw(3)


@pytest.fixture
def ui(tmp_path, monkeypatch):
    """Keep all preferences and metadata under a temporary root."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))
    app = AlexApp(tmp_path / "state.json")
    driver = Driver(app, size=(1100, 720))
    driver.draw(2)
    yield driver
    app.close()


@pytest.mark.parametrize("size", [2, 3, 4])
def test_loading_detects_every_macrotime_phase_without_touching_source(ui, tmp_path, size):
    """Actual file loading resolves all colors from folded macros, despite constant raw microtimes."""
    path = planted_file(tmp_path / "planted.ptu", size)
    original = path.read_bytes()
    assert ui.app.load(str(path))
    settle(ui)
    assert len(ui.app.model.regions) == size
    assert ui.app.model.region_error == ""
    source = core.load(str(path))
    expected = core.apply_alex(core.load(str(path)), 8000, 0)
    detected = core.auto_excitation_regions(
        expected.micro_times, expected.routing_channels, alex_period=8000
    )
    assert [(row["start"], row["stop"], row["ranges"]) for row in ui.app.model.regions] == [
        (row["start"], row["stop"], row["ranges"]) for row in detected["regions"]
    ]
    np.testing.assert_array_equal(
        ui.app.histogram, np.bincount(expected.micro_times, minlength=8000)
    )
    for name in ("macro_times", "micro_times", "routing_channels", "event_types"):
        np.testing.assert_array_equal(getattr(ui.app.model._tttr, name), getattr(source, name))
    assert ui.app.model._tttr.header.json == source.header.json
    assert path.read_bytes() == original
    assert {"region_rows", "redetect_regions", "detector_groups"} <= ui.app.item_rects.keys()


def test_table_edit_wrap_and_redetection_use_actual_controls(ui, tmp_path):
    """Native cell editing changes safe plot ranges; the Re-detect button restores measured candidates."""
    assert ui.app.load(str(planted_file(tmp_path / "planted.ptu")))
    settle(ui)
    before = [dict(region) for region in ui.app.model.regions]
    binding = ui.app.form.tables["region_rows"]
    table = binding.control
    assert table.column_editable("start") and table.column_editable("confirmed")
    ui.click_text(f"{before[0]['start']:.1f}", clicks=2)
    ui.app.key(0x41, "a", CTRL)
    ui.draw(1)
    ui.type("7800")
    ui.enter()
    region = ui.app.model.regions[0]
    assert region["wraps"] and len(region["ranges"]) == 2
    assert region["ranges"][0] == [7800.0, 8000.0]
    x, y, _, _ = table._body_box
    ui.click((x + sum(table._widths[:-1]), y, table._widths[-1], table._row_h))
    assert region["confirmed"]
    # Use the actual numeric editor again to exercise validation and rollback.
    ui.click_text("7800.0", clicks=2)
    ui.app.key(0x41, "a", CTRL)
    ui.draw(1)
    ui.type("-2")
    ui.enter()
    assert region["start"] == 7800.0
    ui.click_name("redetect_regions")
    settle(ui)
    assert [r["start"] for r in ui.app.model.regions] == [r["start"] for r in before]
    assert not any(r["confirmed"] for r in ui.app.model.regions)


def test_manual_period_shift_preview_and_all_exports_stay_exact(ui, tmp_path):
    """Candidates never filter exported photons or alter the existing conversion paths."""
    path = planted_file(tmp_path / "planted.ptu")
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    assert ui.app.load(str(path))
    settle(ui)
    ui.app.model.alex_period, ui.app.model.period_shift = 4000, 23
    ui.draw(2)
    settle(ui)
    expected = core.apply_alex(core.load(str(path)), 4000, 23)
    np.testing.assert_array_equal(
        ui.app.histogram, np.bincount(expected.micro_times, minlength=4000)
    )
    for mode in ("single", "convert", "merge"):
        target = tmp_path / (mode + ".ptu")
        reference = tmp_path / (mode + "-reference.ptu")
        if mode == "single":
            core.convert_file(str(path), str(reference), 4000, 23)
            assert ui.app.save(target)
        else:
            ui.app.model.batch_files = [str(path)]
            ui.app.model.batch_output_folder = str(tmp_path / mode)
            ui.app.model.batch_mode = mode
            if mode == "merge":
                core.merge_files([str(path)], str(reference), 4000, 23)
            else:
                core.convert_file(str(path), str(reference), 4000, 23)
            assert ui.app.run_batch()
        settle(ui)
        actual, wanted = core.load(ui.app.outputs[0]), core.load(str(reference))
        for name in ("macro_times", "micro_times", "routing_channels", "event_types"):
            np.testing.assert_array_equal(getattr(actual, name), getattr(wanted, name))
        assert actual.header.json == wanted.header.json
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original


def test_bad_groups_and_detection_failures_leave_preview_and_conversion_available(ui, tmp_path):
    """An invalid detection configuration cannot make an otherwise readable file unloadable."""
    ui.app.detector_groups = "0;1"
    assert ui.app.load(str(planted_file(tmp_path / "planted.ptu")))
    settle(ui)
    assert ui.app.model.has_data and len(ui.app.histogram) == 8000
    assert ui.app.model.region_error and not ui.app.model.regions
    assert ui.app.enabled("choose_save")
    ui.app.detector_groups = "invalid syntax"
    ui.app.alex_period, ui.app.period_shift = 4000, 23
    ui.draw(2)
    settle(ui)
    expected = core.alex_histogram(ui.app.input_file, 4000, 23)
    np.testing.assert_array_equal(ui.app.histogram, expected)
    assert ui.app.model.region_error and not ui.app.model.regions


def test_detector_group_field_edit_recomputes_all_phases(ui, tmp_path):
    """A real field edit is committed to the worker and physical detector group result."""
    assert ui.app.load(str(planted_file(tmp_path / "planted.ptu")))
    settle(ui)
    ui.type_into_name("detector_groups", "0;1;2")
    settle(ui)
    assert ui.app.model.region_detection["detector_channels"] == [[0], [1], [2]]
    assert len(ui.app.model.regions) == 3


def test_equivalent_circular_boundaries_are_rejected_atomically(ui):
    """The table cannot replace a valid region by an empty phase-zero selection."""
    record = {
        "start": 4000.0,
        "stop": 0.0,
        "_valid_start": 4000.0,
        "_valid_stop": 0.0,
        "wraps": True,
        "ranges": [[4000.0, 8000.0]],
        "confirmed": True,
    }
    before = dict(record)
    # TableBinding writes the mutable record before calling the model hook.
    record["start"] = 8000.0
    with pytest.raises(ValueError, match="nonempty"):
        ui.app.model.edit_region(record, "start", 8000.0)
    assert record == before


def test_boundary_edits_never_emit_empty_ranges(ui):
    """An end at zero is reachable as one increasing range, without an empty second range."""
    record = {
        "start": 4000.0,
        "stop": 2000.0,
        "_valid_start": 4000.0,
        "_valid_stop": 2000.0,
        "ranges": [[4000.0, 8000.0], [0.0, 2000.0]],
    }
    ui.app.model.edit_region(record, "stop", 0.0)
    assert record["ranges"] == [[4000.0, 8000.0]]
    ui.app.model.edit_region(record, "stop", 8000.0)
    assert record["ranges"] == [[4000.0, 8000.0]]


def test_stale_saved_period_warns_and_preserves_other_settings(ui):
    """An unsupported stored period is visibly reset, never silently clipped."""
    ui.app.set_state(
        {
            "settings": {
                "alex_period": 1000000,
                "period_shift": -37,
                "batch_output_folder": "retained",
            }
        }
    )
    assert ui.app.alex_period == 8000
    assert ui.app.period_shift == -37
    assert ui.app.model.batch_output_folder == "retained"
    assert ui.app.message_is_error and "Saved period was invalid" in ui.app.message


def test_real_calibration_keeps_transition_candidates_and_warnings(ui):
    """Real continuously occupied data reports uncertain emission phases explicitly."""
    from chisurf.plugins.burst.alex_suite.tests.test_alternation import REAL_FILE

    if not REAL_FILE.is_file():
        pytest.skip("real calibration measurement unavailable")
    assert ui.app.load(str(REAL_FILE))
    painter = settle(ui)
    assert len(ui.app.model.regions) >= 2
    assert ui.app.model.region_warnings
    assert any(r["ambiguous"] for r in ui.app.model.regions)
    assert any("Review transition" in row[5] for row in painter.texts)
