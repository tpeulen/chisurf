"""The Record tool's Survey: a large area imaged tile by tile, its molecules picked and measured.

Known answers on the simulator: molecules planted in some tiles, none in others -- every planted
molecule is measured exactly once (also where tiles overlap), empty tiles are passed, Stop keeps
what was measured; the tiles spiral out of the start position and stay inside the piezo range.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
from chisurf.plugins.core.acq.live.scanner import ImagingSample, ScanSettings
from chisurf.plugins.core.acq.live.survey import keep_picks, piezo_range, plan_tiles
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

SIZE = (1500, 950)
SHOTS = Path(__file__).resolve().parents[5] / "test" / "native_emtk" / "screenshots"
#: molecules of a 2 x 2 tile survey: two in the first tile, two in the third, none elsewhere
PLANTED = [(12.0, 12.0, 0), (14.0, 14.5, 1), (19.0, 19.0, 0), (20.5, 17.5, 1)]


@pytest.fixture(autouse=True)
def _quiet_hmm():
    logging.getLogger("chisurf.core.math.hmm").setLevel(logging.ERROR)


def _model(tmp_path, planted, *, area=(10.0, 10.0, 12.8, 12.8)) -> RecordModel:
    model = RecordModel(output_dir=tmp_path, realtime=False)
    model.mode = "image"
    model.mode_changed()
    model.load_example()
    model.set_scan(ScanSettings(pixels_x=32, pixels_y=32, area_x_um=6.4, area_y_um=6.4,
                                x0_um=area[0], y0_um=area[1], dwell_ms=0.1, frames=2))
    model.imaging_sample = lambda: ImagingSample(positions=planted, bead_brightness=80.0,
                                                 cell=False)
    model.survey_area_kind = "custom"
    model.survey_x0_um, model.survey_y0_um, model.survey_w_um, model.survey_h_um = area
    model.point_time_s, model.img_bleach_s = 1.0, 0.3
    return model


def _measured(model) -> list[tuple[float, float]]:
    return [tuple(r["molecule"].point) for r in model.survey_rows]


def _matches(measured, planted, tol=0.15) -> bool:
    """Every planted molecule measured exactly once, nothing else."""
    if len(measured) != len(planted):
        return False
    return all(sum(np.hypot(x - px, y - py) < tol for x, y in measured) == 1
               for px, py, _ in planted)


def test_every_planted_molecule_is_measured_once_and_empty_tiles_are_passed(tmp_path):
    model = _model(tmp_path, PLANTED)
    assert model.survey_start()
    assert model.running and not model.enabled("start") and not model.enabled("survey_start")
    model.wait_survey(300)
    assert not model.survey_active and not model.running
    assert _matches(_measured(model), PLANTED), _measured(model)
    states = {(t.row, t.col): t.state for t in model.survey_tiles}
    assert states == {(0, 0): "done", (0, 1): "empty", (1, 1): "done", (1, 0): "empty"}
    assert "area done" in model.survey_text
    assert "stored with the first tile" in model.survey_saved
    table = model.survey_table()
    assert list(table["tile"]) == [r["tile"] for r in model.survey_rows]
    assert np.all(table["steps"] >= 1)
    # every tile image is a recording; one per molecule
    assert len(list(Path(tmp_path).rglob("*_p00*.ptu"))) == 4


def test_overlapping_tiles_measure_an_edge_molecule_once(tmp_path):
    """Tiles overlapping by 1.6 µm with a 2 px guard: a molecule in the overlap (and one cut by
    a tile's edge) is measured once, from the tile that holds it whole."""
    planted = [(15.6, 12.0, 0), (16.3, 13.5, 1), (12.0, 12.5, 0)]
    model = _model(tmp_path, planted, area=(10.0, 10.0, 11.2, 6.4))
    model.survey_overlap_um = 1.6
    model.survey_guard_px = 2
    assert len(model.survey_plan()) == 2
    assert model.survey_start()
    model.wait_survey(300)
    assert _matches(_measured(model), planted), _measured(model)


def test_stop_mid_survey_keeps_what_was_measured(tmp_path):
    planted = PLANTED + [(12.0, 19.0, 0), (19.0, 12.0, 1)]
    model = _model(tmp_path, planted)
    assert model.survey_start()
    end = time.monotonic() + 120
    while not model.survey_rows and time.monotonic() < end:
        model.poll(force=True)
        time.sleep(0.01)
    assert model.survey_rows
    assert model.stop()
    model.wait_survey(60)
    assert not model.survey_active and "stopped" in model.survey_text
    kept = len(model.survey_rows)
    assert 0 < kept < len(planted)
    assert "stored" in model.survey_saved
    assert any(t.state == "pending" for t in model.survey_tiles)


def test_tiles_spiral_out_of_the_start_and_stay_in_range():
    area = (0.0, 0.0, 64.0, 51.2)
    tiles = plan_tiles(area, (6.4, 6.4), start_um=(10.0, 40.0))
    cells = [(t.row, t.col) for t in tiles]
    assert len(cells) == len(set(cells)) == 10 * 8  # every tile once
    start = cells[0]
    assert start == (6, 1)  # the tile holding the start
    ring = [max(abs(r - start[0]), abs(c - start[1])) for r, c in cells]
    assert ring == sorted(ring)  # ring by ring, outward
    for t in tiles:
        assert 0 <= t.x0_um and t.x0_um + t.width_um <= 64.0 + 1e-9
    # serpentine on request; an area beyond the stage is clamped into it
    snake = plan_tiles((90.0, 90.0, 30.0, 30.0), (6.4, 6.4), order="serpentine")
    assert all(t.x0_um + t.width_um <= 100.0 + 1e-9 and t.y0_um + t.height_um <= 100.0 + 1e-9
               for t in snake)
    assert [(t.row, t.col) for t in snake][:4] == [(0, 0), (0, 1), (1, 1), (1, 0)]


def test_the_guard_band_and_measured_molecules_are_left_out():
    (tile,) = plan_tiles((10.0, 10.0, 6.4, 6.4), (6.4, 6.4))
    picks = [(12.0, 12.0), (10.1, 13.0), (14.0, 14.0), (14.05, 14.0)]
    keep, skipped = keep_picks(picks, tile, guard_um=0.4, taken=[(14.0, 14.0)], same_um=0.4)
    assert keep == [0]
    assert skipped == {"edge": 1, "range": 0, "measured": 2}


def test_the_whole_piezo_range_comes_from_the_scanner(tmp_path):
    phacq = pytest.importorskip("phacq")
    if "pi" not in set(phacq.DriverRegistry.instance().driver_names()):
        pytest.skip("this phacq has no pi driver")
    model = RecordModel(output_dir=tmp_path, realtime=False)
    assert model.connect_scanner({"driver": "pi", "address": "sim:"})
    assert piezo_range(model.scanner) == ((0.0, 100.0), (0.0, 100.0))
    assert model.survey_area() == (0.0, 0.0, 100.0, 100.0)
    model.close()


def test_the_survey_on_screen(tmp_path):
    """A survey of a 4 x 4 tile area mid-run and finished: the overview (tiles by state, the
    spiral path, the molecules), the current tile's image and the progress line."""
    from emtk.export import save_png

    model = RecordModel(output_dir=tmp_path, realtime=False)
    app = RecordApp(model)
    try:
        ui = Driver(app, SIZE)
        model.mode = "image"
        model.mode_changed()
        ui.draw(2)
        ui.click("load_example")
        model.set_scan(ScanSettings(pixels_x=48, pixels_y=48, area_x_um=6.4, area_y_um=6.4,
                                    x0_um=30.0, y0_um=30.0, dwell_ms=0.1, frames=2))
        model.img_beads = 4
        model.survey_area_kind = "custom"
        model.survey_x0_um = model.survey_y0_um = 20.0
        model.survey_w_um = model.survey_h_um = 25.6
        model.autopick_max, model.point_time_s = 2, 1.0
        model.realtime = True  # at measurement pace: a point's live trace to look at
        # the survey's fold open, the per-point ones folded: the overview in view
        app.form.folds.update({"Survey": True, "Auto-pick": False, "Measurement": False})
        ui.draw(2)
        ui.click("survey_start")
        assert model.survey_active
        end = time.monotonic() + 300
        ui.hover(5, SIZE[1] - 10)

        def measuring_a_later_tile():
            return (sum(t.state == "done" for t in model.survey_tiles) >= 3
                    and model.points_running and (model.snapshot or {}).get("point_trace"))

        while model.survey_active and not measuring_a_later_tile():
            assert time.monotonic() < end
            ui.draw(1)
        SHOTS.mkdir(parents=True, exist_ok=True)
        save_png(app, str(SHOTS / "record_survey_running.png"), size=SIZE)
        assert "Tile" in model.survey_text
        while model.survey_active:
            assert time.monotonic() < end
            ui.draw(1)
        ui.draw(3)
        save_png(app, str(SHOTS / "record_survey_done.png"), size=SIZE)
        assert all(t.state in ("done", "empty") for t in model.survey_tiles)
    finally:
        app.close()


def test_the_spiral_starts_where_the_last_image_was_not_where_the_stage_parked(tmp_path):
    """After a raster the scanner parks at the stage centre; the focus is the last image."""
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    from chisurf.plugins.core.acq.live.scanner import ScanSettings

    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)

    class Parked:
        def position(self):
            return (50.0, 50.0)

    model.scanner = Parked()
    model.image_scan = ScanSettings(x0_um=10.0, y0_um=20.0, area_x_um=6.4, area_y_um=6.4)
    assert model._start_position() == pytest.approx((13.2, 23.2))
    model.image_scan = None
    assert model._start_position() == (50.0, 50.0)          # no image yet: the stage
    model.survey_centre = "area"
    assert model._start_position() is None
