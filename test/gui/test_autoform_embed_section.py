"""The AutoForm ``embed`` section: construct a widget, or adopt an existing one.

Constructing was all it could do, which is the wrong half for the case that
prompted the other: a panel loaded from a ``.ui`` file. Its widgets are built by
``uic``, wired by ``objectName`` and referenced from a dozen places, so a second
freshly-constructed copy is not the panel — it is a panel-shaped decoy with
nothing connected to it.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    try:
        from qtpy import QtWidgets
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"qtpy unavailable: {exc}")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _form(model):
    from chisurf.gui.autoform import AutoForm

    return AutoForm(model)


def _spec(**options):
    import chisurf.core.dataspec as ds

    return ds.ModelView(sections=(ds.CustomSection(key="embed", options=options),))


def test_attr_adopts_the_widget_the_model_already_holds(qapp):
    from qtpy import QtWidgets

    existing = QtWidgets.QPushButton("the real one")
    existing.setObjectName("adoptMe")
    model = SimpleNamespace(
        view_spec=lambda: _spec(attr="panel", expanding=False),
        panel=existing,
    )
    form = _form(model)

    found = form.findChild(QtWidgets.QPushButton, "adoptMe")
    assert found is existing, "a copy was built instead of the widget itself"
    assert existing.parent() is not None


def test_attr_may_be_a_method(qapp):
    from qtpy import QtWidgets

    existing = QtWidgets.QLabel("built by uic")
    existing.setObjectName("adoptMe")
    model = SimpleNamespace(
        view_spec=lambda: _spec(attr="panel", expanding=False),
        panel=lambda: existing,
    )
    form = _form(model)
    assert form.findChild(QtWidgets.QLabel, "adoptMe") is existing


def test_a_missing_attr_is_reported_not_raised(qapp):
    model = SimpleNamespace(view_spec=lambda: _spec(attr="nothing_here"))
    form = _form(model)  # renders an empty section rather than raising
    assert form is not None


def test_widget_still_constructs_by_import_path(qapp):
    from qtpy import QtWidgets

    model = SimpleNamespace(
        view_spec=lambda: _spec(widget="qtpy.QtWidgets:QPushButton", expanding=False)
    )
    form = _form(model)
    assert form.findChildren(QtWidgets.QPushButton)


def test_expanding_false_leaves_the_widget_compact(qapp):
    from qtpy import QtWidgets

    existing = QtWidgets.QPushButton("compact")
    model = SimpleNamespace(
        view_spec=lambda: _spec(attr="panel", expanding=False), panel=existing
    )
    form = _form(model)  # held: dropping it deletes the adopted child with it
    assert form is not None
    assert not getattr(existing, "_autoform_expanding", False)
    assert existing.sizePolicy().verticalPolicy() != QtWidgets.QSizePolicy.Expanding
