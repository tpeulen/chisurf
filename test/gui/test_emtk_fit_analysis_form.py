"""The fit Info page's Analysis tab is drawn by emtk, not classic Qt.

The report and the mmCIF preview already render through emtk
(`test_emtk_fit_info_view`). The Analysis tab beneath them was still a
``QFormLayout`` of ``QLineEdit``/``QComboBox``/``QPlainTextEdit`` -- the last
classic Qt controls on the page. This pins the emtk port: one emtk form
(editable sample combo, two single-line fields, two multi-line detail
editors) drawn in the *Plot settings* dock's Analysis tab, writing through
the same ``_on_changed`` contract the Qt widgets fed.
"""

from __future__ import annotations

import importlib.util

import numpy as np
import pytest

HAVE_EMTK = importlib.util.find_spec("emtk") is not None

pytestmark = pytest.mark.skipif(not HAVE_EMTK, reason="emtk not importable")


@pytest.fixture()
def info(qapp):
    """A FitInfo over a minimal fit, the same recipe the info-view test uses."""
    import chisurf.core.data
    import chisurf.core.models.parse
    from chisurf.core.fitting.fit import Fit
    from chisurf.gui.plots.fitinfo import FitInfo

    x = np.linspace(0.0, 5.0, 32)
    fit = Fit(
        model_class=chisurf.core.models.parse.ParseModel,
        data=chisurf.core.data.DataCurve(x=x, y=x**2, ey=np.ones_like(x)),
    )
    yield FitInfo(fit)


def test_analysis_tab_is_an_emtk_form(info):
    from chisurf.gui.plots.emtk_analysis_form import EmtkAnalysisForm

    assert isinstance(info.analysis_form, EmtkAnalysisForm)
    assert "analysis_form" in info.settings_form.custom
    assert info.tabs.titles[0] == "Analysis"


def test_sample_typing_updates_the_uuid_line(info, qapp):
    qapp.processEvents()
    info.sample_type("S3")
    assert info.sample_uuid_label.text(), "a new sample id gets a UUID"
    assert info.method_value() == "ParseModel", "the model hint prefills"
    info.method_type("mfm")
    assert info.method_value() == "mfm"
    info.sample_details_type("20 mM Tris")
    info.condition_details_type("pH=7.4; T=293.15 K")
    assert info.sample_details_value() == "20 mM Tris"
    assert info.condition_details_value() == "pH=7.4; T=293.15 K"


def test_qt_api_surface_still_serves_readers(info, qapp):
    """Every reader of the old attributes finds the same call surface."""
    qapp.processEvents()
    info.sample_combo.setEditText("from-qt-code")
    assert info.sample_value() == "from-qt-code"
    info.method_edit.setText("over-the-top")
    assert info.method_value() == "over-the-top"
    info.sample_details_edit.setPlainText("details")
    assert info.sample_details_value() == "details"


def test_picking_a_known_sample_from_the_list(info, qapp):
    qapp.processEvents()
    info._populate_sample_combo()
    info.sample_pick(0) if info.sample_count() else None
    # No database here, so the list is empty and nothing may blow up.
    assert info.sample_value() in ("", info.analysis_id)
