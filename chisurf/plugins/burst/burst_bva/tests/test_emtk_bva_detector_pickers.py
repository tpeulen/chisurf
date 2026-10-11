"""The Setup, Donor detector and Acceptor detector combos of the Channel Definitions tab, operated with the pointer."""

from __future__ import annotations

import pytest

from chisurf.plugins.burst.burst_bva.gui.app import create_app

from .test_emtk_bva_clicks import (  # noqa: F401 (hermetic: autouse)
    SIZE,
    click,
    draw,
    hermetic,
    press,
    text_rect,
)


@pytest.fixture
def app():
    window = create_app()
    window.model.auto_update = False
    editor = window.bva_gui.editor
    for name, detectors in (
        (
            "lab_alex",
            {
                "green": {"chs": [0, 8], "micro_time_ranges": [[0, 2000]]},
                "red": {"chs": [1, 9], "micro_time_ranges": [[100, 4000]]},
            },
        ),
        (
            "lab_three",
            {
                "det_a": {"chs": [2], "micro_time_ranges": [[0, 32768]]},
                "det_b": {"chs": [3], "micro_time_ranges": [[0, 32768]]},
                "det_c": {"chs": [4, 5], "micro_time_ranges": [[10, 20], [30, 40]]},
            },
        ),
    ):
        editor.model.data["detectors"] = detectors
        editor.model.data["tttr_reading"]["file_type"] = "PTU"
        editor.model.save_setup(name)
    editor.toolbar.reload(open_last=False)
    editor.toolbar.select("")  # an unsaved working definition: the tool starts without a setup
    yield window
    window.close()


def pick(app, field, label):
    """Open the combo *field* by pressing it, then press the entry *label* of the list it drew."""
    draw(app)
    click(app, app.item_rects[field])
    painter = draw(app)
    click(app, text_rect(painter, label))


def open_channels(app):
    draw(app)
    click(app, app.item_rects["Channel Definitions"])
    draw(app)


def test_setup_combo_lists_the_saved_setups_and_picking_one_sets_donor_and_acceptor(app):
    open_channels(app)
    gui, model = app.bva_gui, app.model
    strings = draw(app).strings
    assert "FRET Pair Assignment" in strings and "Donor detector:" in strings
    pick(app, "bva_setup", "lab_alex")
    assert gui.editor.model.current_name == "lab_alex"
    assert (gui.donor_detector, gui.acceptor_detector) == ("green", "red")
    assert model.donor_channels == [0, 8] and model.acceptor_channels == [1, 9]
    assert model.donor_micro_time_ranges == [(0, 2000)] and model.acceptor_micro_time_ranges == [
        (100, 4000)
    ]
    assert model.file_type == "PTU"
    assert {"green", "red"} <= set(draw(app).strings)


def test_donor_and_acceptor_combos_offer_the_detectors_of_the_setup_and_assign_their_channels(app):
    open_channels(app)
    model = app.model
    pick(app, "bva_setup", "lab_three")
    assert (app.bva_gui.donor_detector, app.bva_gui.acceptor_detector) == ("det_a", "det_b")
    pick(app, "donor_detector", "det_c")
    assert model.donor_channels == [4, 5] and model.donor_micro_time_ranges == [(10, 20), (30, 40)]
    pick(app, "acceptor_detector", "det_a")
    assert model.acceptor_channels == [2]
    # the choice feeds the analysis settings, not only the model fields
    settings = model.bva_settings()
    assert settings["donor_channels"] == [4, 5] and settings["acceptor_channels"] == [2]


def test_editing_a_detector_in_the_shared_editor_refreshes_the_pair_choices(app):
    open_channels(app)
    pick(app, "bva_setup", "lab_alex")
    editor = app.bva_gui.editor
    editor.add_detector()
    names = list(editor.model.get_settings()["detectors"])
    assert len(names) == 3
    draw(app)
    pick(app, "donor_detector", names[-1])
    assert app.bva_gui.donor_detector == names[-1]
    # the Detectors tab draws the shared editor
    click(app, app.item_rects["Detectors"])
    assert "Setup:" in draw(app).strings and app.bva_gui.selected_settings_tab == "Detectors"
