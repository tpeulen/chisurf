"""What a burst table says it was computed from, and what it used to say.

Two separate ways the recorded edges were wrong, both invisible from the result
itself and both fatal to the claim that a container reconstructs the path back
to its primary data:

* a measurement split over several vendor files is one container holding
  several photon streams, and the analysis reads all of them -- but the parent
  written was ``instrument_uid``, the **first** stream, so a ten-file
  measurement produced a burst table naming ``m000.spc`` alone;
* tags are appended to an object, not replaced, and re-running an analysis
  updates the table in place -- so the parent edge was written again on every
  run and a container analysed three times claimed the same source four times.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chisurf.core.fio.pto import Measurement
from chisurf.plugins.burst.burst_selection.api.models import (
    AnalysisRequest,
    AnalysisSettings,
    BurstDetectionSettings,
    DeltaMacroTimeFilterSettings,
    PhotonFilterSettings,
)
from chisurf.plugins.burst.burst_selection.api.selection import analyze_request

DATA = Path(__file__).resolve().parent / "data" / "bh_spc132_sm_dna"
SPC = DATA / "m000.spc"

pytestmark = pytest.mark.skipif(not SPC.exists(), reason="no BH SPC test data")


def _settings() -> AnalysisSettings:
    s = AnalysisSettings()
    s.output_formats = ["pto"]
    s.photon_filter = PhotonFilterSettings(
        channels=[],
        filter_active=False,
        delta_macro_time_filter=DeltaMacroTimeFilterSettings(dT_min=0.0, dT_max=0.2),
    )
    s.burst_detection = BurstDetectionSettings(
        min_photons=60, photon_window=10, time_window=1e-3
    )
    return s


def _analyze(path: Path) -> None:
    analyze_request(
        AnalysisRequest(files=[str(path)], settings=_settings(), legacy_output=False)
    )


def test_a_merged_measurement_records_every_stream_it_came_from(tmp_path: Path):
    """Three vendor files packed into one container are three parents, not one."""
    from chisurf.plugins.core.tttr_to_pto import api as pto_api

    sources = sorted(DATA.glob("m00*.spc"))[:3]
    assert len(sources) == 3, "need several vendor files to merge"
    for src in sources:
        (tmp_path / src.name).write_bytes(src.read_bytes())
    container = pto_api.convert(sorted(tmp_path.glob("*.spc")))

    _analyze(container)
    with Measurement.open(container) as m:
        parents = m.parents(m._resolve("bursts"))
        assert parents == m.instrument_uids
        assert len(parents) == len(sources)


def test_a_single_file_measurement_still_has_exactly_one_parent(tmp_path: Path):
    """The fix must not turn one source into a list of near-duplicates."""
    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    _analyze(source)
    container = source.with_suffix(".pto")
    with Measurement.open(container) as m:
        assert m.parents(m._resolve("bursts")) == [m.instrument_uid]


def test_rerunning_does_not_duplicate_the_parent_edges(tmp_path: Path):
    """Three runs, one edge -- recording it three times does not make it truer."""
    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    _analyze(source)
    container = source.with_suffix(".pto")
    _analyze(container)
    _analyze(container)
    with Measurement.open(container) as m:
        parents = m.parents(m._resolve("bursts"))
    assert len(parents) == len(set(parents))
