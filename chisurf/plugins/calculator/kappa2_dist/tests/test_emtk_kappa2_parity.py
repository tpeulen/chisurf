"""The native κ² calculator at parity with the Qt Kappa2Dist.

The model is the committed Qt tool's ``_Kappa2DistModel`` moved to ``gui/model.py``
unchanged (method diff: ``okf/plugins/emtk-ports/kappa2_dist/model_diff_vs_head.txt``);
the form is the Qt tool's spec (``k2dist.view.json``). The results are Monte-Carlo
(seeded from numpy), so they are compared under one seed.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.calculator.kappa2_dist.gui.app import make_app

HERE = Path(__file__).parent
PLUGIN = HERE.parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
PICTOGRAM = re.compile("[\U0001f000-\U0001ffff☀-➿️]")


def _draw(app, size=(1200, 800), times=2):
    painter = RecordingPainter()
    for _ in range(times):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def _settle(app, timeout=60.0):
    end = time.monotonic() + timeout
    _draw(app, times=1)
    while (app.tool.busy or getattr(app.tool, "dirty", False)) and time.monotonic() < end:
        time.sleep(0.01)
        _draw(app, times=1)
    assert not app.tool.busy


# 1. the app computes what the Qt model computes, for the same seed
def test_results_equal_the_qt_model_under_one_seed():
    from chisurf.plugins.calculator.kappa2_dist.backend.services import _kappa2_compute_handler
    from chisurf.plugins.calculator.kappa2_dist.gui.model import _Kappa2DistModel

    app = make_app()
    app.tool._model.model_type = "diffusion"
    app.tool._model.fret_efficiency = 0.4
    np.random.seed(7)
    app.kappa2_gui.on_compute()
    _settle(app)
    reference = _Kappa2DistModel()
    reference.model_type, reference.fret_efficiency = "diffusion", 0.4
    np.random.seed(7)
    reference.compute(SimpleNamespace(compute=_kappa2_compute_handler))
    m = app.tool._model
    for field in ("k2_mean", "k2_sd", "Rapp_mean", "RappSD", "delta_deg"):
        assert getattr(m, field) == pytest.approx(getattr(reference, field)), field
    np.testing.assert_allclose(m._k2hist, reference._k2hist)


# 2. an edit during a computation is not lost
def test_an_edit_while_computing_is_computed_too(monkeypatch):
    from chisurf.plugins.calculator.kappa2_dist.backend import services

    runs = []
    original = services._kappa2_compute_handler
    monkeypatch.setattr(
        services,
        "_kappa2_compute_handler",
        lambda *a, **k: (
            runs.append(k.get("kappa2_true", a[-1] if a else None)),
            original(*a, **k),
        )[1],
    )
    app = make_app()  # one computation on construction
    _settle(app)
    app.kappa2_gui.on_compute()  # a run is in flight
    assert app.tool.busy
    app.tool._model.kappa2_true = 1.5  # the user edits meanwhile
    app.kappa2_gui.on_edit()
    _settle(app)
    assert app.tool._model.kappa2_true == 1.5  # the edit survived the arriving result
    assert app.tool.dirty is False
    assert len(runs) == 3  # construction, the run in flight, the edit


# 3. the form is the Qt tool's spec: radio labels, every field described
def test_the_form_is_the_qt_spec():
    app = make_app()
    painter = _draw(app)
    # the model choice shows the Qt labels (a combo here: the radio row did not fit a narrow dock)
    for label in ("WIC (Cone)", "r₀ (fund.)", "r_AD known (use δ)"):
        assert label in painter.strings, label
    choice = next(
        s
        for p in app.kappa2_gui.input_spec["sections"]
        for s in p.get("sections", [])
        if s.get("type") == "choice"
    )
    assert (
        choice["labels"] == ["WIC (Cone)", "DWT (Diffusion)", "Isotropic"] and "style" not in choice
    )
    assert [s for s in painter.strings if PICTOGRAM.search(s)] == []
    spec = json.loads((PLUGIN / "k2dist.view.json").read_text(encoding="utf-8"))

    def walk(sections):
        for s in sections:
            if s.get("type") in ("value", "choice", "toggle"):
                assert s.get("description"), s.get("attr")
            walk(s.get("sections", []))

    # the input panels the app draws; the read-only Results values are the statistics table
    walk([s for s in spec["sections"] if s.get("title") != "Results"])


def test_the_true_kappa2_marker_is_a_legend_entry():
    app = make_app()
    _settle(app)
    painter = _draw(app)
    assert any(s.startswith("true κ² = ") for s in painter.strings)


@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws(size):
    app = make_app()
    _settle(app)
    painter = _draw(app, size)
    assert "Mean κ²" in painter.strings and "Compute" in painter.strings


def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("kappa2_dist")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    assert emtk_inventory(build_emtk_app("kappa2_dist"))["controls_without_tooltip"] == []
