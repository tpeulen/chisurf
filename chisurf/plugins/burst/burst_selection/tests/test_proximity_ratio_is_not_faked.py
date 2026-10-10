"""A proximity ratio that cannot be computed must not be drawn as zero.

A burst table searched without detector definitions has no per-detector column,
so there is nothing to form ``red / (green + red)`` from. Filling that with
zeros put every burst at exactly PR = 0 — a single hard spike in the histogram,
indistinguishable from a real population of zero-efficiency molecules, and the
one answer worse than none.

The way in is ordinary: a micro-second ALEX file carries the alternation in the
macro time, so before the Alternation step its micro time is empty and any
micro-time gate selects nothing. (The gate-mismatch sentence and the refusal to
search such data are tested in ``test_diagnostics.py`` and
``test_emtk_native_behaviour.py``.)
"""

from __future__ import annotations

import numpy as np

from chisurf.core.datastore import store_from_arrays
from chisurf.plugins.burst.burst_selection.api.features import (
    extract_features,
    proximity_ratio,
)


def _table(**columns):
    return store_from_arrays({k: np.asarray(v, dtype=float) for k, v in columns.items()})


def test_no_detector_columns_gives_nan_not_zero():
    frame = _table(
        **{
            "Number of Photons": [100.0, 200.0, 300.0],
            "Duration (ms)": [1.0, 2.0, 3.0],
        }
    )
    assert proximity_ratio(frame) is None
    fret = np.asarray(extract_features([frame])["fret"], dtype=float)
    assert np.all(np.isnan(fret)), "an uncomputable ratio was drawn as zero"


def test_all_zero_detector_counts_give_nan():
    """The unconverted-ALEX shape: the columns exist and hold nothing."""
    frame = _table(
        **{
            "Number of Photons": [100.0, 200.0],
            "Duration (ms)": [1.0, 2.0],
            "Number of Photons (green)": [0.0, 0.0],
            "Number of Photons (red)": [0.0, 0.0],
        }
    )
    assert np.all(np.isnan(np.asarray(proximity_ratio(frame), dtype=float)))
    fret = np.asarray(extract_features([frame])["fret"], dtype=float)
    assert np.all(np.isnan(fret))


def test_a_real_ratio_is_still_computed():
    frame = _table(
        **{
            "Number of Photons": [100.0, 200.0],
            "Duration (ms)": [1.0, 2.0],
            "Number of Photons (green)": [75.0, 50.0],
            "Number of Photons (red)": [25.0, 150.0],
        }
    )
    np.testing.assert_allclose(np.asarray(proximity_ratio(frame), dtype=float), [0.25, 0.75])


def test_an_uncomputable_feature_does_not_discard_every_burst():
    """Dropping a *column* is not the same as dropping the bursts.

    The GMM's row filter needs every feature finite. With one all-NaN feature
    that removed every burst and returned "0 components" for data that clusters
    perfectly well on the other four — which is what turning the faked zeros
    into honest NaNs would otherwise have cost.
    """
    from chisurf.plugins.burst.burst_selection.api.features import fit_gmm

    rng = np.random.default_rng(0)
    n = 200
    frame = _table(
        **{
            "Number of Photons": rng.normal(300, 40, n),
            "Duration (ms)": rng.normal(2.0, 0.3, n),
            # no per-detector columns -> the proximity ratio is NaN for every burst
        }
    )
    features = extract_features([frame])
    assert np.all(np.isnan(np.asarray(features["fret"], dtype=float)))

    result = fit_gmm(features)
    assert result["n_components"] >= 1, "an all-NaN feature discarded every burst"
    assert "fret" not in result["features"]
    assert len(result["means"][0]) == len(result["features"])
