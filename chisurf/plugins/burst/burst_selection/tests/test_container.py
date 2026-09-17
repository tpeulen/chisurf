"""Burst selection writing one container instead of a directory tree.

The legacy layout is a folder whose *name* encodes the parameters, holding a
`.bur` plus four `Info/` files, and whose companions are merged with it by
counting rows. The container replaces the folder; these tests pin the two things
that make it a replacement rather than a rename — that nothing is lost, and that
the parts of the old format which were only ever file-format bookkeeping do not
come with it.

The column list is checked against a baseline captured from the legacy writer
**before** it was touched (`test/data/baselines/burst_selection_legacy.json`),
because "the new output looks fine" is the wrong question for a migration.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from chisurf.core.datastore import column_names, numeric_column, row_count
from chisurf.core.fio.pto import Measurement
from chisurf.plugins.burst.burst_selection.api.io import deinterleave_bursts
from chisurf.plugins.burst.burst_selection.api.models import (
    AnalysisRequest,
    AnalysisSettings,
    BurstDetectionSettings,
    DeltaMacroTimeFilterSettings,
    GMMSettings,
    PhotonFilterSettings,
)
from chisurf.plugins.burst.burst_selection.api.selection import analyze_request

DATA = Path(__file__).resolve().parent / "data" / "bh_spc132_sm_dna"
SPC = DATA / "m000.spc"
BASELINE = (
    Path(__file__).resolve().parents[5]
    / "test"
    / "data"
    / "baselines"
    / "burst_selection_legacy.json"
)

pytestmark = pytest.mark.skipif(not SPC.exists(), reason="no BH SPC test data")


def _settings(formats: list[str]) -> AnalysisSettings:
    s = AnalysisSettings()
    s.photon_filter = PhotonFilterSettings(
        channels=[],
        filter_active=False,
        delta_macro_time_filter=DeltaMacroTimeFilterSettings(dT_min=0.0, dT_max=0.2),
    )
    s.burst_detection = BurstDetectionSettings(min_photons=60, photon_window=10, time_window=1e-3)
    s.gmm = GMMSettings(covariance_type="spherical", random_state=42, max_iter=50)
    s.output_formats = formats
    return s


@pytest.fixture
def analysed(tmp_path: Path) -> Path:
    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    companion = SPC.with_suffix(".set")
    if companion.exists():
        (tmp_path / companion.name).write_bytes(companion.read_bytes())

    result = analyze_request(
        AnalysisRequest(
            files=[str(source)],
            settings=_settings(["pto"]),
            legacy_output=False,
            selected_setup="Test",
        )
    )
    return Path(result.output_paths["pto"])


# -- nothing is lost -----------------------------------------------------------


@pytest.mark.skipif(not BASELINE.exists(), reason="no captured legacy baseline")
def test_every_legacy_column_survives(analysed: Path):
    """Parity is judged on the column inventory, not on bytes: the container
    deliberately stores a table where the folder stored a padded text grid.
    """
    want = json.loads(BASELINE.read_text())["bur_columns"]
    with Measurement.open(analysed) as m:
        got = column_names(m.get_store("bursts"))
    missing = [c for c in want if c not in got]
    assert not missing, f"columns lost in the migration: {missing}"


def test_the_burst_count_matches_the_legacy_writer(tmp_path: Path):
    """The legacy file is 2N+1 physical rows; N is the number of bursts.

    Checked against the ``.bur`` this same run writes, not against a burst
    count captured once into the baseline file. The claim being made is a
    *migration* claim -- the container holds every burst the folder holds --
    and pinning it to a stored integer instead turned it into a second, much
    weaker claim: that the analysis never changes its answer. It did change
    (``min_photons`` is now applied for every search, not only the
    sliding-window one), and a parity test is the wrong place to find that out.
    """
    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    result = analyze_request(
        AnalysisRequest(
            files=[str(source)],
            settings=_settings(["pto", "bur"]),
            legacy_output=True,
            selected_setup="Test",
        )
    )
    from chisurf.core.fio.fluorescence.burst_tree import read_burst_table

    bur_lines = Path(result.output_paths["bur"]).read_text().splitlines()
    # The header line, then 2N+1 interleaved data rows.
    expected = (len(bur_lines) - 2) // 2
    assert row_count(read_burst_table(Path(result.output_paths["pto"]))) == expected


# -- and the bookkeeping does not come with it ---------------------------------


def test_the_interleave_is_not_carried_out_of_the_container(analysed: Path):
    """The zero rows are file-format padding, and a *reader* never sees them.

    They are stored — the container holds the `.bur` 1:1 so that unpacking
    reproduces it — and they come off on the way out, which is the same stride
    the folder reader applies to the same rows. What must never happen is a
    caller receiving them as bursts.
    """
    from chisurf.core.fio.fluorescence.burst_tree import read_burst_table

    store = read_burst_table(analysed)
    numeric_names = [n for n in column_names(store) if store[n].dtype not in ("str", "bool")]
    numeric = np.column_stack([numeric_column(store, n) for n in numeric_names])
    all_zero = np.all(numeric == 0, axis=1)
    assert not all_zero.any(), f"{int(all_zero.sum())} sentinel rows came through"


def test_the_trailing_tab_column_is_not_handed_to_a_reader(analysed: Path):
    """The blank column exists only to produce the trailing tab the `.bur`
    header needs. It is not data, and a reader is not given it.
    """
    from chisurf.core.fio.fluorescence.burst_tree import read_burst_table

    store = read_burst_table(analysed)
    assert [c for c in column_names(store) if not str(c).strip()] == []


def test_one_measurement_leaves_one_container_and_no_folder(analysed: Path):
    """The point of the exercise."""
    beside = sorted(p.name for p in analysed.parent.iterdir())
    assert analysed.name in beside
    assert not [p for p in analysed.parent.iterdir() if p.is_dir()]


# -- provenance ----------------------------------------------------------------


def test_the_bursts_record_where_they_came_from(analysed: Path):
    with Measurement.open(analysed) as m:
        uid = m._resolve("bursts")
        assert m.tag(uid, "_mmfdb_operation.operation_type") == "burst_selection"
        assert m.tag(uid, "_mmfdb_artifact.row_grain") == "burst"
        assert m.parents(uid) == [m.instrument_uid]
        assert m.tag(uid, "_mmfdb_operation.settings_hash")
        assert m.verify() == []


def test_the_instrument_file_is_still_recoverable(tmp_path: Path, analysed: Path):
    import hashlib

    with Measurement.open(analysed) as m:
        out = m.extract(m.instrument_uid, tmp_path / "back.spc")
    assert hashlib.sha256(out.read_bytes()).hexdigest() == (
        hashlib.sha256(SPC.read_bytes()).hexdigest()
    )


def test_rerunning_does_not_accumulate(tmp_path: Path):
    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    request = AnalysisRequest(files=[str(source)], settings=_settings(["pto"]), legacy_output=False)
    first = Path(analyze_request(request).output_paths["pto"])
    with Measurement.open(first) as m:
        before = m._f.n_objects()
    analyze_request(request)
    with Measurement.open(first) as m:
        assert m._f.n_objects() == before


# -- the de-interleaver on its own ---------------------------------------------


def test_deinterleave_takes_the_odd_rows():
    frame = pd.DataFrame({"a": [0, 1, 0, 2, 0], "b": [0.0, 1.5, 0.0, 2.5, 0.0], "": [""] * 5})
    out = deinterleave_bursts(frame)
    assert list(np.asarray(out["a"])) == [1, 2]
    assert column_names(out) == ["a", "b"]


def test_deinterleave_leaves_a_plain_table_alone():
    frame = pd.DataFrame({"a": [1, 2, 3], "b": [1.0, 2.0, 3.0]})
    out = deinterleave_bursts(frame)
    assert row_count(out) == 3
    assert list(np.asarray(out["a"])) == [1, 2, 3]


def test_deinterleave_keeps_a_genuine_zero_burst():
    """An odd row that happens to be all zeros is data; only the *even* rows
    are the padding, and the check is on those.
    """
    frame = pd.DataFrame({"a": [0, 0, 0, 5, 0], "b": [0.0, 0.0, 0.0, 5.0, 0.0]})
    out = deinterleave_bursts(frame)
    assert row_count(out) == 2
    assert list(np.asarray(out["a"])) == [0, 5]


# -- the default ---------------------------------------------------------------


def test_the_container_is_what_an_analysis_writes_by_default(tmp_path: Path):
    """`.pto` is ChiSurf's format for photon data, not one option among several.

    A default that produced the legacy folder made the container something a
    caller had to know to ask for, which is the opposite of the arrangement: a
    measurement's results belong in the measurement's file, and the `…4`
    directories are an export for tools that read them.
    """
    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())

    settings = AnalysisSettings()
    assert settings.output_formats == ["pto"]

    result = analyze_request(
        AnalysisRequest(files=[str(source)], settings=settings, legacy_output=False)
    )
    written = Path(result.output_paths["pto"])
    assert written == source.with_suffix(".pto")
    with Measurement.open(written) as m:
        assert row_count(m.get_store("bursts")) > 0


def test_the_legacy_folder_is_written_only_when_it_is_asked_for(tmp_path: Path):
    """And when it is asked for, it holds the `.bur` that is the point of it.

    Asking for the folder while asking for no format that goes in it used to
    produce a directory holding two `Info/` files and nothing else, freshly
    numbered on every run, which ndX then refused with "No .bur files in
    'bi4_bur' or 'bur'". The legacy layout *is* the `.bur` plus its sidecars, so
    requesting the layout requests the format.
    """
    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())

    result = analyze_request(
        AnalysisRequest(files=[str(source)], settings=_settings(["pto"]), legacy_output=False)
    )
    assert "bur" not in result.output_paths
    assert not [p for p in source.parent.iterdir() if p.is_dir()]

    result = analyze_request(
        AnalysisRequest(files=[str(source)], settings=_settings(["pto"]), legacy_output=True)
    )
    assert "bur" in result.output_paths
    assert Path(result.output_paths["bur"]).exists()


# -- a container is the output, not a thing to write beside ---------------------


def test_a_pto_source_writes_no_folder_even_when_one_is_asked_for(tmp_path: Path):
    """`.pto` in, `.pto` out.

    A container already holds the photons and every result computed from them,
    which is the whole point of it. Writing a parameter-named directory beside
    it puts the same bursts in two places, freshly numbered on every run, and
    the two disagree the moment one of them is re-run — which is exactly how a
    downstream step came to read an eight-burst table from a stale folder while
    the panel above it showed hundreds.
    """
    from chisurf.plugins.core.tttr_to_pto import api as pto_api

    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    container = pto_api.convert(source)
    source.unlink()

    result = analyze_request(
        AnalysisRequest(
            files=[str(container)],
            settings=_settings(["pto"]),
            legacy_output=True,
        )
    )

    assert result.output_paths.get("pto") == str(container)
    assert "bur" not in result.output_paths
    assert not [p for p in container.parent.iterdir() if p.is_dir()]

    # There *is* an analysis path — it just points inside the container. A
    # container is addressed like a folder, so a downstream step is handed
    # `m000.pto/<run>` and needs no idea which of the two it was given.
    from chisurf.core.fio.analysis_path import is_container_path, split_container_path

    analysis = result.output_paths["output_folder"]
    assert is_container_path(analysis)
    assert split_container_path(analysis) == (container, "countrate_All 0.2000#60")
    assert not Path(analysis).exists()


def test_the_results_still_land_when_the_folder_is_suppressed(tmp_path: Path):
    """Suppressing the folder must not suppress the output with it."""
    from chisurf.plugins.core.tttr_to_pto import api as pto_api

    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    container = pto_api.convert(source)

    settings = _settings(["bur"])  # a folder-only request, against a container
    result = analyze_request(
        AnalysisRequest(files=[str(container)], settings=settings, legacy_output=True)
    )

    assert result.output_paths.get("pto") == str(container)
    with Measurement.open(container) as m:
        assert row_count(m.get_store("bursts")) > 0


def test_a_vendor_file_still_gets_its_folder(tmp_path: Path):
    """The suppression is about containers, not about the legacy layout."""
    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())

    result = analyze_request(
        AnalysisRequest(files=[str(source)], settings=_settings(["pto"]), legacy_output=True)
    )

    assert "bur" in result.output_paths
    assert Path(result.output_paths["bur"]).exists()
