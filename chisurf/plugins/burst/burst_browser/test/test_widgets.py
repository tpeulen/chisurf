import numpy as np
import pandas as pd
import time

from chisurf.core.datastore import column_names, numeric_column, row_count, take_rows


def test_burst_browser_loads_gates_and_draws(tmp_path):
    from emtk.testing import RecordingPainter

    from chisurf.plugins.burst.burst_browser.gui.app import create_app

    app = create_app()
    try:
        assert app.table is None

        n = 20
        df = pd.DataFrame(
            {
                "First Photon": range(n),
                "Last Photon": range(1, n + 1),
                "Number of Photons": np.full(n, 100),
                "E": np.linspace(0.1, 0.9, n),
                "S": np.linspace(0.2, 0.8, n),
            }
        )
        burd = tmp_path / "data"
        burd.mkdir()
        _interleave(df, ["First Photon", "Last Photon", "Number of Photons", "E", "S"]).to_csv(
            burd / "test.bur", sep="\t", index=False
        )

        app.load_folder(burd)
        end = time.monotonic() + 30
        while (app.table is None or app.controller.running) and time.monotonic() < end:
            time.sleep(0.02)
            app.draw(RecordingPainter(), 0, 0, 900, 600)
        assert app.table is not None

        painter = RecordingPainter()
        app.draw(painter, 0, 0, 900, 600)
        assert painter.strings
        app.model.e_min = 0.3
        app.model.e_max = 0.7
        app.model.refresh()
        assert app.model.histogram() is not None
    finally:
        app.close()


def _interleave(df_n: pd.DataFrame, cols) -> pd.DataFrame:
    """Return a 2n+1 interleaved table (header row + alternating zero/value rows)."""
    out = pd.DataFrame(np.zeros((2 * len(df_n) + 1, len(cols))), columns=cols)
    out.loc[1::2, cols] = df_n[cols].values
    return out


def test_read_bur_with_companions_merges_bv4_and_2c4(tmp_path):
    """The browser's loader joins BVA (bv4) and 2CDE (2c4) columns into the table."""
    from chisurf.core.fio.fluorescence import burst as burstio
    from chisurf.core.fio.fluorescence.burst_companion import write_companion as legacy_writer
    from chisurf.plugins.burst.burst_2cde.core.computation import COLUMN_FRET_2CDE

    n = 5
    src = pd.DataFrame(
        {
            "First File": ["m000.spc"] * n,
            "First Photon": range(n),
            "Last Photon": range(1, n + 1),
            "Proximity Ratio Mean": np.linspace(0.1, 0.9, n),
            "Proximity Ratio Std": np.linspace(0.01, 0.05, n),
            COLUMN_FRET_2CDE: np.linspace(10.0, 40.0, n),
        }
    )
    burd = tmp_path / "bi4_bur"
    burd.mkdir(parents=True)
    _interleave(src, ["First Photon", "Last Photon"]).to_csv(
        burd / "m000.bur", sep="\t", index=False
    )
    # The browser still reads legacy folders; the companions it reads are what
    # `export_legacy` produces, so write them the way that does.
    legacy_writer(
        tmp_path,
        "bv4",
        "m000",
        ["Proximity Ratio Mean", "Proximity Ratio Std"],
        src[["Proximity Ratio Mean", "Proximity Ratio Std"]].to_numpy(),
    )
    legacy_writer(tmp_path, "2c4", "m000", [COLUMN_FRET_2CDE], src[[COLUMN_FRET_2CDE]].to_numpy())

    merged = burstio.read_bur_with_companions(burd / "m000.bur")
    assert "Proximity Ratio Std" in column_names(merged)  # from BVA
    assert COLUMN_FRET_2CDE in column_names(merged)  # from 2CDE
    # Values land on the burst (odd) rows of the interleaved table.
    odd = take_rows(merged, np.arange(1, row_count(merged), 2))
    assert np.allclose(numeric_column(odd, "Proximity Ratio Std"), src["Proximity Ratio Std"])
    assert np.allclose(numeric_column(odd, COLUMN_FRET_2CDE), src[COLUMN_FRET_2CDE])


def test_read_bur_with_companions_without_companions(tmp_path):
    """With no …4 companions the loader returns just the .bur columns."""
    from chisurf.core.fio.fluorescence import burst as burstio

    burd = tmp_path / "bi4_bur"
    burd.mkdir(parents=True)
    _interleave(
        pd.DataFrame({"First Photon": range(3), "Last Photon": range(1, 4)}),
        ["First Photon", "Last Photon"],
    ).to_csv(burd / "m000.bur", sep="\t", index=False)

    merged = burstio.read_bur_with_companions(burd / "m000.bur")
    assert "Proximity Ratio Std" not in column_names(merged)
    assert column_names(merged) == ["First Photon", "Last Photon"]
