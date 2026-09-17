"""Offscreen-Qt tests for the reusable ``image_browser`` AutoForm section."""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    try:
        from qtpy import QtWidgets
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"qtpy unavailable: {exc}")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class _BrowserModel:
    """A minimal browsable-image model: three named entries, each an image."""

    def __init__(self):
        self.current = None
        self.selected_ids = []
        self.picked = []
        self.ratings = {}
        self._images = {
            "a": np.zeros((4, 4)),
            "b": np.ones((4, 4)),
            "c": np.full((4, 4), 2.0),
        }

    def browse_entries(self):
        return [
            {"id": "a", "label": "Alpha", "badge": "★", "rating": self.ratings.get("a", 1)},
            {"id": "b", "label": "Beta", "rating": self.ratings.get("b", 0)},
            {"id": "c", "label": "Gamma", "rating": self.ratings.get("c", 0)},
        ]

    def select_entry(self, entry_id):
        self.picked.append(entry_id)

    def current_image(self):
        return self._images.get(self.current)

    def entry_info(self):
        return f"<b>{self.current}</b>"

    def set_rating(self, entry_id, value):
        self.ratings[entry_id] = value

    def view_spec(self):
        import chisurf.core.dataspec as ds

        return ds.ModelView(
            sections=(
                ds.CustomSection(
                    key="image_browser",
                    target="current_image",
                    options={
                        "entries_source": "browse_entries",
                        "entry_attr": "current",
                        "selected_ids_attr": "selected_ids",
                        "select_call": "select_entry",
                        "info_source": "entry_info",
                        "filter": True,
                        "rating_call": "set_rating",
                        "max_rating": 3,
                    },
                ),
            )
        )


def _browser(form):
    from chisurf.gui.autoform.sections.image_browser_section import ImageBrowserWidget

    return form.findChild(ImageBrowserWidget)


def test_browser_populates_and_selects_first(qapp):
    from chisurf.gui.autoform import AutoForm

    model = _BrowserModel()
    form = AutoForm(model)
    browser = _browser(form)
    assert browser is not None
    assert browser._list.count() == 3
    # First entry auto-selected → model current set, select_call fired, canvas drawn.
    assert model.current == "a"
    assert model.picked and model.picked[-1] == "a"


def test_selecting_entry_updates_model_and_canvas(qapp):
    from chisurf.gui.autoform import AutoForm

    model = _BrowserModel()
    form = AutoForm(model)
    browser = _browser(form)

    browser._list.setCurrentRow(2)
    assert model.current == "c"
    assert model.picked[-1] == "c"
    # The canvas re-read the model's current image (all-2s).
    img = browser._canvas._image.getImageItem().image
    assert img is not None and float(np.asarray(img).max()) == 2.0


def test_filter_hides_non_matching_rows(qapp):
    from chisurf.gui.autoform import AutoForm

    model = _BrowserModel()
    form = AutoForm(model)
    browser = _browser(form)

    browser._filter_edit.setText("bet")
    hidden = [browser._list.item(i).isHidden() for i in range(browser._list.count())]
    # Only "Beta" remains visible.
    assert hidden == [True, False, True]


def test_rating_row_writes_through_callback(qapp):
    from chisurf.gui.autoform import AutoForm

    model = _BrowserModel()
    form = AutoForm(model)
    browser = _browser(form)

    browser._list.setCurrentRow(1)  # Beta
    browser._star_buttons[2].click()  # rate 3
    assert model.ratings["b"] == 3
    # Stars reflect the new rating after refresh.
    assert [b.text() for b in browser._star_buttons] == ["★", "★", "★"]


def test_refresh_reloads_entries(qapp):
    from chisurf.gui.autoform import AutoForm

    model = _BrowserModel()
    form = AutoForm(model)
    browser = _browser(form)

    model._images["d"] = np.zeros((4, 4))
    model.browse_entries = lambda: [{"id": "d", "label": "Delta"}]
    form.refresh_plots()
    assert browser._list.count() == 1
    assert browser._list.item(0).text() == "Delta"
