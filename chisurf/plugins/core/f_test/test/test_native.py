"""Native calculator preserves statistics, fit loading and Qt-free launch."""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from scipy.stats import f

from chisurf.plugins.core.f_test.gui.model import FTestModel


@pytest.mark.parametrize("confidence", [0.5, 0.68, 0.95, 0.99])
def test_native_confidence_threshold_round_trip(confidence):
    model = FTestModel()
    model.edit_field("conf_level", confidence)
    model.recompute_conf()
    assert model.conf_level == pytest.approx(confidence, abs=1e-9)


def test_native_support_plane_threshold():
    model = FTestModel()
    model.chi2_min, model.npars, model.dof = 1.0, 3, 20
    model.edit_field("conf_level_2", 0.95)
    assert model.chi2_max == pytest.approx(1.464758681821117)
    assert model.chi2_max == pytest.approx(1.0 + 3.0 / 20.0 * f.isf(0.05, 3, 20))


def test_native_fit_loading_targets_and_no_files():
    from chisurf.plugins.core.f_test.gui.app import FTestApp

    fit = SimpleNamespace(
        name="Example fit", model=SimpleNamespace(n_points=120, n_free=3), chi2r=1.2
    )
    app = FTestApp(fit_provider=lambda: [fit])
    app.refresh_fits()
    app.tour.start(1)
    assert app.tour.awaiting
    assert app.load_fit_into(0, "model1")
    assert not app.tour.awaiting
    assert (app.model.chi2_1, app.model.n1) == (1.2, 117)
    assert app.load_fit_into(0, "model2")
    assert (app.model.chi2_2, app.model.n2) == (1.2, 117)
    assert app.model.conf_level == pytest.approx(0.5)
    assert app.load_fit_into(0, "chi2max")
    assert (app.model.chi2_min, app.model.npars, app.model.dof) == (1.2, 3, 117)
    assert app.files_dropped(["ignored.ptu"])
    assert "no dropped files" in app.status
    assert not app.load_fit_into(1, "model1")
    assert "No such open fit" in app.status


def test_native_f_test_without_qt():
    script = """
import importlib.abc, sys
class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'}:
            raise RuntimeError('Qt imported: ' + fullname)
sys.meta_path.insert(0, BlockQt())
from chisurf.plugins.core.f_test.gui.app import make_app
app = make_app()
assert app.model.chi2_max > 1
from emtk import im
from emtk.testing import RecordingPainter
app.draw(RecordingPainter(), 0, 0, 950, 950)
assert 'chisurf.gui' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[5],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_fields_render_with_tooltips(monkeypatch):
    from emtk import im
    from emtk.testing import RecordingPainter

    from chisurf.plugins.core.f_test.gui.app import make_app

    app = make_app()
    tips = []
    from emtk import im_widgets

    monkeypatch.setattr(im, "set_item_tooltip", tips.append)
    monkeypatch.setattr(im_widgets, "set_item_tooltip", tips.append)
    box = (0.0, 0.0, 950.0, 950.0)
    app.draw(RecordingPainter(), *box)
    assert set(app.forms[0].rects) >= {"chi2_1", "chi2_2", "n1", "n2", "conf_level"}
    assert set(app.forms[1].rects) >= {"chi2_min", "npars", "dof", "conf_level_2", "chi2_max"}
    assert any("Reduced" in text for text in tips)
    assert any("Number of free" in text for text in tips)


def test_native_fit_registry_flattens_every_group_member(monkeypatch):
    import chisurf
    from chisurf.plugins.core.f_test.gui.app import open_fits

    fit1, fit2 = object(), object()

    class FitGroup(list):
        model = object()
        chi2r = 1.0

    monkeypatch.setattr(chisurf, "fits", [FitGroup([fit1, fit2])])
    assert open_fits() == [fit1, fit2]


def test_native_form_commit_recomputes_confidence_threshold():
    from emtk.view_form import _commit

    from chisurf.plugins.core.f_test.gui.app import make_app

    app = make_app()
    field = next(
        field for field in app.spec["sections"][0]["sections"] if field["attr"] == "conf_level"
    )
    _commit(app.model, field, 0.99, app.forms[0])
    app.model.recompute_conf()
    assert app.model.conf_level == pytest.approx(0.99, abs=1e-9)
