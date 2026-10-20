"""Contact kQ per dye reproduces the MalE prototype (chapter 3a) from the titration posterior.

The port is bit for bit on the platform that wrote the golden file; RTOL only absorbs a
different LAPACK in ``numpy.polyfit`` (the titration lines) elsewhere.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.core.inference import (
    columns,
    kq_scaling,
    measurements,
    titration,
)

GOLDEN = Path(__file__).resolve().parent / "baselines" / "male_prototype.json"
RTOL = 1e-12


@pytest.fixture(scope="module")
def golden():
    """The prototype golden document."""
    return json.loads(GOLDEN.read_text())


@pytest.fixture(scope="module")
def posterior():
    """The titration posterior of the shipped data."""
    data = measurements.load_measurements()
    return titration.analyse_titrations(data.titration_points)[1]


def test_textbook_kq_is_the_reference_chemistry(golden):
    assert kq_scaling.textbook_kq() == golden["KQ_TEXTBOOK"]


@pytest.fixture(scope="module")
def table(posterior, golden):
    """The kQ table, scaled from the textbook values the golden file was made with."""
    return kq_scaling.kq_table(posterior, textbook=golden["KQ_TEXTBOOK"])


def test_kq_table(table, golden):
    assert table.dyes == ("AF488", "Cy3B", "Atto655")
    assert table.quenchers == ("TRP", "TYR", "MET", "HIS", "PRO")
    for dye in table.dyes:
        ref, ref_sd = golden["KQ_TABLE"][dye], golden["KQ_TABLE_SD"][dye]
        np.testing.assert_allclose(
            [table.row(dye)[r] for r in table.quenchers],
            [ref[r] for r in table.quenchers],
            rtol=RTOL,
            atol=0,
        )
        np.testing.assert_allclose(
            [table.row_sd(dye)[r] for r in table.quenchers],
            [ref_sd[r] for r in table.quenchers],
            rtol=RTOL,
            atol=0,
        )


def test_printed_kq_rows(table):
    """The plan's printed rows (3 decimals)."""
    assert table.row("AF488") == {"TRP": 3.5, "TYR": 2.0, "MET": 1.67, "HIS": 1.0, "PRO": 2.0}
    assert not table.sd[0].any()  # the reference dye is exact by construction
    cy3b = [round(v, 3) for v in table.value[1]]
    assert cy3b == [4.625, 0.0, 0.024, 0.0, 2.643]
    assert [round(v, 3) for v in table.sd[1]] == [0.139, 0.240, 0.017, 0.0, 0.079]
    atto = [round(v, 3) for v in table.value[2]]
    assert atto == [3.030, 5.397, 0.0, 0.0, 1.732]
    assert [round(v, 3) for v in table.sd[2]] == [0.088, 0.445, 0.0, 0.0, 0.050]


def test_negative_slopes_do_not_quench(posterior, golden):
    """Cy3B Tyr/His and Atto655 Met/His have K_SV <= 0: kQ is 0, not negative."""
    k = posterior.k_mean()
    assert k[("Cy3B", "Tyr")] < 0 and k[("Atto655", "His")] < 0
    tb = golden["KQ_TEXTBOOK"]
    v = kq_scaling.kq_vector("Cy3B", k, posterior.tau0(), tb)
    assert v[1] == 0.0 and v[3] == 0.0


def test_long_table_follows_the_declaration(table):
    long = table.as_table()
    assert long.dtype.names == tuple(c["column"] for c in columns.columns("kq_contact"))
    assert len(long) == 15
    assert str(long["dye"][5]) == "Cy3B" and str(long["quencher"][5]) == "TRP"


@pytest.mark.parametrize(
    "preset, dye, tau0, linker",
    [
        ("AF488_C1R_MalE", "AF488", 4.108, 20.4),
        ("Cy3B_C2R", "Cy3B", 2.391, 19.74),
        ("Atto655_C2R", "Atto655", 1.846, 20.12),
    ],
)
def test_dye_presets_carry_the_measured_values(table, preset, dye, tau0, linker):
    from chisurf.plugins.quenching_estimator import settings

    entry = settings.dye_repository()[preset]
    assert entry["tau0"] == tau0
    assert entry["av_parameter"]["linker_length"] == linker
    assert entry["measured_analysis"]["linker_width"] == 0.5
    kq = {r: entry["amino_acid_interactions"][r]["kQ"] for r in table.quenchers}
    assert kq == {r: round(v, 3) for r, v in table.row(dye).items()}
    if dye == "Atto655":
        assert entry["tau0_D2O"] == 3.69
