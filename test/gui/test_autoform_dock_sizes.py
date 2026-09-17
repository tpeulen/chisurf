"""A dock area must get the split the view spec asked for.

``sizes`` was applied while the splitter was still ~100 px wide, so every share
clamped to the children's minimum widths and the ratio was lost — an authored
26/74 came out 50/50 in every view that asked for one, silently. These tests pin
the ratio on the real geometry, and pin that a user's saved arrangement still
wins over it.
"""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SPEC = {
    "sections": [
        {
            "type": "dock_area",
            "title": "Docks",
            "split": "horizontal",
            "sizes": [25, 75],
            "sections": [
                {
                    "type": "panel",
                    "title": "Controls",
                    "dock_group": "controls",
                    "sections": [
                        {"type": "value", "attr": "value", "label": "Value", "kind": "float"}
                    ],
                },
                {
                    "type": "plot",
                    "title": "Result",
                    "dock_group": "result",
                    "source": "series",
                },
            ],
        }
    ]
}


class _Model:
    """Minimal model: one bound field and one plot source."""

    def __init__(self) -> None:
        self.value = 1.0

    def view_spec(self):
        """Return the spec under test."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(SPEC)

    def series(self):
        """Return one flat series so the plot panel has something to draw."""
        return [{"x": [0.0, 1.0], "y": [0.0, 1.0], "name": "s"}]


@pytest.fixture(scope="module")
def qapp():
    try:
        from qtpy import QtWidgets
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"qtpy unavailable: {exc}")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _build(qapp, spec=None, width=1000):
    from qtpy import QtCore, QtWidgets

    from chisurf.gui.autoform import AutoForm

    model = _Model()
    if spec is not None:
        model.view_spec = lambda: __import__(
            "chisurf.core.dataspec", fromlist=["load_view_spec"]
        ).load_view_spec(spec)
    form = AutoForm(model)
    form.resize(width, 600)
    form.show()
    qapp.processEvents()
    # The authored ratio is applied on the event loop, once the splitter has a
    # real width — so a test that never spins it measures the pre-layout state.
    QtCore.QCoreApplication.sendPostedEvents()
    qapp.processEvents()
    splitters = form.findChildren(QtWidgets.QSplitter)
    return form, splitters


def test_authored_sizes_survive_the_first_layout(qapp):
    _form, splitters = _build(qapp)
    assert splitters, "the dock area must have split into two groups"
    sizes = splitters[0].sizes()
    assert len(sizes) == 2
    fraction = sizes[0] / sum(sizes)
    assert 0.18 < fraction < 0.34, f"expected ~25 % for the controls, got {sizes}"


def test_without_authored_sizes_the_split_is_even(qapp):
    spec = json.loads(json.dumps(SPEC))
    del spec["sections"][0]["sizes"]
    _form, splitters = _build(qapp, spec)
    sizes = splitters[0].sizes()
    assert abs(sizes[0] - sizes[1]) <= max(4, 0.1 * sum(sizes))


def test_a_persisted_arrangement_wins_over_the_authored_one(qapp, tmp_path, monkeypatch):
    """The deferred pass must stand down for a user's own saved layout."""
    from qtpy import QtCore

    import chisurf.gui.misc_helpers as helpers

    # ``_persist_settings`` imports this lazily from the helpers module, so that
    # is where the redirect has to land.
    monkeypatch.setattr(helpers, "get_plugin_settings_path", lambda key: tmp_path / f"{key}.ini")
    spec = json.loads(json.dumps(SPEC))
    spec["sections"][0]["persist"] = "autoform_dock_sizes_test"

    # First run: the user widens the control column, and that is what gets saved.
    form, splitters = _build(qapp, spec)
    area = splitters[0].parentWidget()
    while area is not None and not hasattr(area, "get_layout_state"):
        area = area.parentWidget()
    assert area is not None, "the splitter must live inside the dock area"

    splitters[0].setSizes([700, 300])
    qapp.processEvents()
    area._save_persisted_layout()
    QtCore.QCoreApplication.sendPostedEvents()
    assert area._persist_settings().value("dock_layout"), "the layout must have been saved"

    # Second run: the authored 25/75 must not overwrite it.
    _form2, splitters2 = _build(qapp, spec)
    sizes = splitters2[0].sizes()
    assert sizes[0] / sum(sizes) > 0.4, "the saved arrangement must not be overwritten"
