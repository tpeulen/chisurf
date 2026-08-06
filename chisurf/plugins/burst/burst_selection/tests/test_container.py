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
    s.burst_detection = BurstDetectionSettings(
        min_photons=60, photon_window=10, time_window=1e-3
    )
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
    deliberately stores a table where the folder stored a padded text grid."""
    want = json.loads(BASELINE.read_text())["bur_columns"]
    with Measurement.open(analysed) as m:
        got = list(m.get_table("bursts").columns)
    missing = [c for c in want if c not in got]
    assert not missing, f"columns lost in the migration: {missing}"


@pytest.mark.skipif(not BASELINE.exists(), reason="no captured legacy baseline")
def test_the_burst_count_matches_the_legacy_writer(analysed: Path):
    """The legacy file is 2N+1 physical rows; N is the number of bursts."""
    base = json.loads(BASELINE.read_text())
    expected = (base["bur_lines"] - 1) // 2
    with Measurement.open(analysed) as m:
        assert len(m.get_table("bursts")) == expected


# -- and the bookkeeping does not come with it ---------------------------------


def test_the_interleave_is_not_carried_into_the_container(analysed: Path):
    """The zero rows exist so companions can be merged by counting; the
    container joins on declared keys, so a placeholder row would only destroy
    the information that a burst was absent."""
    with Measurement.open(analysed) as m:
        df = m.get_table("bursts")
    numeric = df.select_dtypes(include="number")
    all_zero = (numeric == 0).all(axis=1)
    assert not all_zero.any(), f"{int(all_zero.sum())} sentinel rows came through"


def test_the_trailing_tab_column_is_not_carried_over(analysed: Path):
    """The blank column exists only to produce the trailing tab the `.bur`
    header needs. It is not data."""
    with Measurement.open(analysed) as m:
        df = m.get_table("bursts")
    assert [c for c in df.columns if not str(c).strip()] == []


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
    request = AnalysisRequest(
        files=[str(source)], settings=_settings(["pto"]), legacy_output=False
    )
    first = Path(analyze_request(request).output_paths["pto"])
    with Measurement.open(first) as m:
        before = m._f.n_objects()
    analyze_request(request)
    with Measurement.open(first) as m:
        assert m._f.n_objects() == before


# -- the de-interleaver on its own ---------------------------------------------


def test_deinterleave_takes_the_odd_rows():
    frame = pd.DataFrame(
        {"a": [0, 1, 0, 2, 0], "b": [0.0, 1.5, 0.0, 2.5, 0.0], "": [""] * 5}
    )
    out = deinterleave_bursts(frame)
    assert list(out["a"]) == [1, 2]
    assert list(out.columns) == ["a", "b"]


def test_deinterleave_leaves_a_plain_frame_alone():
    frame = pd.DataFrame({"a": [1, 2, 3], "b": [1.0, 2.0, 3.0]})
    out = deinterleave_bursts(frame)
    assert len(out) == 3
    assert list(out["a"]) == [1, 2, 3]


def test_deinterleave_keeps_a_genuine_zero_burst():
    """An odd row that happens to be all zeros is data; only the *even* rows
    are the padding, and the check is on those."""
    frame = pd.DataFrame({"a": [0, 0, 0, 5, 0], "b": [0.0, 0.0, 0.0, 5.0, 0.0]})
    out = deinterleave_bursts(frame)
    assert len(out) == 2
    assert list(out["a"]) == [0, 5]
