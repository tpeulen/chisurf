"""The detector table's G-Factor cell is edited in place, and guarded.

A row's G-Factor lives in a ``QLineEdit`` held as a cell widget, and two things
about it matter enough to pin down. It is updated *in place* -- the calculator
and the settings loader write through
:meth:`DetectorWizardPage._set_g_factor_programmatically` rather than swapping a
fresh widget in, because a replaced widget drops the signal wiring and the
row's last-valid value with it. And it is *guarded*: a bare ``setText`` from
code that did not go through that method is reverted, so a stray write cannot
silently overwrite a calibrated G-factor.
"""

import pytest
from qtpy.QtWidgets import QLineEdit

from chisurf.gui.widgets.wizard.tttr_channeldefinition import DetectorWizard

#: Column of the detector table holding the G-Factor line edit.
G_FACTOR_COLUMN = 3


@pytest.fixture
def page(qapp):
    """A detector wizard page with one freshly added detector row."""
    wizard = DetectorWizard()
    page = wizard.page(0)
    page._add_detector()
    yield page
    wizard.close()


def _cell(page, column: int) -> QLineEdit:
    """Return the last row's cell widget in ``column``."""
    row = page.detectors_form.rowCount() - 1
    return page.detectors_form.cellWidget(row, column)


def test_programmatic_update_keeps_the_same_widget(page):
    """The calculator's write updates the existing editor, not a new one."""
    row = page.detectors_form.rowCount() - 1
    before = _cell(page, G_FACTOR_COLUMN)
    assert isinstance(before, QLineEdit)

    page._set_g_factor_programmatically(row, "3.456", l1="0.01000", l2="0.02000")

    assert _cell(page, G_FACTOR_COLUMN) is before
    assert before.text() == "3.456"
    assert _cell(page, 4).text() == "0.01000"
    assert _cell(page, 5).text() == "0.02000"


def test_programmatic_update_reaches_the_settings(page):
    """A written G-factor is what ``get_settings`` reports for that detector."""
    row = page.detectors_form.rowCount() - 1
    name = page.detectors_form.item(row, 0).text()
    page._set_g_factor_programmatically(row, "3.456")

    detectors = page.get_settings()["detectors"]
    assert detectors[name]["g_factor"] == pytest.approx(3.456)


def test_unauthorised_write_is_reverted(page):
    """A bare ``setText`` from outside the guarded path does not stick."""
    row = page.detectors_form.rowCount() - 1
    page._set_g_factor_programmatically(row, "1.234")
    line_edit = _cell(page, G_FACTOR_COLUMN)

    line_edit.setText("9.999")

    assert line_edit.text() == "1.234"


def test_user_edit_is_kept_and_normalised(page):
    """Typing a value keeps it, formatted to three decimals."""
    line_edit = _cell(page, G_FACTOR_COLUMN)
    line_edit.textEdited.emit("2.3")  # what typing emits, before textChanged
    line_edit.setText("2.3")
    line_edit.editingFinished.emit()

    assert line_edit.text() == "2.300"


def test_invalid_user_edit_falls_back_to_the_last_valid_value(page):
    """Finishing an edit on unparseable text restores the previous G-factor."""
    row = page.detectors_form.rowCount() - 1
    page._set_g_factor_programmatically(row, "1.500")
    line_edit = _cell(page, G_FACTOR_COLUMN)

    line_edit.textEdited.emit("not a number")
    line_edit.setText("not a number")
    line_edit.editingFinished.emit()

    assert line_edit.text() == "1.500"
