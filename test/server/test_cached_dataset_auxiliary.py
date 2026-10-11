"""A cached curve keeps the payload beside x/y that its models fit (PDA's S1S2 histogram).

The emtk shell reads a file in its own process and sends the decoded curve to
the session server (``dataset.load`` with ``curve_data``). A PDA curve is a
flattened S1S2 histogram whose models need the matrix and the photon-count
indices of ``curve.pda``; the server refused any such payload, so no PDA file
could be read into the shell, and the Qt shell in server mode fell back to a
dataset the server never saw.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.api import _extract_curve_data
from chisurf.core.data import DataCurve
from chisurf.server.services import datasets
from chisurf.server.session import SessionState


def _pda_curve() -> DataCurve:
    from chisurf.core.experiments.pda2c import Pda2cReader

    reader = Pda2cReader(channels=[[0], [1]], micro_time_ranges=[[0, 10], [0, 10]], name="PDA")
    s1s2 = np.arange(9.0).reshape(3, 3)
    return DataCurve(
        name="m000",
        x=np.arange(9.0),
        y=s1s2.ravel(),
        ey=np.ones(9),
        load_filename_on_init=False,
        data_reader=reader,
        pda={"s1s2": s1s2, "ndim": 2, "shape": (3, 3), "row_indices": [0, 0, 0, 1, 1, 1, 2, 2, 2]},
    )


def test_a_cached_pda_curve_arrives_with_its_histogram():
    state = SessionState()
    result = datasets.add_dataset(state, curve_data=_extract_curve_data(_pda_curve()))
    assert result["ok"], result
    curve = state.datasets[-1]
    np.testing.assert_array_equal(curve.pda["s1s2"], np.arange(9.0).reshape(3, 3))
    assert curve.pda["row_indices"] == [0, 0, 0, 1, 1, 1, 2, 2, 2]


def test_an_unknown_auxiliary_field_is_refused():
    payload = _extract_curve_data(_pda_curve())
    payload["auxiliary"]["shellcode"] = {"x": 1}
    result = datasets.add_dataset(SessionState(), curve_data=payload)
    assert result["ok"] is False and "auxiliary" in result["error"]


@pytest.mark.parametrize("field", ["pda", "pda3c", "mfd"])
def test_the_project_codec_and_the_cache_accept_the_same_fields(field):
    from chisurf.core.project.session import AUXILIARY_FIELDS

    assert field in AUXILIARY_FIELDS
