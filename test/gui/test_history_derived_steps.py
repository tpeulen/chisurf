"""One user edit is one undo step, whatever it recomputes.

Editing a parameter records the edit and then the fit's recompute (``fit.update``).
A recompute is ``side_effect_class="derived"`` and belongs to the step before it:
undo and redo stop only at step ends.
"""


def test_step_ends_skip_derived_events():
    from chisurf.history.core import OperationHistory

    history = OperationHistory()
    history.record("parameter.value", "edit", {}, persist=False)
    history.record("fit.update", "recompute", {"side_effect_class": "derived"}, persist=False)
    history.record("fit.run", "fit", {"side_effect_class": "execution"}, persist=False)
    assert [history.is_step_end(i) for i in range(-1, 3)] == [True, False, True, True]
