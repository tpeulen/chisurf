"""The strict background selection runs once per (photons, bursts, IRFs), and gives what it gave.

The pipeline's hand-over set the setup and fitted before the references had given the IRFs:
that fit made the selection without an IRF to judge it by (and was blocked anyway, for want of
one), then the IRFs came and it was made again -- two selections of ~10 s on a real
measurement, the first one unused. Now a fit that is blocked for want of an IRF makes no
background, and an IRF taken again with the same numbers is not a new selection.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.core.fluorescence.burst import fused_pipeline, irf_bg

from .test_mle_restored_inputs import fresh_session, inputs  # noqa: F401 - fixture


@pytest.fixture
def counted(monkeypatch):
    calls = []
    real = irf_bg.strict_background_mask

    def mask(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(irf_bg, "strict_background_mask", mask)
    # the native selection (tttrlib's StrictBackground) is the same selection, counted the same
    native = fused_pipeline.session_strict_background

    def strict(*args, **kwargs):
        calls.append(1)
        return native(*args, **kwargs)

    monkeypatch.setattr(fused_pipeline, "session_strict_background", strict)
    return calls


def _selection(session):
    return dict(session.strict_background), {d: np.asarray(v).copy() for d, v in session.bg_strict_np.items()}


def test_the_hand_over_selects_once_and_as_before(inputs, counted):  # noqa: F811 - the fixture
    # the hand-over's order: the setup's fit before the IRF, then the IRF, then the fit
    session = fresh_session(Path(inputs["bur"]))
    session.set_binning(1)
    assert session.fit() is None and "no IRF" in session.status
    assert not counted, "no selection before there is an IRF to judge it by"
    session.set_pattern_files("irf", "synthetic", [inputs["irf"]])
    session.extract_irf_background()
    session.build_decay()
    assert session.fit() is not None, session.status
    # the IRF taken again from its source: a new array, the same numbers
    session.irf_np["synthetic"] = np.array(session.irf_np["synthetic"], copy=True)
    session.select_background()
    session.fit()
    assert len(counted) == 1
    got = _selection(session)

    # the selection made directly with the same IRF, in a session that never fitted early
    direct = fresh_session(Path(inputs["bur"]))
    direct.set_binning(1)
    direct.set_pattern_files("irf", "synthetic", [inputs["irf"]])
    direct.extract_irf_background()
    want = _selection(direct)
    assert got[0] == want[0] or all(
        (a == b) or (a != a and b != b) for a, b in zip(got[0].values(), want[0].values())
    )
    assert got[1].keys() == want[1].keys()
    for det in want[1]:
        np.testing.assert_array_equal(got[1][det], want[1][det])


def test_another_irf_is_another_selection(inputs, counted):  # noqa: F811 - the fixture
    session = fresh_session(Path(inputs["bur"]))
    session.set_binning(1)
    session.set_pattern_files("irf", "synthetic", [inputs["irf"]])
    session.extract_irf_background()
    session.irf_np["synthetic"] = np.roll(session.irf_np["synthetic"], 2)
    session.select_background()
    assert len(counted) == 2
