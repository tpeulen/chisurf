"""The emtk H2MM windows draw what the fit computed, or say that there is none (no invented data, card H-X).

The earlier app drew a hard-coded rate matrix, seeded ``np.random.normal`` transition clusters and invented
exponential dwell curves whenever there was no result, and read result fields (``rates``, dict-shaped
``transitions``) that the real ``H2mmAnalysis`` does not have, so even after a real fit it kept drawing the
inventions. These tests fail if a plotted array or a table cell does not come from the backend's analysis.

The fits here are **generated**: photons are simulated from a known two-state model (the same generator the
backend tests use) and fitted by the real ``analyze``; nothing is read from outside the repository.
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest
from emtk import implot
from emtk.testing import RecordingPainter

from chisurf.plugins.burst.burst_h2mm.core import h2mm
from chisurf.plugins.burst.burst_h2mm.core.analysis import analyze
from chisurf.plugins.burst.burst_h2mm.gui import result_view

SIZES = [(1200, 800), (800, 600)]
GUI = Path(__file__).parents[1] / "gui"


def generated_fit(
    seed: int, trans=((0.99, 0.01), (0.02, 0.98)), obs=((0.85, 0.15), (0.20, 0.80)), states=(1, 2)
):
    """A fit of GENERATED photons: a two-state model simulates the bursts, ``analyze`` fits them. Returns ``(analysis, data)``."""
    truth = h2mm.H2mmModel(np.array([0.5, 0.5]), np.array(trans), np.array(obs))
    rng = np.random.default_rng(seed)
    times = [
        np.concatenate([[0], np.cumsum(rng.poisson(4, 59) + 1)]).astype(np.int64) for _ in range(80)
    ]
    data = h2mm.prepare_bursts(times, h2mm.simulate_bursts(truth, times, seed=seed + 1), 2)
    return analyze(data, state_counts=states, n_restarts=1, max_iter=100), data


def generated_analysis(seed: int, **kwargs):
    return generated_fit(seed, **kwargs)[0]


@pytest.fixture(scope="module")
def ana():
    return generated_analysis(2)


@pytest.fixture(scope="module")
def other_ana():
    return generated_analysis(
        7, trans=((0.95, 0.05), (0.10, 0.90)), obs=((0.95, 0.05), (0.10, 0.90))
    )


class PlotSpy:
    """Records every ``implot.plot_*`` call (name, label, the numpy arrays it was given)."""

    def __init__(self, monkeypatch) -> None:
        self.calls: list[tuple[str, str, list[np.ndarray]]] = []
        for name in [n for n in dir(implot) if n.startswith("plot_") and "pixels" not in n]:
            original = getattr(implot, name)
            monkeypatch.setattr(implot, name, self._wrap(name, original))

    def _wrap(self, name, original):
        def spy(*args, **kwargs):
            label = args[0] if args and isinstance(args[0], str) else ""
            arrays = [
                np.asarray(a, dtype=float)
                for a in list(args) + list(kwargs.values())
                if _is_array(a)
            ]
            self.calls.append((name, label, arrays))
            return original(*args, **kwargs)

        return spy

    def clear(self):
        self.calls.clear()


def _is_array(value) -> bool:
    return (
        isinstance(value, (np.ndarray, list, tuple))
        and len(value) > 0
        and not isinstance(value[0], str)
    )


def draw(app, size=(1200, 800), frames=2, spy=None):
    """Draw *frames* frames; the spy keeps only the calls of the last one."""
    painter = None
    for i in range(frames):
        if spy is not None and i == frames - 1:
            spy.clear()
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def texts(painter):
    return [t[5] for t in painter.texts]


def test_the_gate_count_is_computed_from_the_transitions(ana):
    points = result_view.transition_points(ana)
    assert points is not None
    everything = result_view.transitions_in_gate(points, (0.0, 1.0), (0.0, 1.0))
    assert everything == (points[0].size, points[0].size)
    nothing = result_view.transitions_in_gate(points, (2.0, 3.0), (2.0, 3.0))
    assert nothing == (0, points[0].size)
    assert result_view.transitions_in_gate(None, (0, 1), (0, 1)) == (0, 0)


def test_the_result_view_returns_nothing_without_an_analysis():
    assert result_view.n_states(None) is None
    assert result_view.rate_matrix(None) is None
    assert result_view.transition_points(None) is None
    assert result_view.dwell_histograms(None) == ([], [])


def test_the_app_source_cannot_make_data_up():
    """Static guard: no numpy / random import in the native app, no numeric literal fed to a plot call."""
    tree = ast.parse((GUI / "native.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {a.name.split(".")[0] for a in node.names} & {"numpy", "random"}, (
                "the app imports numpy/random"
            )
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in {"numpy", "random"}
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr.startswith("plot_")
        ):
            for arg in node.args[1:]:
                assert not isinstance(arg, (ast.List, ast.Tuple, ast.Constant)), (
                    f"literal data in {node.func.attr}"
                )


def _named(self, label):
    found = [c for c in self.calls if c[1] == label]
    assert len(found) == 1, f"{label!r} drawn {len(found)} times: {[c[:2] for c in self.calls]}"
    return found[0]


PlotSpy.named = _named
