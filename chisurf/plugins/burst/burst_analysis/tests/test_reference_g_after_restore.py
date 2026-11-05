"""The reference dye's G reaches the setup after a session is restored.

The owner's session (2026-11-05): Data Selection restored ``applied_g = {G|G: 1.436}`` with the
session, while the setup came back from the setup library at G 1.0. The G written last no longer
matched the setup, so it was read as a hand edit and never written again: Burst MLE and the IRF
tool fitted at G 1.0 while the reference dye gave 1.436.
"""

from types import SimpleNamespace

from chisurf.plugins.burst.burst_analysis.gui.data_selection_app import BurstDataSelectionApp


def _app(setup_g: dict, applied: dict, computed: dict):
    written = {}
    calibration = {"colours": {"G": {"g_factor": {d: {"g": g} for d, g in computed.items()}}}}
    app = SimpleNamespace(
        source=SimpleNamespace(applied_g=dict(applied), calibration=calibration),
        on_apply_g=written.update,
        setup=lambda: {"detectors": {d: {"g_factor": g} for d, g in setup_g.items()}},
        UNCALIBRATED_G=BurstDataSelectionApp.UNCALIBRATED_G,
    )
    for name in ("setup_g", "computed_g", "_edited_by_hand", "apply_all_g", "hand_edited_g"):
        setattr(app, name, getattr(BurstDataSelectionApp, name).__get__(app))
    return app, written


def test_a_setup_reloaded_at_g_1_takes_the_reference_g_again():
    app, written = _app({"G|G": 1.0}, applied={"G|G": 1.436}, computed={"G|G": 1.436})
    assert app.hand_edited_g() == []
    assert app.apply_all_g() == 1
    assert written == {"G|G": 1.436}


def test_a_g_edited_by_hand_is_kept():
    app, written = _app({"G|G": 1.2}, applied={"G|G": 1.436}, computed={"G|G": 1.436})
    assert app.hand_edited_g() == ["G|G"]
    assert app.apply_all_g() == 0
    assert written == {}


def test_a_first_calibration_is_written():
    app, written = _app({"G|G": 1.0}, applied={}, computed={"G|G": 1.436})
    assert app.apply_all_g() == 1
    assert written == {"G|G": 1.436}
