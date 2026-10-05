"""One user edit is one undo step, whatever it recomputes.

Editing a parameter in the GUI records the edit and then the fit's recompute
(``fit.update``). Both were navigable, so Ctrl+Z first stepped back over the
recompute -- the value on screen did not change -- and only the second press
undid the edit; Ctrl+Y mirrored it. A recompute is ``side_effect_class="derived"``
and belongs to the step before it: undo and redo stop only at step ends.
"""

import numpy as np

from chisurf.gui.widgets.history_browser import HistoryBrowserWidget
from test.history.test_history_scientific_owner import scientific_owner


def _edit_then_recompute(owner, history, value):
    owner.fits[0].model.parameters_all_dict["a"].value = value
    history.record("parameter.value", f"a = {value}", {"new_value": value}, persist=False)
    for fit in owner.fits:
        fit.model.update()
    history.record("fit.update", "recompute", {"side_effect_class": "derived"}, persist=False)


def test_one_undo_reverts_an_edit_and_one_redo_reapplies_it(qtbot, tmp_path):
    owner, history, raw, capture, publish = scientific_owner(tmp_path)
    history.configure_science(capture, publish)
    _edit_then_recompute(owner, history, 7)
    _edit_then_recompute(owner, history, 9)
    browser = HistoryBrowserWidget()
    qtbot.addWidget(browser)
    browser.set_history(history)

    browser.undo_step()
    assert owner.fits[0].model.parameters_all_dict["a"].value == 7
    np.testing.assert_array_equal(owner.fits[1].model.y, 7 * np.arange(8.0) + 2)
    browser.undo_step()
    assert owner.fits[0].model.parameters_all_dict["a"].value == 4
    assert not browser.can_undo()

    browser.redo_step()
    assert owner.fits[0].model.parameters_all_dict["a"].value == 7
    # Redo lands after the recompute, so derived outputs are current too.
    np.testing.assert_array_equal(owner.fits[1].model.y, 7 * np.arange(8.0) + 2)
    browser.redo_step()
    assert owner.fits[0].model.parameters_all_dict["a"].value == 9
    assert not browser.can_redo()


def test_step_ends_skip_derived_events():
    from chisurf.history.core import OperationHistory

    history = OperationHistory()
    history.record("parameter.value", "edit", {}, persist=False)
    history.record("fit.update", "recompute", {"side_effect_class": "derived"}, persist=False)
    history.record("fit.run", "fit", {"side_effect_class": "execution"}, persist=False)
    assert [history.is_step_end(i) for i in range(-1, 3)] == [True, False, True, True]
