"""The Bursts table prints photon indices in full.

Every float cell went through ``f"{value:.4g}"``, so the burst of m000.spc that starts at photon 12 503 was listed as
``1.25e+04`` -- an index nobody can find in the photon stream again (guide 33 reads these ranges against
``burst_search``). Whole numbers are printed whole; fractional values keep four significant digits.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np

DATA = Path(__file__).parent / "data" / "bh_spc132_sm_dna"
SETUP = {
    "detectors": {
        "G|G": {"chs": [0, 8], "micro_time_ranges": []},
        "R|G": {"chs": [1, 9], "micro_time_ranges": []},
    },
    "windows": {},
    "tttr_reading": {"file_type": "SPC-130"},
}


def feed(window, *paths) -> bool:
    """Hand photon files over as the workspace does (Input section / Open in… / a drag)."""
    from chisurf.plugins.burst.burst_selection.gui.native import receive_photons

    try:
        receive_photons(window, {"files": [str(p) for p in paths], "datasets": []})
    except ValueError:
        return False
    return True


def test_cell_text_keeps_whole_numbers_whole():
    from chisurf.plugins.burst.burst_selection.gui.model import _cell_text

    assert _cell_text(12503.0) == "12503"
    assert _cell_text(2.9744) == "2.974"
    assert _cell_text(12270.5) == "12270.5"
    assert _cell_text(float("nan")) == "nan"
    assert _cell_text("m000.spc") == "m000.spc"


def test_the_bursts_table_lists_photon_indices_in_full(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    (tmp_path / "settings").mkdir()
    (tmp_path / "mmfdb").mkdir()
    shutil.copy(DATA / "m000.spc", tmp_path / "m000.spc")
    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel, save_setup

    save_setup("sm dna", SETUP)
    model = BurstSelectionModel()
    assert model.select_setup("sm dna")
    model.add_paths([tmp_path / "m000.spc"])
    model.run()
    rows = model.burst_rows()
    assert len(rows) == 71
    for row in rows:
        for key in ("First Photon", "Last Photon", "Number of Photons"):
            assert "e" not in row[key] and "." not in row[key], (key, row[key])
    firsts = np.array([int(r["First Photon"]) for r in rows])
    assert firsts[4] > 10_000 and np.all(np.diff(firsts) > 0)


def test_the_histogram_is_of_the_bursts_in_the_visible_window(tmp_path, monkeypatch):
    """The histogram (which replaced the *Burst duration* tab: Duration is one of its features)
    shows the bursts of the window the count-rate trace shows, and says so with their number."""
    from chisurf.plugins.burst.burst_selection.gui import diagnostics as diag
    from chisurf.plugins.emtk_test_input import Driver

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    (tmp_path / "settings").mkdir()
    (tmp_path / "mmfdb").mkdir()
    shutil.copy(DATA / "m000.spc", tmp_path / "m000.spc")
    from chisurf.plugins.burst.burst_selection.gui.native import create_app

    app = create_app(restore=False)
    try:
        app.apply_setup(SETUP, "sm dna")
        drv = Driver(app, (1400, 860))
        assert feed(drv.app, tmp_path / "m000.spc")
        app.model.run()
        app.model.load_diagnostics()
        app.model.hist_feature = "Duration (ms)"
        app.docks.focus("histogram")
        strings = drv.draw(2).strings
        assert "Burst duration" not in strings  # no tab of its own
        window = diag.rows_in_window(
            app.model.display_frame, app.model.window_start_s, app.model.window_length_s, "m000.spc"
        )
        n = diag.histogram_data_from_frame(window, "Duration (ms)").size
        everything = diag.histogram_data_from_frame(app.model.display_frame, "Duration (ms)").size
        assert 0 < n < everything
        assert f"Duration (ms): {n} bursts in the visible window" in strings, [
            x for x in strings if "bursts" in x or "Histogram" in x
        ]
    finally:
        app.close()


def test_a_fitted_mixture_keeps_its_legend_off_the_histogram(tmp_path, monkeypatch):
    """Guide 29's figure at 1400 x 860: the GMM table leaves the histogram ~80 px tall, and the legend inside the plot
    covered the donor-only peak. The legend now sits beside the plot: every component is listed and none lies over the
    plotted area."""
    from chisurf.plugins.emtk_test_input import Driver

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    (tmp_path / "settings").mkdir()
    (tmp_path / "mmfdb").mkdir()
    paths = []
    for name in ("m000.spc", "m001.spc", "m002.spc"):
        shutil.copy(DATA / name, tmp_path / name)
        paths.append(tmp_path / name)
    from chisurf.plugins.burst.burst_selection.gui.native import create_app

    app = create_app(restore=False)
    try:
        app.apply_setup(SETUP, "sm dna")
        size = (1400, 860)
        drv = Driver(app, size)
        assert feed(drv.app, *paths)
        app.model.run()
        app.model.gmm_components = 3
        app.model.fit_gmm()
        painter = drv.draw(3)
        labels = {t[5]: t[:4] for t in painter.texts}
        for entry in ("Bursts", "GMM fit", "Gaussian 1", "Gaussian 2", "Gaussian 3"):
            assert entry in labels, f"legend entry {entry!r} is not drawn"
        ticks = [t[0] + t[2] for t in painter.texts if t[5] in ("0.8", "0.9", "1")]
        assert ticks, "the histogram's x ticks are not drawn"
        assert labels["Gaussian 1"][0] > max(ticks), "the legend lies over the histogram"
    finally:
        app.close()


def test_a_feature_the_detectors_do_not_have_falls_back_to_duration(tmp_path, monkeypatch):
    """Proximity Ratio needs a green and a red detector; a setup proposed from a file names them by
    channel. The histogram showed nothing; it now shows Duration and says why."""
    from chisurf.plugins.emtk_test_input import Driver

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    (tmp_path / "settings").mkdir()
    (tmp_path / "mmfdb").mkdir()
    shutil.copy(DATA / "m000.spc", tmp_path / "m000.spc")
    from chisurf.plugins.burst.burst_selection.gui.native import FALLBACK_FEATURE, create_app

    by_channel = dict(SETUP)
    by_channel["detectors"] = {f"ch{c}": {"chs": [c]} for c in (0, 1, 8, 9)}
    app = create_app(restore=False)
    try:
        app.apply_setup(by_channel, "by channel")
        drv = Driver(app, (1400, 860))
        assert feed(drv.app, tmp_path / "m000.spc")
        app.model.run()
        app.model.load_diagnostics()
        app.model.hist_feature = "Proximity Ratio"
        app.docks.focus("histogram")
        strings = drv.draw(2).strings
        assert app.model.hist_feature == FALLBACK_FEATURE
        assert any("is not defined for these detectors" in x for x in strings), strings
        assert any(x.startswith(f"{FALLBACK_FEATURE}: ") for x in strings), strings
    finally:
        app.close()
