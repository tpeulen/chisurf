"""Fusing a burst run of a measurement container: the fused bursts become a run of the same
container, read back by the same reader every burst tool and ndX use.

In a project the container is the photon dataset's analysis container, so this is the path the
workspace takes; nothing is written beside the measurement.
"""

from __future__ import annotations

import pathlib
import shutil

import numpy as np
import pytest

from chisurf.core.datastore import column_names, numeric_column, row_count
from chisurf.plugins.burst.burst_fusion.api.models import FusionSettings
from chisurf.plugins.burst.burst_fusion.core.fusion import (
    analyze,
    fuse_folder,
    fused_run_name,
    is_run_source,
)

DATA = (
    pathlib.Path(__file__).resolve().parents[2]
    / "burst_selection"
    / "tests"
    / "data"
    / "bh_spc132_sm_dna"
)
ANALYSIS = "burstwise_All 0.1000#15"
RUN = "burstwise_All 0.1000#15"
DETECTORS = {
    "green": {"chs": [0, 8], "micro_time_ranges": [[0, 2048]]},
    "red": {"chs": [1, 9], "micro_time_ranges": [[0, 2048]]},
}
WINDOWS = {"prompt": [0, 2048], "delayed": [2048, 4095]}


@pytest.fixture
def run_address(tmp_path):
    """A burst run in an analysis container (photons linked), as a project session holds it."""
    if not DATA.is_dir():
        pytest.skip("burst-selection test data not available")
    from chisurf.core.fio.fluorescence.burst import read_bur_file
    from chisurf.core.fio.fluorescence.burst_container import deinterleave_bursts
    from chisurf.plugins.burst.burst_selection.api.io import write_container

    data = tmp_path / "data"
    data.mkdir()
    shutil.copy(DATA / "m000.spc", data / "m000.spc")
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    bursts = deinterleave_bursts(read_bur_file(DATA / ANALYSIS / "bi4_bur" / "m000.bur"))
    container = write_container(
        data / "m000.spc",
        bursts,
        parameters={"search": 1},
        out_dir=analysis,
        run=RUN,
        raw_data="sidecar",
    )
    return f"{container}/{RUN}"


def test_a_run_is_a_run_source(run_address, tmp_path):
    assert is_run_source(run_address)
    assert not is_run_source(tmp_path / "data")


def test_analyze_reads_the_run_and_remembers_it(run_address):
    analysis = analyze(run_address, FusionSettings(threshold=0.5))
    assert analysis.sources == {"m000": run_address}
    stats = analysis.statistics
    assert stats["n_bursts_before"] > stats["n_bursts_after"] > 0


def test_fusing_a_run_writes_a_run_of_the_same_container(run_address, tmp_path):
    from chisurf.core.fio.classify import container_entries
    from chisurf.core.fio.fluorescence.burst import _read_burst_analysis_from_container

    settings = FusionSettings(threshold=0.5)
    result = fuse_folder(run_address, settings, detectors=DETECTORS, windows=WINDOWS)
    container = pathlib.Path(run_address).parent
    fused = f"{container}/{fused_run_name(RUN, settings)}"
    assert result["runs"] == [fused]
    after = result["per_measurement"]["m000"]["bursts_after"]
    assert 0 < after < result["per_measurement"]["m000"]["bursts_before"]

    # The workspace lists the fused run beside the search it came from.
    runs = [a for kind, a in container_entries(container) if kind == "bursts"]
    assert runs == [run_address, fused]

    # Read as every burst tool reads a run: the fused bursts, with how each was assembled.
    table, _tttrs = _read_burst_analysis_from_container(pathlib.Path(fused))
    assert row_count(table) == after
    names = column_names(table)
    assert "Fused Bursts" in names and "Number of Photons" in names
    assert np.all(numeric_column(table, "Fused Bursts") >= 1)

    # The source run carries each burst's group, for colouring the original bursts.
    source, _ = _read_burst_analysis_from_container(pathlib.Path(run_address))
    assert "Fusion Group" in column_names(source)

    # Nothing beside the measurement.
    assert sorted(p.name for p in (tmp_path / "data").iterdir()) == ["m000.spc"]


def test_without_a_detector_setup_nothing_is_written(run_address):
    from chisurf.plugins.burst.burst_fusion.core.fusion import FusionError

    with pytest.raises(FusionError, match="detector"):
        fuse_folder(run_address, FusionSettings(threshold=0.5), windows=WINDOWS)
