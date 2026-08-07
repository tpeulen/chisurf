import numpy as np

from chisurf.core.datastore import column_names, numeric_column, row_count, take_rows
import pandas as pd
from qtpy import QtWidgets


def test_burst_browser_widget(qapp, qtbot):
    from chisurf.plugins.burst.burst_browser import BurstBrowserWidget
    widget = BurstBrowserWidget()
    qtbot.addWidget(widget)
    assert isinstance(widget, QtWidgets.QWidget)
    assert widget.windowTitle() == "Burst Browser"


def _interleave(df_n: pd.DataFrame, cols) -> pd.DataFrame:
    """Return a 2n+1 interleaved table (header row + alternating zero/value rows)."""
    out = pd.DataFrame(np.zeros((2 * len(df_n) + 1, len(cols))), columns=cols)
    out.loc[1::2, cols] = df_n[cols].values
    return out


def test_read_bur_with_companions_merges_bv4_and_2c4(tmp_path):
    """The browser's loader joins BVA (bv4) and 2CDE (2c4) columns into the table."""
    from chisurf.core.fio.fluorescence import burst as burstio
    from chisurf.plugins.burst.burst_2cde.core.computation import (
        COLUMN_FRET_2CDE,
        write_2cde_analysis,
    )
    from chisurf.plugins.burst.burst_bva.core.computation import write_bv4_analysis

    n = 5
    src = pd.DataFrame({
        "First File": ["m000.spc"] * n,
        "First Photon": range(n),
        "Last Photon": range(1, n + 1),
        "Proximity Ratio Mean": np.linspace(0.1, 0.9, n),
        "Proximity Ratio Std": np.linspace(0.01, 0.05, n),
        COLUMN_FRET_2CDE: np.linspace(10.0, 40.0, n),
    })
    burd = tmp_path / "bi4_bur"
    burd.mkdir(parents=True)
    _interleave(src, ["First Photon", "Last Photon"]).to_csv(
        burd / "m000.bur", sep="\t", index=False
    )
    write_bv4_analysis(src, str(tmp_path))          # -> bv4/m000.bv4
    write_2cde_analysis(src, str(tmp_path), variant="fret")  # -> 2c4/m000.2c4

    merged = burstio.read_bur_with_companions(burd / "m000.bur")
    assert "Proximity Ratio Std" in column_names(merged)   # from BVA
    assert COLUMN_FRET_2CDE in column_names(merged)          # from 2CDE
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
