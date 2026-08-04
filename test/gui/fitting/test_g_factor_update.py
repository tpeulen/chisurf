"""A G-factor typed into one detector row belongs to that detector alone.

The page grew a ``+`` button that names detectors itself, so the
``new_detector_le`` line edit this test drove is gone. It was also asserting
nothing about ChiSurf: it replaced the G-factor cell widget with one of its own
and then checked that ``cellWidget`` returned the widget it had just set --
true of any ``QTableWidget``. What matters is that the value reaches
:meth:`DetectorWizardPage.get_settings`, per detector and without bleeding into
its neighbour.
"""

from chisurf.gui.widgets.wizard.tttr_channeldefinition import DetectorWizard

#: Column of the G-factor cell in ``detectors_form``.
G_FACTOR_COLUMN = 3

#: Column holding the detector name.
NAME_COLUMN = 0


def _type_g_factor(qtbot, form, row: int, text: str) -> None:
    """Type a G-factor into a row the way a user does.

    ``setText`` is not equivalent here: :meth:`DetectorWizardPage.
    _wire_g_factor_cell` deliberately *reverts* programmatic writes, so that a
    calibrated G-factor cannot be overwritten by unrelated code. Only key
    events (``textEdited``) and explicitly allowed internal writes get through,
    and the value is normalised on ``editingFinished``.
    """
    cell = form.cellWidget(row, G_FACTOR_COLUMN)
    cell.selectAll()
    qtbot.keyClicks(cell, text)
    cell.editingFinished.emit()


def test_g_factor_update(qtbot):
    """Two detectors keep their own G-factors, through the page's own widgets."""
    wizard = DetectorWizard()
    qtbot.addWidget(wizard)
    page = wizard.page(0)

    form = page.detectors_form
    form.setRowCount(0)
    page._add_detector()
    page._add_detector()
    assert form.rowCount() == 2, "the add button must create a row per detector"

    names = [form.item(row, NAME_COLUMN).text() for row in range(2)]
    assert names[0] != names[1], "auto-named detectors must not collide"

    _type_g_factor(qtbot, form, 0, "1.234")
    _type_g_factor(qtbot, form, 1, "2.345")

    detectors = page.get_settings()["detectors"]

    assert float(detectors[names[0]]["g_factor"]) == 1.234
    assert float(detectors[names[1]]["g_factor"]) == 2.345


def test_a_detector_row_can_be_removed_without_disturbing_the_other(qtbot):
    """Deleting a row must not shift another detector's G-factor onto it."""
    wizard = DetectorWizard()
    qtbot.addWidget(wizard)
    page = wizard.page(0)

    form = page.detectors_form
    form.setRowCount(0)
    page._add_detector()
    page._add_detector()
    _type_g_factor(qtbot, form, 0, "1.234")
    _type_g_factor(qtbot, form, 1, "2.345")
    kept = form.item(1, NAME_COLUMN).text()

    form.removeRow(0)
    detectors = page.get_settings()["detectors"]

    assert list(detectors) == [kept]
    assert float(detectors[kept]["g_factor"]) == 2.345
