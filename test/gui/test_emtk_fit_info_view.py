"""The fit Info plot's visible contents are drawn by emtk, not Qt.

The fit window's plot surface is emtk (FitPlotsArea, the chiplot emtk
backend). The Info page was the last plot page whose visible content was
still a classic Qt widget: a white read-only ``QPlainTextEdit`` pasted into
the dark emtk window. The report and the mmCIF preview are drawn by emtk's
``TextEditor`` now, hosted like every other emtk surface; the Qt fallback
exists only for an environment where emtk cannot be imported.
"""

from __future__ import annotations

import importlib.util

import numpy as np
import pytest
from qtpy import QtWidgets

from chisurf.gui.plots.emtk_text_view import EmtkTextView

HAVE_EMTK = importlib.util.find_spec("emtk") is not None


@pytest.fixture()
def plain_fit(qapp):
    """A minimal single fit, the same recipe test_mfd_surface uses."""
    import chisurf.core.data
    import chisurf.core.models.parse
    from chisurf.core.fitting.fit import Fit

    x = np.linspace(0.0, 5.0, 32)
    return Fit(
        model_class=chisurf.core.models.parse.ParseModel,
        data=chisurf.core.data.DataCurve(x=x, y=x**2, ey=np.ones_like(x)),
    )


def test_text_view_round_trips_text(qapp):
    view = EmtkTextView()
    view.setPlainText("chi2r=1.02\nrange=5..90")
    assert view.toPlainText() == "chi2r=1.02\nrange=5..90"
    view.setPlainText("replaced")
    assert view.toPlainText() == "replaced"


@pytest.mark.skipif(not HAVE_EMTK, reason="emtk not importable")
def test_text_view_draws_with_emtk(qapp):
    """The visible surface is emtk's read-only TextEditor, not a Qt editor."""
    from emtk.widgets.text_editor import TextEditor

    view = EmtkTextView()
    view.setPlainText("drawn by emtk")
    assert isinstance(view._editor, TextEditor)
    assert view._editor.config.read_only is True
    assert view._host is not None
    assert not isinstance(view._host, QtWidgets.QPlainTextEdit)


@pytest.mark.skipif(not HAVE_EMTK, reason="emtk not importable")
def test_fit_info_report_is_drawn_by_emtk(plain_fit, qapp):
    """The Info page's report is an emtk view with the old text contract."""
    from chisurf.gui.plots.fitinfo import FitInfo

    info = FitInfo(plain_fit)
    assert isinstance(info.textedit, EmtkTextView)
    info.update()
    text = info.textedit.toPlainText()
    assert str(plain_fit) in text


@pytest.mark.skipif(not HAVE_EMTK, reason="emtk not importable")
def test_cif_preview_is_drawn_by_emtk(plain_fit, qapp):
    """The Export tab's mmCIF preview is an emtk view too."""
    from chisurf.gui.plots.fitinfo import FitInfo

    info = FitInfo(plain_fit)
    assert isinstance(info.cif_preview, EmtkTextView)
    info._update_cif_preview(full=False)
    assert isinstance(info.cif_preview.toPlainText(), str)


def test_mfd_surface_summary_contract_still_holds(plain_fit, qapp):
    """The existing readers of ``textedit`` keep their text."""
    from chisurf.gui.plots.fitinfo import FitInfo

    info = FitInfo(plain_fit)
    info.update()
    text = info.textedit.toPlainText()
    assert isinstance(text, str)
    assert "--- Analysis:" in text
