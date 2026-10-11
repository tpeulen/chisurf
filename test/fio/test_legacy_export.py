"""The one explicit export of a measurement container to the Seidel/Margarita folder.

Every burst step writes a run into the ``.pto``; a companion exists only because
somebody asked for one. These tests state what that export promises: one row per
burst of the measurement -- the skipped ones as sentinel rows -- directory names
that end in ``4``, and values equal to the run tables they were made from.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.datastore import numeric_column, store_from_arrays
from chisurf.core.fio.fluorescence.burst_companion import (
    CompanionError,
    is_companion_dir,
    read_companion,
)
from chisurf.core.fio.fluorescence.burst_container import (
    container_for,
    write_burst_artifact,
)
from chisurf.core.fio.fluorescence.legacy_export import (
    COMPANION_ENDINGS,
    COMPANIONS,
    export_legacy,
)

DATA = Path(__file__).resolve().parents[1] / "data"
PTU = DATA / "clsm" / "Leica_SP5.ptu"
RUN = "countrate_All 0.1000#60"
N = 20

pytestmark = pytest.mark.skipif(not PTU.exists(), reason="no instrument test data")


def _interleaved_bursts(n: int = N):
    """A burst table as the ``.bur`` file holds it: ``2n + 1`` rows, data on the odd ones."""
    first = np.zeros(2 * n + 1)
    first[1::2] = np.arange(n) * 100.0
    photons = np.zeros(2 * n + 1)
    photons[1::2] = np.arange(n) + 60.0
    return store_from_arrays({"First Photon": first, "Number of Photons": photons})


@pytest.fixture
def measurement(tmp_path: Path) -> Path:
    raw = tmp_path / "m000.ptu"
    shutil.copy(PTU, raw)
    write_burst_artifact(
        raw,
        _interleaved_bursts(),
        name=f"{RUN}/bi4_bur/m000.bur",
        deinterleave=False,
        artifact_kind="burst_table",
        operation_type="burst_selection",
        row_grain="burst",
        parameters={"min_photons": 60},
        derived_from=(),
    )
    return raw


def _write(raw: Path, name: str, columns: dict, operation: str, **kwargs):
    write_burst_artifact(
        raw,
        store_from_arrays(columns),
        name=name,
        artifact_kind=kwargs.pop("artifact_kind", "burst_table"),
        operation_type=operation,
        row_grain=kwargs.pop("row_grain", "burst"),
        derived_from=(),
        **kwargs,
    )


def test_bursts_bva_and_2cde_export_to_companions_equal_to_the_run_tables(
    measurement: Path, tmp_path: Path
):
    mean = np.linspace(0.1, 0.9, N)
    std = np.linspace(0.01, 0.05, N)
    cde = np.linspace(8.0, 40.0, N)
    cde[[3, 11]] = np.nan  # two bursts the 2CDE could not score
    _write(
        measurement,
        "bva",
        {"Proximity Ratio Mean": mean, "Proximity Ratio Std": std},
        "burst_variance_analysis",
        parameters={"window": 5},
    )
    _write(measurement, "2cde fret", {"FRET-2CDE": cde}, "burst_2cde", parameters={"tau": 50})

    out = tmp_path / "legacy"
    written = export_legacy(container_for(measurement), out)

    bur = out / RUN / "bi4_bur" / "m000.bur"
    assert bur in written and bur.is_file()
    # the companions sit beside the burst table that defines their grid
    bva = out / RUN / "bv4" / "m000.bv4"
    two = out / RUN / "2c4" / "m000.2c4"
    assert bva.is_file() and two.is_file()
    assert is_companion_dir(bva.parent.name) and is_companion_dir(two.parent.name)

    columns, rows = read_companion(bva)
    assert columns == ["Proximity Ratio Mean", "Proximity Ratio Std"]
    assert rows.shape == (N, 2)  # one row per burst
    np.testing.assert_allclose(rows[:, 0], mean, atol=1e-6)
    np.testing.assert_allclose(rows[:, 1], std, atol=1e-6)

    columns, rows = read_companion(two)
    assert rows.shape == (N, 1)
    expected = np.nan_to_num(cde, nan=0.0)  # skipped bursts: sentinel rows, not absent rows
    np.testing.assert_allclose(rows[:, 0], expected, atol=1e-6)
    assert rows[3, 0] == 0.0 and rows[11, 0] == 0.0
    # the physical file is the 2N+1 zero-interleaved layout the readers stride over
    assert len(two.read_text().splitlines()) == 1 + (2 * N + 1)


def test_a_keyed_result_is_placed_on_the_full_burst_grid(measurement: Path, tmp_path: Path):
    """H2MM keeps only the bursts it fitted; the key puts them back, skipped ones as zeros."""
    kept = np.array([0, 2, 3, 7, 19])
    _write(
        measurement,
        "h2mm",
        {
            "Burst": kept.astype(float),
            "H2MM State": np.array([0, 1, 1, 0, 1], dtype=float),
            "H2MM Fitted": np.ones(kept.size),
        },
        "photon_hmm",
        parameters={"states": 2},
        source_row_column="Burst",
    )
    out = tmp_path / "legacy"
    written = export_legacy(container_for(measurement), out)
    bh4 = next(p for p in written if p.suffix == ".bh4")
    columns, rows = read_companion(bh4)
    assert columns == ["H2MM State", "H2MM Fitted"]  # the key is not a column
    assert rows.shape == (N, 2)
    fitted = rows[:, columns.index("H2MM Fitted")]
    assert fitted[kept].tolist() == [1.0] * kept.size
    assert fitted.sum() == kept.size  # every other burst: the sentinel row
    assert rows[7, 0] == 0.0 and rows[19, 0] == 1.0  # burst 19 is not shifted up


def test_a_per_detector_fit_goes_to_its_colours_ending(measurement: Path, tmp_path: Path):
    for detector, tau in (("green", 2.0), ("red", 1.0)):
        _write(
            measurement,
            f"mle {detector}",
            {f"Tau ({detector})": np.full(N, tau)},
            "burst_lifetime_fitting",
            artifact_kind="fit_result",
            algorithm="mle",
            parameters={"detector": detector},
        )
    written = export_legacy(container_for(measurement), tmp_path / "legacy")
    endings = {p.suffix for p in written if p.suffix.endswith("4")}
    assert {".bg4", ".br4"} <= endings


def test_every_exported_ending_is_discoverable():
    assert COMPANION_ENDINGS and all(is_companion_dir(e) for e in COMPANION_ENDINGS)
    assert {"bv4", "2c4", "bg4", "br4", "by4", "bh4", "td4", "bf4"} <= set(COMPANION_ENDINGS)
    assert set(COMPANIONS) >= {"burst_2cde", "burst_variance_analysis", "photon_hmm"}


def test_an_unregistered_operation_is_refused_not_guessed(measurement: Path, tmp_path: Path):
    _write(measurement, "ebfret fit", {"X": np.arange(N, dtype=float)}, "model_fitting")
    with pytest.raises(CompanionError, match="no registered legacy companion"):
        export_legacy(container_for(measurement), tmp_path / "a", operations=["model_fitting"])
    # without naming it, it is skipped (and logged), and nothing is written for it
    written = export_legacy(container_for(measurement), tmp_path / "b")
    assert not any("ebfret" in str(p) for p in written if p.suffix.endswith("4"))


def test_a_result_that_does_not_fit_the_grid_is_refused(measurement: Path, tmp_path: Path):
    """Three rows for twenty bursts, with no key: exporting it would shift the rest."""
    _write(
        measurement,
        "bva",
        {"Proximity Ratio Mean": np.arange(3.0)},
        "burst_variance_analysis",
        parameters={"window": 5},
    )
    with pytest.raises(CompanionError, match="no burst table in the container has that many"):
        export_legacy(container_for(measurement), tmp_path / "legacy")


def test_the_companion_values_read_back_from_the_container(measurement: Path, tmp_path: Path):
    from chisurf.core.fio.pto import Measurement

    values = np.linspace(0, 1, N)
    _write(
        measurement,
        "bva",
        {"Proximity Ratio Mean": values},
        "burst_variance_analysis",
        parameters={"window": 5},
    )
    with Measurement.open(container_for(measurement)) as m:
        stored = numeric_column(m.get_store("bva"), "Proximity Ratio Mean")
    written = export_legacy(container_for(measurement), tmp_path / "legacy")
    bv4 = next(p for p in written if p.suffix == ".bv4")
    np.testing.assert_allclose(read_companion(bv4)[1][:, 0], np.asarray(stored), atol=1e-6)


def test_mle_h2mm_fcs_are_runs_of_their_own_derived_from_the_burst_table(
    measurement: Path, tmp_path: Path
):
    """Each analysis is its own picker row, traces to the photons through the search, and exports."""
    from chisurf.core.fio.pto import Measurement
    from chisurf.plugins.burst.burst_fcs_correlator.core.export import write_fcs_container
    from chisurf.plugins.burst.burst_h2mm.core.export import write_h2mm_container
    from chisurf.plugins.burst.burst_mle_analysis.core.export import write_mle_container
    from chisurf.plugins.core.pto_inspector.core import run_rows_for

    box = container_for(measurement)
    green = store_from_arrays({"Tau (green)": np.linspace(1.0, 4.0, N)})
    write_mle_container(box, {"green": green}, parameters={"model": "a"})
    write_h2mm_container(
        box,
        store_from_arrays({"H2MM State": np.arange(N, dtype=float)}),
        None,
        parameters={"states": 2},
    )
    write_fcs_container(
        box,
        store_from_arrays({"Burst Index": np.array([0.0, 5.0]), "td_a": np.array([1.0, 2.0])}),
        parameters={"pairs": "a"},
    )

    rows = run_rows_for(box, operation="")
    assert len(rows) == 4 and all(r["run_name"] for r in rows), rows
    with Measurement.open(box, writable=False) as m:
        for obj in m.artifacts():
            if obj.kind in ("readme", "tttr_photon_stream"):
                continue
            chain = m.lineage(obj.uid)
            assert chain[-1]["name"] == "m000.ptu", chain
            if obj.name.rpartition("/")[2] in ("mle green", "h2mm", "burst fcs"):
                assert chain[1]["name"].endswith("m000.bur"), chain
    out = tmp_path / "legacy"
    export_legacy(box, out)
    assert (out / RUN / "bg4" / "m000.bg4").is_file()
    assert (out / RUN / "bh4" / "m000.bh4").is_file()
    assert (out / RUN / "td4" / "m000.td4").is_file()
