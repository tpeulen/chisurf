"""Arriving at the alternation step must leave converted data behind.

The step is declared ``optional``, and the workflow hub never runs an optional step for you, so that walking past a
step cannot silently change the analysis. For µs-ALEX that made **Next skip the conversion**: the burst search then
ran on files whose alternation was still in the macro time, gating on a micro-time of zeros.

So the step converts itself on arrival (:meth:`AlexAlternationModel.set_files`). These pin the two conditions that
make that safe, on the Qt-free model.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from chisurf.plugins.burst.alex_suite.gui import alternation_model
from chisurf.plugins.burst.alex_suite.gui.alternation_model import AlexAlternationModel, needs_conversion


class _Tttr:
    def __init__(self, micro):
        self.micro_times = np.asarray(micro)


def _patch(monkeypatch, micro):
    import chisurf.core.fio.staging as staging

    monkeypatch.setattr(staging, "open_tttr", lambda *_a, **_k: _Tttr(micro))


def test_a_macro_time_alternation_is_converted(monkeypatch):
    """An empty micro-time is what an unfolded µs-ALEX file looks like."""
    _patch(monkeypatch, np.zeros(1000, dtype=int))
    assert needs_conversion(Path("/data/a.sm")) is True


def test_data_that_already_has_a_micro_time_is_left_alone(monkeypatch):
    """PIE data, or a container this step produced earlier: folding it again would overwrite a real micro-time."""
    _patch(monkeypatch, np.arange(1000))
    assert needs_conversion(Path("/data/a.sm")) is False


def test_an_unreadable_file_is_not_converted(monkeypatch):
    """Unknown is not "needs folding": refuse rather than rewrite blindly."""
    import chisurf.core.fio.staging as staging

    def _raise(*_a, **_k):
        raise OSError("no such file")

    monkeypatch.setattr(staging, "open_tttr", _raise)
    assert needs_conversion(Path("/data/missing.sm")) is False


def test_arrival_converts_alex_and_leaves_pie_alone(monkeypatch):
    """Arrival runs the conversion for µs-ALEX data and only reports for PIE data."""
    started = []
    monkeypatch.setattr(AlexAlternationModel, "run", lambda self, convert=True: started.append(convert) or True)
    monkeypatch.setattr(alternation_model, "needs_conversion", lambda _p: True)
    model = AlexAlternationModel()
    model.set_files(["/data/a.sm"])
    assert started == [True] and model.decision == "convert"
    model.set_files(["/data/a.sm"])
    assert started == [True], "the same files arriving again must not run the step again"

    monkeypatch.setattr(alternation_model, "needs_conversion", lambda _p: False)
    pie = AlexAlternationModel()
    pie.set_files(["/data/b.spc"])
    assert started == [True] and pie.decision == "pie"
    assert "already has a micro-time" in pie.status_text
