"""ndX opens the measurement container the burst search actually writes.

The container replaced the analysis *folder* on the writing side while the
reading side still only knew how to open a folder, so the end of the pipeline
was: pack ten `.spc` files into one `.pto`, search it, then be told
"No .bur files in 'bi4_bur' or 'bur'" by the viewer, about a file holding the
bursts.

Two things are pinned here, because both are ways the answer can be wrong
rather than absent:

* a container and the legacy folder written from the *same* run must produce
  the same bursts -- a reader that "works" but reads a different number is
  worse than one that refuses;
* re-running with a changed setting adds an object rather than replacing one,
  so a container can hold several tables all called ``bursts``. Concatenating
  them side by side lines up unrelated analyses of different lengths and pads
  with NaN, which pandas does silently.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.burst.burst_selection.api.models import (
    AnalysisRequest,
    AnalysisSettings,
    BurstDetectionSettings,
    DeltaMacroTimeFilterSettings,
    PhotonFilterSettings,
)
from chisurf.plugins.burst.burst_selection.api.selection import analyze_request

DATA = (
    Path(__file__).resolve().parents[2]
    / "chisurf"
    / "plugins"
    / "burst"
    / "burst_selection"
    / "tests"
    / "data"
    / "bh_spc132_sm_dna"
)
SPC = DATA / "m000.spc"

pytestmark = pytest.mark.skipif(not SPC.exists(), reason="no BH SPC test data")


def _settings(min_photons: int = 60) -> AnalysisSettings:
    s = AnalysisSettings()
    s.output_formats = ["pto", "bur"]
    s.photon_filter = PhotonFilterSettings(
        channels=[],
        filter_active=True,
        used_filter="count_rate",
        delta_macro_time_filter=DeltaMacroTimeFilterSettings(dT_min=0.0, dT_max=0.2),
    )
    s.burst_detection = BurstDetectionSettings(
        min_photons=min_photons, photon_window=10, time_window=1e-3
    )
    return s


@pytest.fixture
def analysed(tmp_path: Path) -> dict:
    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    result = analyze_request(
        AnalysisRequest(files=[str(source)], settings=_settings(), legacy_output=True)
    )
    return result.output_paths


def test_the_container_and_the_folder_hold_the_same_bursts(analysed: dict):
    from ndxplorer.io.reader import read_burst_analysis

    from_folder = read_burst_analysis(analysed["output_folder"])
    from_container = read_burst_analysis(analysed["pto"])

    assert from_container.size == from_folder.size
    assert from_container.size > 0


def test_the_macro_time_column_arrives_in_seconds_either_way(analysed: dict):
    """The folder reader renames ms to s; a container-loaded set must match, or
    every downstream axis silently depends on where the data came from.
    """
    from ndxplorer.io.reader import read_burst_analysis

    from_folder = read_burst_analysis(analysed["output_folder"])
    from_container = read_burst_analysis(analysed["pto"])

    column = "Mean Macro Time (s)"
    assert column in from_container.parameter_names
    assert column in from_folder.parameter_names


def test_a_second_search_does_not_get_merged_into_the_first(tmp_path: Path):
    """Two runs, two tables named `bursts`, and only the newer one is read."""
    from ndxplorer.io.reader import read_burst_analysis

    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    first = analyze_request(
        AnalysisRequest(files=[str(source)], settings=_settings(20), legacy_output=False)
    )
    container = first.output_paths["pto"]
    second = analyze_request(
        AnalysisRequest(files=[container], settings=_settings(200), legacy_output=False)
    )

    loaded = read_burst_analysis(container)
    assert loaded.size == second.metadata["n_bursts"]
    assert second.metadata["n_bursts"] < first.metadata["n_bursts"]
    assert not np.isnan(loaded.column_values("Number of Photons")).any()


def test_a_container_with_no_burst_table_says_so(tmp_path: Path):
    """Photons but no search is a different problem from a missing file."""
    from ndxplorer.io.reader import read_burst_analysis

    from chisurf.plugins.core.tttr_to_pto import api as pto_api

    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    container = pto_api.convert(source)

    with pytest.raises(FileNotFoundError, match="no burst table"):
        read_burst_analysis(container)
