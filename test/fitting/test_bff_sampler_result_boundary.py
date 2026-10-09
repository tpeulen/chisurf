"""Result-export boundary contracts for BFF-native ChiSurf sampling."""

import operator
import pathlib
import sys
from functools import partial

import numpy as np
import pytest

from chisurf.core.fitting import sampler_bff

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


def test_two_argument_progress_callback_does_not_build_partial_result(monkeypatch):
    calls = []
    original = sampler_bff._result

    def record_materialization(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(sampler_bff, "_result", record_materialization)
    monkeypatch.setattr(sampler_bff, "_substeps", lambda _value: 4)

    # The test uses a tiny real graph fit from the existing sampler contract.
    from test_bff_sampler import _collinear_fit

    fit = _collinear_fit(seed=3)
    seen = []
    result = sampler_bff.sample_via_graph(
        fit,
        fit.model,
        "metropolis",
        steps=8,
        n_adapt=0,
        blocks=[[0, 1, 2]],
        seed=13,
        callback=lambda done, total: seen.append((done, total)),
    )

    assert result is not None
    assert seen
    assert len(calls) == 1  # only the final public result


def test_result_callback_schema_and_values_remain_unchanged():
    from test_bff_sampler import _collinear_fit

    fit = _collinear_fit(seed=4)
    partial = []

    def callback(done, total, result=None):
        partial.append((done, total, result))

    result = sampler_bff.sample_via_graph(
        fit,
        fit.model,
        "metropolis",
        steps=8,
        n_adapt=0,
        blocks=[[0, 1, 2]],
        seed=14,
        substeps=4,
        callback=callback,
    )

    assert result is not None
    assert partial
    done, total, item = partial[-1]
    assert done == total == 8
    assert item is not None
    assert item["parameter_values"].shape == (done, fit.model.n_free)
    np.testing.assert_allclose(item["parameter_values"], result["parameter_values"])


@pytest.mark.parametrize("kind", ["builtin", "callable", "partial", "varargs", "keyword_only"])
def test_callback_signature_shapes_do_not_materialize_or_drop_progress(monkeypatch, kind):
    from test_bff_sampler import _collinear_fit

    fit = _collinear_fit(seed=5)
    seen = []
    if kind == "builtin":
        callback = operator.add
        seen.append(True)  # operator.add is a builtin two-argument callable.
    elif kind == "callable":

        class Callable:
            def __call__(self, done, total):
                seen.append((done, total))

        callback = Callable()
    elif kind == "partial":
        callback = partial(lambda prefix, done, total: seen.append((prefix, done, total)), "p")
    elif kind == "varargs":

        def callback(*args, **kwargs):
            seen.append((args, kwargs))
    else:

        def callback(done, total, *, result=None):
            seen.append(result is not None)

    sampler_bff.sample_via_graph(
        fit,
        fit.model,
        "metropolis",
        steps=4,
        n_adapt=0,
        blocks=[[0, 1, 2]],
        seed=15,
        substeps=2,
        callback=callback,
    )
    assert seen


def test_type_error_inside_callback_is_not_swallowed():
    from test_bff_sampler import _collinear_fit

    fit = _collinear_fit(seed=6)

    def callback(done, total):
        raise TypeError("callback body sentinel")

    with pytest.raises(TypeError, match="callback body sentinel"):
        sampler_bff.sample_via_graph(
            fit,
            fit.model,
            "metropolis",
            steps=4,
            n_adapt=0,
            blocks=[[0, 1, 2]],
            seed=16,
            substeps=2,
            callback=callback,
        )


def test_opaque_native_two_argument_callback_remains_compatible():
    """Opaque native progress callbacks accept the legacy two-argument call."""
    from test_bff_sampler import _collinear_fit

    fit = _collinear_fit(seed=7)

    class Callback:
        @property
        def __signature__(self):
            """Keep the native callback opaque across NumPy versions."""
            raise ValueError("opaque signature")

        __call__ = np.add

    result = sampler_bff.sample_via_graph(
        fit,
        fit.model,
        "metropolis",
        steps=4,
        n_adapt=0,
        blocks=[[0, 1, 2]],
        seed=17,
        substeps=2,
        callback=Callback(),
    )

    assert result is not None
    assert result["parameter_values"].shape == (4, fit.model.n_free)


def test_opaque_python_callback_body_type_error_is_not_retried():
    """An opaque Python callback's body error preserves single-call side effects."""
    from test_bff_sampler import _collinear_fit

    fit = _collinear_fit(seed=8)
    seen = []

    class Callback:
        @property
        def __signature__(self):
            """Reject signature inspection to exercise opaque dispatch."""
            raise ValueError("opaque signature")

        def __call__(self, done, total, result=None):
            """Record the call before raising the callback's own error."""
            seen.append((done, total))
            raise TypeError("opaque callback body sentinel")

    with pytest.raises(TypeError, match="opaque callback body sentinel"):
        sampler_bff.sample_via_graph(
            fit,
            fit.model,
            "metropolis",
            steps=4,
            n_adapt=0,
            blocks=[[0, 1, 2]],
            seed=18,
            substeps=2,
            callback=Callback(),
        )

    assert seen == [(2, 4)]
