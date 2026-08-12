"""Tests for the Burst Selection API I/O module (HDF5 and ZIP writers)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.datastore import (
    column_names,
    numeric_column,
    read_results_table,
    read_table,
    store_from_arrays,
    store_from_rows,
)
from chisurf.plugins.burst.burst_selection.api.io import (
    get_unique_folder_path,
    zip_output_folder,
)
from chisurf.plugins.burst.burst_selection.api.models import (
    AnalysisSettings,
    BurstDetectionSettings,
    BurstFilterMode,
    CountRateFilterSettings,
    DeltaMacroTimeFilterSettings,
    PhotonFilterSettings,
)
from chisurf.plugins.burst.burst_selection.api.selection import analyze_file

BH_SPC_FILE = (
    Path(__file__).resolve().parent
    / "data"
    / "bh_spc132_sm_dna"
    / "m000.spc"
)

DEFAULT_SETTINGS = AnalysisSettings(
    photon_filter=PhotonFilterSettings(
        channels=[0, 1, 8, 9],
        filter_active=True,
        used_filter=BurstFilterMode.BURST,
        count_rate_filter=CountRateFilterSettings(
            n_ph_max=60,
            time_window=0.001,
            invert=True,
        ),
        delta_macro_time_filter=DeltaMacroTimeFilterSettings(
            dT_min=0.0001,
            dT_max=0.15,
            dT_min_active=False,
            dT_max_active=True,
        ),
        invert_filter=True,
        max_gap=3,
        use_gap_fill=False,
    ),
    burst_detection=BurstDetectionSettings(
        min_photons=60,
        photon_window=5,
        time_window=0.001,
    ),
)


@pytest.fixture
def burst_table():
    """Run analysis on the BH SPC132 file and return a burst store.

    Returns
    -------
    tttrlib.DataStore
    """
    result = analyze_file(str(BH_SPC_FILE), settings=DEFAULT_SETTINGS)
    path_key = str(BH_SPC_FILE)
    return store_from_rows(result.dataframes[path_key])


# ---------------------------------------------------------------------------
# get_unique_folder_path
# ---------------------------------------------------------------------------

def test_get_unique_folder_path_returns_base_when_free(tmp_path: Path) -> None:
    """Return the base path when neither folder nor .zip exists."""
    base = tmp_path / "output"
    result = get_unique_folder_path(base)
    assert result == base


def test_get_unique_folder_path_avoids_zip_conflict(tmp_path: Path) -> None:
    """Append _N suffix when a sibling .zip exists."""
    base = tmp_path / "output"
    zipfile.ZipFile(tmp_path / "output.zip", "w").close()
    result = get_unique_folder_path(base)
    assert result == tmp_path / "output_0"


def test_get_unique_folder_path_avoids_folder_conflict(tmp_path: Path) -> None:
    """Append _N suffix when the folder itself exists."""
    base = tmp_path / "output"
    base.mkdir()
    result = get_unique_folder_path(base)
    assert result == tmp_path / "output_0"


def test_get_unique_folder_path_avoids_both_conflicts(tmp_path: Path) -> None:
    """Increment suffix when multiple conflicts exist."""
    base = tmp_path / "output"
    base.mkdir()
    zipfile.ZipFile(tmp_path / "output.zip", "w").close()
    (tmp_path / "output_0").mkdir()
    zipfile.ZipFile(tmp_path / "output_0.zip", "w").close()
    result = get_unique_folder_path(base)
    assert result == tmp_path / "output_1"


# ---------------------------------------------------------------------------
# zip_output_folder
# ---------------------------------------------------------------------------

def test_zip_output_folder_roundtrip(tmp_path: Path) -> None:
    """Zip a folder and verify extracted contents match originals."""
    src = tmp_path / "source"
    src.mkdir()
    (src / "bi4_bur").mkdir()
    (src / "bi4_bur" / "test.bur").write_text("photon\tcount\n1\t2\n")
    (src / "Info").mkdir()
    (src / "Info" / "params.json").write_text('{"key": "val"}')

    zip_path = tmp_path / "out.zip"
    result = zip_output_folder(src, zip_path)
    assert result == zip_path
    assert zip_path.exists()

    extract_dir = tmp_path / "extracted"
    extract_dir.mkdir()
    with zipfile.ZipFile(str(zip_path), "r") as zf:
        zf.extractall(str(extract_dir))

    extracted_files = sorted(
        str(p.relative_to(extract_dir)) for p in extract_dir.rglob("*") if p.is_file()
    )
    expected = sorted(["Info/params.json", "bi4_bur/test.bur"])
    assert extracted_files == expected
    assert (extract_dir / "bi4_bur" / "test.bur").read_text() == "photon\tcount\n1\t2\n"


def test_zip_output_folder_nonexistent(tmp_path: Path) -> None:
    """Raises FileNotFoundError for a nonexistent folder."""
    with pytest.raises(FileNotFoundError):
        zip_output_folder(tmp_path / "nonexistent", tmp_path / "out.zip")


def test_zip_output_folder_default_path(tmp_path: Path) -> None:
    """When no zip_path is given, use {output_folder}.zip."""
    src = tmp_path / "my_output"
    src.mkdir()
    (src / "file.txt").write_text("data")
    result = zip_output_folder(src)
    assert result == tmp_path / "my_output.zip"
    assert result.exists()
