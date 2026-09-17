"""AutoForm captions are typeset from the plain label in the view spec.

The view spec spells a quantity the way code and translators want it —
``tau_D(0)``, ``Phi_A`` — and the panel shows the typography. Nothing else in
the suite would notice if this stopped working: the form still builds, the field
still binds, the label simply reads ``tau_D(0)`` forever.
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


def _model(view, **attrs):
    return SimpleNamespace(view_spec=lambda: view, **attrs)


def _labels(form):
    """``{plain label: rendered text}`` for every caption the form drew."""
    from qtpy import QtWidgets

    found = {}
    for label in form.findChildren(QtWidgets.QLabel):
        plain = label.property("plainLabel")
        if plain:
            found[plain] = label.text()
    return found


def _form(*sections):
    import chisurf.core.dataspec as ds
    from chisurf.gui.autoform import AutoForm

    view = ds.ModelView(sections=sections)
    attrs = {s.attr: 1.0 for s in sections}
    return AutoForm(_model(view, **attrs))


def test_a_plain_label_is_rendered_typeset(qapp):
    """``tau_D(0)`` in the spec, τ with a real subscript on screen."""
    from qtpy import QtCore, QtWidgets

    import chisurf.core.dataspec as ds

    form = _form(
        ds.ValueSection(attr="tau", kind="float", label="tau_D(0) (ns)"),
        ds.ValueSection(attr="phi", kind="float", label="Phi_A"),
        ds.ValueSection(attr="k2", kind="float", label="kappa^2"),
    )
    rendered = _labels(form)
    assert rendered["tau_D(0) (ns)"] == "&tau;<sub>D(0)</sub> (ns)"
    assert rendered["Phi_A"] == "&Phi;<sub>A</sub>"
    assert rendered["kappa^2"] == "&kappa;<sup>2</sup>"

    # RichText explicitly, not Qt's AutoText guess — the heuristic does not fire
    # for every fragment, and a caption showing literal <sub> is worse than none.
    for label in form.findChildren(QtWidgets.QLabel):
        if label.property("plainLabel"):
            assert label.textFormat() == QtCore.Qt.RichText


def test_the_plain_text_stays_reachable(qapp):
    """A typeset caption must still be findable — by a test, and by the user.

    Without this the label's meaning exists only as markup, and searching the
    panel for the name in the documentation finds nothing.
    """
    import chisurf.core.dataspec as ds

    form = _form(ds.ValueSection(attr="r", kind="float", label="R_DA (Å)"))
    assert "R_DA (Å)" in _labels(form)


def test_an_ordinary_label_is_untouched(qapp):
    """Most labels are prose and must survive exactly as written."""
    import chisurf.core.dataspec as ds

    form = _form(ds.ValueSection(attr="w", kind="float", label="Linker width (Å)"))
    assert _labels(form)["Linker width (Å)"] == "Linker width (Å)"


def test_set_field_label_retitles_a_field_at_run_time(qapp):
    """The counterpart of a fitting widget's ``label_text``.

    The field keeps the model attribute it is bound to — its programmatic
    identity — while what the reader sees changes.
    """
    import chisurf.core.dataspec as ds

    form = _form(ds.ValueSection(attr="i_da", kind="float", label="I_DA"))
    assert form.set_field_label("i_da", text="F_D|A")
    assert _labels(form)["F_D|A"] == "F<sub>D</sub>|A"

    # ready-made markup wins over the plain form
    assert form.set_field_label("i_da", html="F<sub>A|D</sub>")
    assert _labels(form)["FA|D"] == "F<sub>A|D</sub>"

    # an attribute no field is bound to reports that it found nothing
    assert not form.set_field_label("no_such_attr", text="x")
