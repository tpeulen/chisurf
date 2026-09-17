"""Cross-engine agreement for the H2MM surrogate: scikit-learn vs tttrlib C++.

The contract these tests defend: a surrogate trained here with scikit-learn and
exported to the language-neutral JSON schema must produce *identical* estimates
when executed by the C++ engine. That only holds if the feature extractor, the
scalers, the net, and the decoder all agree, so the tests check each link as
well as the end-to-end result.
"""

from __future__ import annotations

import json
import os
import tempfile

import numpy as np
import pytest

from chisurf.plugins.burst.burst_h2mm.core import engines, h2mm, surrogate

tttrlib = pytest.importorskip("tttrlib")
if not hasattr(tttrlib, "HmmSurrogate"):
    pytest.skip("tttrlib without HmmSurrogate support", allow_module_level=True)

from chisurf.plugins.burst.burst_h2mm.core import surrogate_tttrlib  # noqa: E402

pytestmark = pytest.mark.skipif(
    not surrogate.surrogate_available(), reason="scikit-learn is required"
)


def _dataset(n_bursts=40, burst_len=60, n_streams=2, seed=0):
    rng = np.random.default_rng(seed)
    times, streams = [], []
    for _ in range(n_bursts):
        t = np.concatenate([[0], np.cumsum(rng.poisson(4, burst_len - 1) + 1)]).astype(np.int64)
        state = rng.random(burst_len) < 0.5
        e = np.where(state, 0.75, 0.25)
        s = (rng.random(burst_len) < e).astype(np.int32)
        times.append(t)
        streams.append(s)
    return h2mm.prepare_bursts(times, streams, n_streams)


@pytest.fixture(scope="module")
def trained():
    """A small scikit-learn surrogate; slow enough to be worth sharing."""
    return surrogate.train_surrogate(
        n_states=2,
        n_streams=2,
        n_samples=60,
        hidden_layer_sizes=(32, 32),
        max_iter=80,
        n_bursts=20,
        burst_len=40,
        seed=3,
    )


def test_feature_extractors_agree(trained):
    """The C++ extractor must reproduce the numba one bit for bit."""
    data = _dataset(seed=5)
    np.testing.assert_allclose(
        surrogate_tttrlib.extract_features(data),
        surrogate.extract_features(data),
        rtol=0,
        atol=1e-12,
    )


def test_export_json_schema(trained):
    doc = trained.to_json()
    assert doc["format"] == "tttrlib.hmm_surrogate"
    assert doc["n_states"] == 2 and doc["n_streams"] == 2
    assert doc["features_version"] == surrogate.FEATURES_VERSION
    assert doc["net"]["format"] == "tttrlib.neural_net"

    # weights must be transposed relative to sklearn's (n_in, n_out) layout
    layer0, coef0 = doc["net"]["layers"][0], trained.net.coefs_[0]
    assert layer0["n_in"] == coef0.shape[0]
    assert layer0["n_out"] == coef0.shape[1]
    np.testing.assert_allclose(
        np.asarray(layer0["weight"]).reshape(layer0["n_out"], layer0["n_in"]),
        np.asarray(coef0).T,
        rtol=0,
        atol=1e-15,
    )


def test_cpp_and_sklearn_estimates_agree(trained):
    """End-to-end: same surrogate, same data, same model out of either engine."""
    data = _dataset(seed=7)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "surrogate.json")
        trained.export_json(path)
        got = surrogate_tttrlib.estimate_model(data, 2, path)

    expect = surrogate.estimate_model(data, 2, trained)
    np.testing.assert_allclose(got.obs, expect.obs, rtol=0, atol=1e-9)
    np.testing.assert_allclose(got.trans, expect.trans, rtol=0, atol=1e-9)
    np.testing.assert_allclose(got.prior, expect.prior, rtol=0, atol=1e-9)


def test_refinement_agrees_too(trained):
    data = _dataset(seed=11)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "surrogate.json")
        trained.export_json(path)
        got = surrogate_tttrlib.estimate_model(data, 2, path, refine_iters=5)
    expect = surrogate.estimate_model(data, 2, trained, refine_iters=5)
    np.testing.assert_allclose(got.obs, expect.obs, rtol=0, atol=1e-7)


def test_engines_routes_json_surrogate_to_tttrlib(trained):
    """fit_one must accept a JSON path and still match the Python path."""
    data = _dataset(seed=13)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "surrogate.json")
        trained.export_json(path)
        via_json = engines.fit_one(data, 2, engine="surrogate", surrogates={2: path})
    via_obj = engines.fit_one(data, 2, engine="surrogate", surrogates={2: trained})
    np.testing.assert_allclose(via_json.obs, via_obj.obs, rtol=0, atol=1e-9)


def test_engines_falls_back_to_em_without_a_surrogate():
    data = _dataset(seed=17)
    model = engines.fit_one(data, 2, engine="surrogate", surrogates={})
    # EM populates the log-likelihood; the one-shot surrogate path does not.
    assert np.isfinite(model.loglik)


def test_state_count_mismatch_is_rejected(trained):
    data = _dataset(seed=19)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "surrogate.json")
        trained.export_json(path)
        with pytest.raises(ValueError):
            surrogate_tttrlib.estimate_model(data, 3, path)


def test_stale_features_version_is_rejected(trained):
    _dataset(seed=23)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "surrogate.json")
        doc = trained.to_json()
        doc["features_version"] = surrogate.FEATURES_VERSION + 1
        with open(path, "w") as fh:
            json.dump(doc, fh)
        with pytest.raises(Exception) as exc:
            surrogate_tttrlib.load(path)
    assert "features_version" in str(exc.value)
