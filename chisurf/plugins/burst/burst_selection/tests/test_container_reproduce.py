"""A burst search stored in a container can be re-run from the container alone.

The container holds the photons, the burst table and the settings that made it,
and the table's lineage reaches the photon stream. Re-running the search with the
*stored* settings must give the stored bursts back -- interval for interval --
and the check must actually depend on those settings, which the first version of
this reconstruction did not: it read them and then searched with defaults.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chisurf.plugins.burst.burst_selection.api.models import (
    AnalysisRequest,
    AnalysisSettings,
    BurstDetectionSettings,
    DeltaMacroTimeFilterSettings,
    PhotonFilterSettings,
)
from chisurf.plugins.burst.burst_selection.api.reproduce import reproduce_burst_search
from chisurf.plugins.burst.burst_selection.api.selection import analyze_file, analyze_request

DATA = Path(__file__).resolve().parent / "data" / "bh_spc132_sm_dna"
SPC = DATA / "m000.spc"

pytestmark = pytest.mark.skipif(not SPC.exists(), reason="no BH SPC test data")


def _settings(min_photons: int) -> AnalysisSettings:
    s = AnalysisSettings()
    s.output_formats = ["pto"]
    s.photon_filter = PhotonFilterSettings(
        channels=[],
        filter_active=False,
        delta_macro_time_filter=DeltaMacroTimeFilterSettings(dT_min=0.0, dT_max=0.2),
    )
    s.burst_detection = BurstDetectionSettings(
        min_photons=min_photons, photon_window=10, time_window=1e-3
    )
    return s


def _container(tmp_path: Path, min_photons: int) -> Path:
    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    analyze_request(
        AnalysisRequest(files=[str(source)], settings=_settings(min_photons), legacy_output=False)
    )
    return source.with_suffix(".pto")


def test_the_stored_search_is_reproduced_from_the_container(tmp_path: Path):
    container = _container(tmp_path, min_photons=60)
    before = container.read_bytes()

    report = reproduce_burst_search(container)

    assert report.n_stored > 0
    assert report.is_exact, report
    assert report.lineage[-1]["name"] == SPC.name, "lineage must end at the photon stream"
    assert report.settings["burst_detection"]["min_photons"] == 60
    assert container.read_bytes() == before, "reproducing must not write the container"


def test_the_reproduction_uses_the_stored_settings_not_defaults(tmp_path: Path):
    """Different stored settings give a different, still exact, reproduction."""
    container = _container(tmp_path, min_photons=120)
    report = reproduce_burst_search(container)
    assert report.is_exact, report

    defaults = AnalysisSettings()
    defaults.output_formats = []
    rows = next(iter(analyze_file(container, settings=defaults).dataframes.values()))
    n_default = sum(1 for row in rows if row.get("Number of Photons"))
    assert n_default != report.n_reproduced, "the check would pass with the settings ignored"


def test_a_container_without_a_burst_table_is_refused(tmp_path: Path):
    from chisurf.plugins.core.tttr_to_pto import api as pto_api

    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    container = pto_api.convert([source])
    with pytest.raises(FileNotFoundError):
        reproduce_burst_search(container)
