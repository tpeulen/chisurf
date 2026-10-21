"""Regression test for proximity ratio computation with BigS detector setup.

BigS detector setup defines detectors named "Green" and "Red" (capitalized),
channels [0, 8] and [1, 9], with polarization-resolved detection and no windows.
Previously, proximity_ratio and make_ui_dataframe only looked for lowercase
"Number of Photons (red)" and "Number of Photons (green)", causing all bursts
to collapse to Proximity Ratio = 0.0 (a single vertical bar in the histogram).
"""

from __future__ import annotations

import os
import pathlib
import shutil
import tempfile
import time
from typing import Any

import numpy as np
import pandas as pd

from chisurf.core.datastore import column_names, numeric_column, store_from_rows
from chisurf.plugins.burst.burst_selection.api.features import proximity_ratio
from chisurf.plugins.burst.burst_selection.api.models import (
    AnalysisSettings,
    BurstDetectionSettings,
    PhotonFilterSettings,
)
from chisurf.plugins.burst.burst_selection.api.selection import analyze_file
from chisurf.plugins.burst.burst_selection.gui.adapter import (
    make_ui_dataframe,
    proximity_ratio_from_frame,
)
from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel

DATA_DIR = pathlib.Path(__file__).resolve().parent / "data" / "bh_spc132_sm_dna"
BH_SPC_FILE = DATA_DIR / "m000.spc"

BIGS_SETUP: dict[str, Any] = {
    "setup_name": "BigS",
    "detectors": {
        "Green": {
            "chs": [0, 8],
            "g_factor": 1.0,
            "l1": 0.0,
            "l2": 0.0,
            "micro_time_ranges": [[0, 4096]],
        },
        "Red": {
            "chs": [1, 9],
            "g_factor": 1.0,
            "l1": 0.0,
            "l2": 0.0,
            "micro_time_ranges": [[0, 4096]],
        },
    },
    "windows": {},
    "polarization_resolved": True,
}


def test_synthetic_bigs_table_computes_proximity_ratio() -> None:
    """Proximity ratio must be computed from capitalized Green/Red photon counts."""
    df = pd.DataFrame(
        {
            "First Photon": [0, 10, 0, 30],
            "Last Photon": [0, 19, 0, 39],
            "Duration (ms)": [0.0, 1.0, 0.0, 1.5],
            "Number of Photons": [0, 10, 0, 20],
            "Number of Photons (Red)": [0, 3, 0, 15],
            "Number of Photons (Green)": [0, 7, 0, 5],
        }
    )
    # Direct api calculation
    pr = proximity_ratio(df)
    assert pr is not None
    assert np.allclose(pr[1::2], [0.3, 0.75])

    # UI dataframe calculation
    ui_df = make_ui_dataframe(df)
    assert "Proximity Ratio" in column_names(ui_df)
    assert np.allclose(numeric_column(ui_df, "Proximity Ratio"), [0.3, 0.75])
    assert np.allclose(numeric_column(ui_df, "Number of Photons (red)"), [3.0, 15.0])
    assert np.allclose(numeric_column(ui_df, "Number of Photons (green)"), [7.0, 5.0])
    assert "Number of Photons (Red)" in column_names(ui_df)
    assert "Number of Photons (Green)" in column_names(ui_df)


