"""Every downstream burst step reads the container, so nothing has to copy it out.

`read_burst_analysis` could only open a *folder*, so the burst workflow wrote a
`burst_analysis_handoff/` directory of `.bur` files purely to have one to hand
to the next step. That put the same bursts in a second place — and the second
place went stale the moment the selection was re-run, which is how BVA came to
report "4 bursts with Std > 0 on 8 total" from a handoff folder while the panel
above it showed hundreds.

Both readers are covered: the shared one in `chisurf.core.fio.fluorescence.burst`
and BVA's own (which 2CDE reuses).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.core.datastore import column_names, row_count
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
    / "chisurf" / "plugins" / "burst" / "burst_selection"
    / "tests" / "data" / "bh_spc132_sm_dna"
)
SPC = DATA / "m000.spc"

pytestmark = pytest.mark.skipif(not SPC.exists(), reason="no BH SPC test data")


def _settings() -> AnalysisSettings:
    s = AnalysisSettings()
    s.output_formats = ["pto"]
    s.photon_filter = PhotonFilterSettings(
        channels=[],
        filter_active=True,
        used_filter="count_rate",
        delta_macro_time_filter=DeltaMacroTimeFilterSettings(dT_min=0.0, dT_max=0.2),
    )
    s.burst_detection = BurstDetectionSettings(
        min_photons=60, photon_window=10, time_window=1e-3
    )
    return s


@pytest.fixture
def analysed(tmp_path: Path) -> tuple[Path, int]:
    """A container with a burst table in it, and the number of bursts."""
    from chisurf.plugins.core.tttr_to_pto import api as pto_api

    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    container = pto_api.convert(source)
    result = analyze_request(
        AnalysisRequest(
            files=[str(container)], settings=_settings(), legacy_output=True
        )
    )
    return container, int(result.metadata["n_bursts"])


def test_the_shared_reader_opens_a_container(analysed):
    container, n_bursts = analysed
    from chisurf.core.fio.fluorescence.burst import read_burst_analysis

    table, tttrs = read_burst_analysis(container, "SPC-130", pattern="bi4_bur")

    assert row_count(table) == n_bursts
    assert "Number of Photons" in column_names(table)
    # Keyed the way `First File` names the measurement, so a caller indexing
    # `tttrs[row["First File"]]` resolves without knowing where it came from.
    for name in {str(v) for v in np.asarray(table["First File"]).tolist()}:
        assert name in tttrs


def test_bvas_reader_opens_a_container(analysed):
    """BVA has its own reader, and 2CDE reuses it."""
    container, n_bursts = analysed
    from chisurf.plugins.burst.burst_bva.core.computation import read_burst_analysis

    table, tttrs = read_burst_analysis(container, "SPC-130", pattern="bi4_bur")

    assert row_count(table) == n_bursts
    assert tttrs


def test_bva_computes_over_the_container(analysed):
    """The end of the chain: the number that was 8.

    Not an assertion about BVA's physics — only that it sees the bursts the
    selection found rather than a stale handful from a folder beside them.
    """
    container, n_bursts = analysed
    from chisurf.plugins.burst.burst_bva.core.computation import (
        compute_bva,
        read_burst_analysis,
    )

    table, tttrs = read_burst_analysis(container, "SPC-130", pattern="bi4_bur")
    out = compute_bva(
        table, tttrs,
        donor_channels=[0, 8], donor_micro_time_ranges=[],
        acceptor_channels=[1, 9], acceptor_micro_time_ranges=[],
        minimum_window_length=0.5, number_of_photons_per_slice=5,
    )

    assert row_count(out) == n_bursts
    std = np.asarray(out["Proximity Ratio Std"], dtype=float)
    assert int(np.sum(std > 0)) > n_bursts // 2


def test_a_container_without_bursts_says_what_is_missing(tmp_path: Path):
    """Photons but no search is not the same as a missing file."""
    from chisurf.core.fio.fluorescence.burst import read_burst_analysis
    from chisurf.plugins.core.tttr_to_pto import api as pto_api

    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    container = pto_api.convert(source)

    with pytest.raises(FileNotFoundError, match="no burst table"):
        read_burst_analysis(container, "SPC-130", pattern="bi4_bur")
