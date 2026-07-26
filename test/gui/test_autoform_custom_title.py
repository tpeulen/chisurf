"""A ``custom`` AutoForm section shows the title the view spec gives it.

``Section.title`` is on the base type, so every section may carry one — but
``_build_custom`` dropped it. The consequence was invisible until a panel had
more than one custom widget of the same kind: the molecule-MLE tool stacked
three ``path_list`` drop boxes with nothing to say which took the CLSM files,
which the IRF and which the analysis region. Nothing else in the suite notices,
because the form still builds and the widget still binds.
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


@pytest.fixture
def marker_section():
    """Register a trivial custom section and yield its key."""
    from qtpy import QtWidgets

    from chisurf.gui.autoform.sections import register_section

    key = "_test_marker"

    @register_section(key)
    def _factory(model, target, **options):
        widget = QtWidgets.QLineEdit()
        widget.setObjectName(f"marker:{target}")
        return widget

    return key


def _form(*sections):
    import chisurf.core.dataspec as ds
    from chisurf.gui.autoform import AutoForm

    view = ds.ModelView(sections=sections)
    return AutoForm(SimpleNamespace(view_spec=lambda: view, a=[], b=[]))


def _captions(form):
    from qtpy import QtWidgets

    return {label.text() for label in form.findChildren(QtWidgets.QLabel)}


def test_two_custom_sections_are_told_apart_by_their_titles(qapp, marker_section):
    """Both titles are drawn, so the two boxes are distinguishable."""
    import chisurf.core.dataspec as ds

    form = _form(
        ds.CustomSection(key=marker_section, target="a", title="CLSM imaging files"),
        ds.CustomSection(key=marker_section, target="b", title="Analysis region"),
    )
    captions = _captions(form)
    assert "CLSM imaging files" in captions
    assert "Analysis region" in captions


def test_the_widget_itself_is_still_reachable(qapp, marker_section):
    """Wrapping must not hide the custom widget from the form."""
    from qtpy import QtWidgets

    import chisurf.core.dataspec as ds

    form = _form(ds.CustomSection(key=marker_section, target="a", title="Titled"))
    names = {w.objectName() for w in form.findChildren(QtWidgets.QLineEdit)}
    assert "marker:a" in names


def test_an_untitled_custom_section_gains_no_caption(qapp, marker_section):
    """The wrapper is only added when there is something to write in it."""
    import chisurf.core.dataspec as ds

    form = _form(ds.CustomSection(key=marker_section, target="a"))
    assert not any(_captions(form))


def test_the_description_becomes_the_caption_tooltip(qapp, marker_section):
    """Long help belongs on the caption, not in a second line of text."""
    from qtpy import QtWidgets

    import chisurf.core.dataspec as ds

    form = _form(
        ds.CustomSection(
            key=marker_section,
            target="a",
            title="Analysis region",
            description="Confines the molecule search to one patch.",
        )
    )
    tips = {
        label.text(): label.toolTip()
        for label in form.findChildren(QtWidgets.QLabel)
    }
    assert tips["Analysis region"] == "Confines the molecule search to one patch."
