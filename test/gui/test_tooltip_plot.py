"""Tests for the curve previews shown in dataset/fit tooltips.

The previews are painted headlessly into a ``QPixmap`` and embedded as base64
PNGs, so everything here runs without a display. The behaviour that matters and
is easy to break: rendering must be *lazy* (a list of hundreds of curves must not
paint hundreds of thumbnails while populating) and it must degrade to the plain
file name when the preview is switched off in the settings or the row carries no
curve.
"""

import numpy as np
import pytest
from qtpy import QtCore, QtWidgets


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def _decay(n=1024):
    x = np.arange(n, dtype=float) * 0.032
    y = 1e4 * np.exp(-x / 2.5) + 1.0
    return x, y


def test_render_curve_thumbnail_is_a_png_img(qapp):
    """A curve renders to an inline base64 PNG of the requested size."""
    from chisurf.gui.widgets.tooltip_plot import render_curve_thumbnail

    html = render_curve_thumbnail(*_decay(), width=220, height=120)
    assert html.startswith('<img src="data:image/png;base64,')
    assert 'width="220"' in html and 'height="120"' in html
    assert len(html) > 500, "the PNG payload looks empty"


def test_render_series_thumbnail_needs_data(qapp):
    """Empty or single-point series render nothing rather than crashing."""
    from chisurf.gui.widgets.tooltip_plot import render_series_thumbnail

    assert render_series_thumbnail([]) == ""
    assert render_series_thumbnail([([1.0], [2.0], "#fff")]) == ""
    assert render_series_thumbnail([([], [], "#fff")]) == ""


def test_non_finite_samples_are_dropped(qapp):
    """NaN/inf samples must not poison the axis range (the curve still draws)."""
    from chisurf.gui.widgets.tooltip_plot import render_curve_thumbnail

    x, y = _decay(64)
    y[3] = np.nan
    y[7] = np.inf
    assert render_curve_thumbnail(x, y).startswith("<img")


def test_log_scale_chosen_for_decays(qapp):
    """A multi-decade decay is drawn logarithmically, a flat curve linearly."""
    from chisurf.gui.widgets.tooltip_plot import _prefers_log

    assert _prefers_log(_decay()[1])
    assert not _prefers_log(np.linspace(1.0, 2.0, 100))


def test_curve_tooltip_html_has_title_and_plot(qapp):
    """The tooltip is the file name in bold above the curve image."""
    from chisurf.gui.widgets.tooltip_plot import curve_tooltip_html

    x, y = _decay()
    html = curve_tooltip_html("/data/experiment/decay_1.dat", x, y)
    assert html.startswith("<b>")
    assert "decay_1.dat" in html
    assert '<img src="data:image/png;base64,' in html


def test_curve_tooltip_falls_back_to_plain_name(qapp, monkeypatch):
    """With gui.tooltip.curve_preview.enabled false the tooltip is plain text."""
    import chisurf.gui.tooltip as tooltip
    from chisurf.gui.widgets import tooltip_plot

    monkeypatch.setattr(
        tooltip,
        "curve_preview_config",
        lambda: {"enabled": False, "width": 300, "height": 140},
    )
    html = tooltip_plot.curve_tooltip_html("/data/decay_1.dat", *_decay())
    assert "<img" not in html
    assert "decay_1.dat" in html


def test_curve_tooltip_without_curve_is_plain_name(qapp):
    """Rows that carry no curve (e.g. a global dataset) still show their name."""
    from chisurf.gui.widgets.tooltip_plot import curve_tooltip_html, dataset_tooltip_html

    assert "<img" not in curve_tooltip_html("Global Dataset")
    assert "<img" not in dataset_tooltip_html(object())


def test_tooltip_items_render_once_and_cache(qapp):
    """Tree/list/model items paint the preview on first hover only."""
    from chisurf.gui.widgets.tooltip_plot import (
        TooltipListItem,
        TooltipStandardItem,
        TooltipTreeItem,
    )

    tree = QtWidgets.QTreeWidget()
    tree.setColumnCount(3)
    calls = []
    item = TooltipTreeItem(
        tree, ["0", "decay", "TCSPC"], key="k", render_fn=lambda k: calls.append(k) or "<b>k</b>"
    )
    # Only the name column carries the tooltip; the others fall through to Qt.
    assert item.data(1, QtCore.Qt.ToolTipRole) == "<b>k</b>"
    assert item.data(1, QtCore.Qt.ToolTipRole) == "<b>k</b>"
    assert calls == ["k"], "render_fn must be called once and cached"
    assert item.text(1) == "decay"

    for cls in (TooltipListItem, TooltipStandardItem):
        seen = []
        obj = cls("decay", "key", lambda k: seen.append(k) or "tip")
        assert obj.data(QtCore.Qt.ToolTipRole) == "tip"
        assert obj.data(QtCore.Qt.ToolTipRole) == "tip"
        assert seen == ["key"], f"{cls.__name__} must cache its tooltip"


