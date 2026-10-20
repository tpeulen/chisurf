"""Time regions drawn per file on the Files step's count-rate trace: only photons inside them are correlated.

The region arithmetic, the two photon paths of the workflow (raw and photon-filtered), and real pointer drags on the
drawn trace. Data: two short simulated streams (:mod:`.streams`), so the photons in a window can be counted exactly.
"""

from __future__ import annotations

import time

import numpy as np
import pytest
from emtk.events import RIGHT_BUTTON

from chisurf.plugins.fcs.fcs_correlator.filter_model import FilterSettingsModel
from chisurf.plugins.fcs.fcs_correlator.regions import (
    TimeRegions,
    file_key,
    interval_mask,
    merge_intervals,
    times_s,
)
from chisurf.plugins.fcs.fcs_correlator.workflow import FcsWorkflow

from .streams import diffusion_spc
from .test_emtk_workflow import Hub, _hub


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "s"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "m"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "m.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path))


@pytest.fixture
def two_files(tmp_path):
    a = diffusion_spc(tmp_path, "a.spc", rate_hz=20.0, duration_s=2.0, seed=1)
    b = diffusion_spc(tmp_path, "b.spc", rate_hz=20.0, duration_s=2.0, seed=2)
    return a, b


def _read(path):
    return FcsWorkflow.read_tttr(str(path), "")


# ── the arithmetic ───────────────────────────────────────────────────────────


def test_merge_joins_overlaps_orders_and_drops_empty():
    assert merge_intervals([(3, 2), (0.5, 1), (0.9, 1.5), (4, 4)]) == [(0.5, 1.5), (2.0, 3.0)]


def test_interval_mask_is_start_inclusive_stop_exclusive():
    t = np.array([0.0, 0.5, 0.99, 1.0, 2.0, 2.5, 3.0])
    assert interval_mask(t, [(0.5, 1.0), (2.0, 3.0)]).tolist() == [
        False, True, True, False, True, True, False,
    ]
    assert interval_mask(t, []).all(), "no regions: the whole file"


def test_regions_add_remove_copy_and_round_trip(tmp_path):
    r = TimeRegions()
    r.add(tmp_path / "a.spc", 0.2, 0.4)
    r.add(tmp_path / "a.spc", 0.3, 0.6)
    assert r.get(tmp_path / "a.spc") == [(0.2, 0.6)]
    r.add(tmp_path / "a.spc", 1.0, 1.5)
    assert r.remove_at(tmp_path / "a.spc", 1.2) and not r.remove_at(tmp_path / "a.spc", 0.8)
    r.copy_to(tmp_path / "a.spc", [tmp_path / "b.spc"])
    assert r.get(tmp_path / "b.spc") == [(0.2, 0.6)]
    again = TimeRegions()
    again.restore_settings(r.export_settings())
    assert again.by_file == r.by_file
    r.clear(tmp_path / "b.spc")
    assert file_key(tmp_path / "b.spc") not in r.by_file


# ── the workflow ─────────────────────────────────────────────────────────────


def test_a_folder_stands_for_its_spc_files(two_files, tmp_path):
    """Guard: folder expansion once matched suffixes against tttrlib container names and dropped every .spc file."""
    wf = FcsWorkflow()
    wf.set_files([str(tmp_path)], use_filter=False, use_merger=False)
    assert wf.expanded_files() == [file_key(p) for p in two_files]


def test_raw_path_keeps_only_photons_inside_each_files_regions(two_files):
    a, b = two_files
    wf = FcsWorkflow()
    wf.set_files([str(a), str(b)], use_filter=False, use_merger=False)
    wf.regions.set(a, [(0.5, 1.0), (1.5, 1.75)])
    ta, tb = times_s(_read(a)), times_s(_read(b))
    inside = ((ta >= 0.5) & (ta < 1.0)) | ((ta >= 1.5) & (ta < 1.75))
    combined = wf.load_raw_combined(wf.expanded_files())
    assert len(combined) == int(inside.sum()) + len(tb), "b has no regions: used whole"
    first = times_s(combined)[: int(inside.sum())]
    np.testing.assert_allclose(first, ta[inside])


def test_filtered_path_cuts_after_invert_and_gap_fill(two_files):
    a, b = two_files
    wf = FcsWorkflow()
    wf.set_files([str(a), str(b)], use_filter=True, use_merger=False)
    wf.regions.set(a, [(0.25, 0.75)])
    model = FilterSettingsModel()
    model.filter_mode, model.invert = "burst", True
    model.use_gap_fill, model.max_gap = True, 3
    wf.load_files_into_filter(model)
    ta = times_s(model._tttr_objects[file_key(a)])
    keep = model.compute_selection(model._tttr_objects[file_key(a)], str(a))
    assert keep.any(), "the inverted burst filter keeps background photons in the region"
    assert ((ta[keep] >= 0.25) & (ta[keep] < 0.75)).all(), "neither invert nor gap filling leaves the region"
    # the step-3 view (first file) counts the same photons
    assert int(model.selected().sum()) == int(keep.sum())
    combined = wf.filtered_tttr(model)
    kb = model.compute_selection(model._tttr_objects[file_key(b)], str(b))
    assert len(combined) == int(keep.sum()) + int(kb.sum())