def test_bigs_setup_burst_search_and_distribution() -> None:
    """Analyze real TTTR data with BigS and verify sane PR distribution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = pathlib.Path(tmpdir)
        spc = tmp / "m000.spc"
        shutil.copy(BH_SPC_FILE, spc)

        settings = AnalysisSettings()
        settings.photon_filter = PhotonFilterSettings(
            channels=[0, 1, 8, 9],
            filter_active=False,
        )
        settings.burst_detection = BurstDetectionSettings(
            min_photons=20,
            photon_window=10,
            time_window=1e-3,
        )

        res = analyze_file(
            spc,
            settings=settings,
            detectors=BIGS_SETUP["detectors"],
            windows=BIGS_SETUP["windows"],
        )

        rows = list(res.dataframes.values())[0]
        raw_df = store_from_rows(rows)

        pr = proximity_ratio(raw_df)
        assert pr is not None
        valid_pr = pr[np.isfinite(pr)]
        assert len(valid_pr) > 100

        # Distribution should be broad, not all zero or constant
        assert len(np.unique(valid_pr)) > 50
        assert 0.0 < np.mean(valid_pr) < 1.0
        assert np.std(valid_pr) > 0.05

        ui_df = make_ui_dataframe(raw_df)
        ui_pr = numeric_column(ui_df, "Proximity Ratio")
        valid_ui_pr = ui_pr[np.isfinite(ui_pr)]
        assert len(valid_ui_pr) > 100
        assert len(np.unique(valid_ui_pr)) > 50


def test_bigs_driver_end_to_end() -> None:
    """End-to-end verification through BurstSelectionNativeApp and Driver."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = pathlib.Path(tmpdir)
        old_settings = os.environ.get("CHISURF_SETTINGS_DIR")
        old_mmfdb = os.environ.get("MMFDB_SETTINGS_DIR")
        old_db = os.environ.get("MMFDB_DATABASE_PATH")
        old_qpa = os.environ.get("QT_QPA_PLATFORM")

        try:
            os.environ["CHISURF_SETTINGS_DIR"] = str(tmp / "settings")
            os.environ["MMFDB_SETTINGS_DIR"] = str(tmp / "mmfdb")
            os.environ["MMFDB_DATABASE_PATH"] = str(tmp / "db.sqlite")
            os.environ["QT_QPA_PLATFORM"] = "offscreen"
            (tmp / "settings").mkdir()
            (tmp / "mmfdb").mkdir()

            from chisurf.plugins.burst.burst_selection.gui.model import save_setup

            save_setup("BigS", BIGS_SETUP)

            spc = tmp / "m000.spc"
            shutil.copy(BH_SPC_FILE, spc)

            from chisurf.plugins.burst.burst_selection.gui.native import create_app
            from chisurf.plugins.emtk_test_input import Driver

            app = create_app(restore=False)
            app.apply_setup(BIGS_SETUP, "BigS")

            drv = Driver(app, (1200, 800))
            assert drv.drop(spc)
            drv.draw(2)

            drv.click_name("toolAction_run")

            end = time.monotonic() + 30.0
            drv.draw(1)
            while app.job.busy and time.monotonic() < end:
                time.sleep(0.05)
                drv.draw(1)
            assert not app.job.busy, "burst search job did not finish"
            drv.draw(2)

            assert app.model.n_bursts > 0

            # Histogram check: must have multiple non-zero bins
            hist = app.model.histogram()
            assert hist is not None
            centers, counts, width = hist
            nonzero_bins = int(np.count_nonzero(counts))
            assert nonzero_bins >= 20, f"Expected >=20 nonzero bins, got {nonzero_bins}"
            assert np.max(counts) < np.sum(counts), "All bursts in single bin!"

            # Scatter check: must have multiple distinct points
            sc = app.model.scatter()
            assert sc is not None
            x, y = sc
            assert len(np.unique(x)) > 20

            # Summary check: Mean photons for Green and Red detectors
            summary = {r["key"]: r["value"] for r in app.model.summary_rows()}
            assert "Mean photons (Green)" in summary
            assert "Mean photons (Red)" in summary
            assert float(summary["Mean photons (Green)"]) > 0
            assert float(summary["Mean photons (Red)"]) > 0

            app.close()
        finally:
            if old_settings is not None:
                os.environ["CHISURF_SETTINGS_DIR"] = old_settings
            else:
                os.environ.pop("CHISURF_SETTINGS_DIR", None)
            if old_mmfdb is not None:
                os.environ["MMFDB_SETTINGS_DIR"] = old_mmfdb
            else:
                os.environ.pop("MMFDB_SETTINGS_DIR", None)
            if old_db is not None:
                os.environ["MMFDB_DATABASE_PATH"] = old_db
            else:
                os.environ.pop("MMFDB_DATABASE_PATH", None)
            if old_qpa is not None:
                os.environ["QT_QPA_PLATFORM"] = old_qpa
            else:
                os.environ.pop("QT_QPA_PLATFORM", None)


if __name__ == "__main__":
    print("Running test_synthetic_bigs_table_computes_proximity_ratio ...")
    test_synthetic_bigs_table_computes_proximity_ratio()
    print("PASS")

    print("Running test_bigs_setup_burst_search_and_distribution ...")
    test_bigs_setup_burst_search_and_distribution()
    print("PASS")

    print("Running test_bigs_driver_end_to_end ...")
    test_bigs_driver_end_to_end()
    print("PASS")

    print("ALL BIGS REGRESSION TESTS PASSED!")