def test_tooltip_item_survives_a_failing_renderer(qapp):
    """A renderer that raises must not break the item view."""
    from chisurf.gui.widgets.tooltip_plot import TooltipTreeItem

    tree = QtWidgets.QTreeWidget()
    tree.setColumnCount(2)

    def boom(_key):
        raise RuntimeError("no data")

    item = TooltipTreeItem(tree, ["0", "bad"], key=None, render_fn=boom)
    assert item.data(1, QtCore.Qt.ToolTipRole) == ""


def test_dataset_tooltip_uses_meta_data_filename(qapp):
    """The heading prefers the recorded file name over the display name."""
    from chisurf.gui.widgets.tooltip_plot import dataset_title

    class _DS:
        name = "decay"
        filename = "No file"
        meta_data = {"filename": "/data/raw/decay_1.dat"}

    assert dataset_title(_DS()) == "/data/raw/decay_1.dat"

    class _DS2:
        name = "decay"
        filename = "/data/decay_2.dat"
        meta_data = {}

    assert dataset_title(_DS2()) == "/data/decay_2.dat"

    class _DS3:
        name = "Global Dataset"
        filename = "None"
        meta_data = None

    assert dataset_title(_DS3()) == "Global Dataset"


def test_dataset_selector_rows_carry_a_curve_tooltip(qapp):
    """The shared curve list (dataset list, IRF/background selectors) previews rows."""
    import types

    import chisurf.core.data
    from chisurf.gui.widgets.experiments.widgets import ExperimentalDataSelector

    x, y = _decay()
    d = chisurf.core.data.DataCurve(x=x, y=y, filename="/data/decay_1.dat")
    d.name = "/data/decay_1.dat"
    d.experiment = types.SimpleNamespace(name="TCSPC")

    selector = ExperimentalDataSelector(get_data_sets=lambda **kw: [d])
    selector.update()
    item = selector.topLevelItem(0)
    tooltip = item.data(1, QtCore.Qt.ToolTipRole)
    assert tooltip.startswith("<b>/data/decay_1.dat</b>")
    assert '<img src="data:image/png;base64,' in tooltip
    # The other columns keep Qt's default (no tooltip).
    assert not item.data(0, QtCore.Qt.ToolTipRole)


def test_fit_tooltip_shows_data_and_model(qapp, monkeypatch):
    """The fit list previews data plus model, and degrades in server mode."""
    import chisurf
    from chisurf.gui.widgets.fitting.fit_list import ModelDataRepresentationSelector
    from chisurf.gui.widgets.tooltip_plot import fit_tooltip_html

    x, y = _decay()

    class _Curve:
        def __init__(self, x, y):
            self.x, self.y = x, y

    fit = type(
        "_Fit",
        (),
        {
            "name": "fit of decay_1",
            "data": _Curve(x, y),
            "model": _Curve(x, y * 0.98),
            "unique_identifier": "uid-1",
        },
    )()
    html = fit_tooltip_html(fit)
    assert html.startswith("<b>fit of decay_1</b>")
    assert '<img src="data:image/png;base64,' in html

    monkeypatch.setattr(chisurf, "fits", [fit], raising=False)
    dto = {"uid": "uid-1", "name": "fit of decay_1", "dataset_name": "decay_1"}
    assert "<img" in ModelDataRepresentationSelector._fit_tooltip(dto)
    # A fit that lives in a remote process has no curves here: plain name.
    remote = {"uid": "uid-remote", "name": "remote fit", "dataset_name": "decay_2"}
    assert ModelDataRepresentationSelector._fit_tooltip(remote) == "remote fit"


def test_spectra_thumbnail_reuses_the_shared_renderer(qapp):
    """The spectra tooltip is built on the same painter as the curve preview."""
    from chisurf.gui.widgets.spectra_tooltip import render_spectra_thumbnail

    wl = list(np.linspace(400, 700, 64))

    class _Adapter:
        def get_probe_spectrum(self, probe_id, kind):
            if kind == "transmission":
                return None
            return wl, list(np.exp(-((np.asarray(wl) - 520) ** 2) / 800.0))

    html = render_spectra_thumbnail(1, _Adapter())
    assert html.startswith('<img src="data:image/png;base64,')
    assert render_spectra_thumbnail(1, None) == ""