# ── drawing on the trace (real pointer input) ────────────────────────────────


def _files_with_trace(hub: Hub, paths):
    hub.nav("files")
    files = hub.child
    files.add_paths(paths)
    end = time.monotonic() + 30
    while any(files.trace(f) is None for f in files.region_files()):
        assert time.monotonic() < end, "traces were not read"
        time.sleep(0.02)
        hub.draw(1)
    hub.draw(2)
    return files


def _plot_x(hub: Hub, frac):
    x, y, w, h = hub.rect("region_plot_area")
    return x + frac * w, y + 0.5 * h


def test_dragging_on_the_trace_draws_a_region_that_reaches_the_correlator(two_files):
    a, b = two_files
    hub = _hub()
    files = _files_with_trace(hub, [a, b])
    assert files.trace_file == file_key(a)
    hub.click("draw_regions")
    assert files.draw_mode
    x0, y = _plot_x(hub, 0.2)
    x1, _ = _plot_x(hub, 0.6)
    hub.app.pointer_move(x0, y)
    hub.draw(1)
    hub.app.press(x0, y)
    hub.draw(1)
    for k in range(1, 6):
        hub.app.drag(x0 + (x1 - x0) * k / 5, y)
        hub.draw(1)
    hub.app.release()
    hub.draw(2)
    regions = files.regions.get(a)
    assert len(regions) == 1, regions
    start, stop = regions[0]
    lo, hi = hub.child._view[:2]
    np.testing.assert_allclose([start, stop], [lo + 0.2 * (hi - lo), lo + 0.6 * (hi - lo)], atol=0.02)
    row = next(r for r in files.file_rows() if r["key"] == file_key(a))
    assert row["regions"] == 1, "the file table counts a file's regions"
    # the correlator gets only those photons of a (and all of b)
    hub.nav("correlator")
    ta, tb = times_s(_read(a)), times_s(_read(b))
    n_in = int(((ta >= start) & (ta < stop)).sum())
    assert len(hub.app.correlator_model._tttr) == n_in + len(tb)
    # right-click inside the region removes it
    hub.nav("files")
    xm, _ = _plot_x(hub, 0.4)
    hub.app.pointer_move(xm, y)
    hub.draw(1)
    hub.app.pointer_press(xm, y, RIGHT_BUTTON)
    hub.draw(1)
    hub.app.pointer_release(xm, y, RIGHT_BUTTON)
    hub.draw(2)
    assert files.regions.get(a) == []


def test_file_picker_lists_every_file_and_to_all_copies(two_files, tmp_path):
    a, b = two_files
    hub = _hub()
    files = _files_with_trace(hub, [tmp_path])  # a folder: its files are listed one by one
    assert files.region_files() == [file_key(a), file_key(b)]
    files.add_region(0.1, 0.9)
    hub.click("copy_regions")
    assert files.regions.get(b) == [(0.1, 0.9)]
    files.select_trace_file(file_key(b))
    hub.click("clear_regions")
    assert files.regions.get(b) == [] and files.regions.get(a) == [(0.1, 0.9)]
    state = files.export_settings()
    files.regions.clear()
    files.restore_settings(state)
    assert files.regions.get(a) == [(0.1, 0.9)]


def test_clicking_a_row_draws_that_files_trace_one_file_at_a_time(two_files, tmp_path):
    from emtk.events import SHIFT_MODIFIER

    a, b = two_files
    hub = _hub()
    files = _files_with_trace(hub, [tmp_path])  # one folder row, its two files as children
    control = files._table.control
    assert files.trace_file == file_key(a)
    hub.press_text("b.spc")
    assert files.trace_file == file_key(b) and control.selected_indices() == [2]
    x, y, w, h = hub.text_rect("a.spc")
    hub.app.pointer_move(x + w / 2, y + h / 2)
    hub.draw(1)
    hub.app.pointer_press(x + w / 2, y + h / 2, 1, SHIFT_MODIFIER)
    hub.draw(1)
    hub.app.release()
    hub.draw(2)
    assert control.selected_indices() == [1], "a shift-click selects one file, not a range"
    files.add_region(0.1, 0.5)
    files.add_region(1.0, 1.5)
    rows = {r["name"]: r["regions"] for r in files.file_rows()}
    assert rows["a.spc"] == 2 and rows["b.spc"] == 0 and rows[tmp_path.name + "/"] == 2
    hub.draw(2)
    assert hub.shown("2"), "the Regions column shows the count"
