"""The fit Info plot's visible contents are drawn by emtk, not Qt.

The fit window's plot surface is emtk (FitPlotsArea, the chiplot emtk
backend). The Info page was the last plot page whose visible content was
still a classic Qt widget: a white read-only ``QPlainTextEdit`` pasted into
the dark emtk window. The report and the mmCIF preview are emtk's
``TextEditor`` now, and the view that wraps it is no widget either: the fit
window's surface draws the report, the *Plot settings* dock the preview.
"""

from __future__ import annotations

import importlib.util

import numpy as np
import pytest

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
    """The view is emtk's read-only TextEditor, and no Qt widget."""
    from emtk.widgets.text_editor import TextEditor
    from qtpy import QtWidgets

    view = EmtkTextView()
    view.setPlainText("drawn by emtk")
    assert isinstance(view.editor, TextEditor)
    assert view.editor.config.read_only is True
    assert not isinstance(view, QtWidgets.QWidget)
    asked = []
    view.set_refresh_target(lambda: asked.append(1))
    view.setPlainText("again")
    assert asked, "a new text must ask for a frame"


@pytest.mark.skipif(not HAVE_EMTK, reason="emtk not importable")
def test_the_info_page_is_no_widget_and_draws_its_report(plain_fit, qapp):
    """The page body is the report editor; nothing on the page is Qt."""
    from qtpy import QtWidgets

    from chisurf.gui.plots.emtk_page import page_body
    from chisurf.gui.plots.fitinfo import FitInfo

    info = FitInfo(plain_fit)
    assert not isinstance(info, QtWidgets.QWidget)
    body = page_body(info)
    assert body.control is info.textedit.editor and body.missing == []
    assert info.textedit in body.refreshables


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


@pytest.mark.skipif(not HAVE_EMTK, reason="emtk not importable")
def test_metadata_rows_write_through_and_keep_the_picked_row(plain_fit, qapp):
    """A typed value and a catalogue key reach the fit; the reload keeps the pick."""
    from chisurf.gui.plots.fitinfo import FitInfo

    plain_fit.flr_metadata = {"pH": "7.4"}
    info = FitInfo(plain_fit)
    rows = info.metadata_editor
    rows.add_row()
    picked = rows.selected_row
    rows.detail_key = "_flr_sample.details"
    assert rows.selected_row == picked, "the page's reload must not drop the picked row"
    rows.edited(rows._selected(), "value", "20 mM Tris")
    assert plain_fit.flr_metadata == {"pH": "7.4", "_flr_sample.details": "20 mM Tris"}
    rows.delete_row()
    assert plain_fit.flr_metadata == {"pH": "7.4"}


@pytest.mark.skipif(not HAVE_EMTK, reason="emtk not importable")
def test_dropped_files_become_external_references(plain_fit, qapp):
    from chisurf.gui.plots.fitinfo import FitInfo

    info = FitInfo(plain_fit)
    info.on_paths_dropped(["/data/run1.ptu", "/data/irf.csv"])
    assert info.TABS[info.tabs.current] == "External data"
    streams = [(s["file_path"], s["file_format"]) for s in plain_fit.flr_photon_streams]
    assert streams == [("/data/run1.ptu", "ptu"), ("/data/irf.csv", "csv")]


@pytest.mark.skipif(not HAVE_EMTK, reason="emtk not importable")
def test_the_settings_tabs_draw_every_control(plain_fit, qapp):
    """All four tabs of the analysis record render in the Plot-settings dock."""
    from chisurf.gui.plots.emtk_settings import PlotSettingsHost
    from chisurf.gui.plots.fitinfo import FitInfo

    info = FitInfo(plain_fit)
    host = PlotSettingsHost()
    host.resize(440, 640)
    host.show_page(info)
    host.show()
    for tab in range(len(info.TABS)):
        info.tabs.select(tab)
        for _ in range(3):
            qapp.processEvents()
            host.host.repaint()
    drawn = set(info.settings_form.rects)
    assert {"metadata_rows", "detail_key", "add_row", "delete_row", "external_rows",
            "export_full_preview", "export_copy", "export_save"} <= drawn
    host.close()
