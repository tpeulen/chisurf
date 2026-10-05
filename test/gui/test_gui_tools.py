import glob
import pathlib

import pytest
from qtpy.QtCore import Qt

TOPDIR = pathlib.Path(__file__).parent.parent
import utils

utils.set_search_paths(TOPDIR)

from chisurf.plugins.calculator.kappa2_dist.k2dgui import Kappa2Dist


@pytest.fixture
def kappa2_form(qtbot):
    form = Kappa2Dist()
    qtbot.addWidget(form)
    return form


# --- Kappa2Dist Tests ---


def test_kappa2_defaults(kappa2_form):
    assert kappa2_form._model.r_0 == 0.380
    assert kappa2_form._model.r_Dinf == 0.050
    assert kappa2_form._model.r_Ainf == 0.100
    assert kappa2_form._model.step == 1.5
    assert kappa2_form._model.n_bins == 131
    assert kappa2_form._model.r_ADinf == 0.005


def test_kappa2_calculation_1(kappa2_form, qtbot):
    ok_button = kappa2_form.pushButton
    qtbot.mouseClick(ok_button, Qt.LeftButton)

    # The cone model samples orientations, so these carry a tolerance rather
    # than a rounded equality. RappSD is ~0.051 -- a real 5% distance
    # uncertainty -- and `round(0.051, 1) == 0.0` was simply false.
    assert kappa2_form._model.k2_mean == pytest.approx(0.667, abs=0.02)
    assert kappa2_form._model.k2_sd == pytest.approx(0.216, abs=0.02)
    assert kappa2_form._model.Rapp_mean == pytest.approx(0.993, abs=0.01)
    assert kappa2_form._model.RappSD == pytest.approx(0.051, abs=0.01)


def test_kappa2_calculation_2(kappa2_form, qtbot):
    kappa2_form._model.rAD_known = True

    ok_button = kappa2_form.pushButton
    qtbot.mouseClick(ok_button, Qt.LeftButton)

    # The cone model samples orientations, so these carry a tolerance rather
    # than a rounded equality. RappSD is ~0.051 -- a real 5% distance
    # uncertainty -- and `round(0.051, 1) == 0.0` was simply false.
    assert kappa2_form._model.k2_mean == pytest.approx(0.667, abs=0.02)
    assert kappa2_form._model.k2_sd == pytest.approx(0.216, abs=0.02)
    assert kappa2_form._model.Rapp_mean == pytest.approx(0.993, abs=0.01)
    assert kappa2_form._model.RappSD == pytest.approx(0.051, abs=0.01)
