"""Click coverage of the native FRET calculator: every control is operated with simulated pointer and keyboard events.

The window is drawn by the emtk frame loop (``ImApp.draw``) and driven only through ``press`` / ``release`` /
``pointer_move`` / ``wheel`` / ``key`` at the rectangles the controls were drawn in, or at the position of the
text a button drew; the assertions read the visible outcome (field values, status text, plot labels, windows).
The coverage list control -> test is in ``okf/plugins/emtk-ports/fret_calculator/REPORT.md``.
"""

from __future__ import annotations

import pytest
from emtk import keys
from emtk.view_form import spin_step

from .test_emtk_fret_calculator_parity import (
    SIZE,
    SMALL,
    click,
    draw,
    edit,
    hermetic,  # noqa: F401  (autouse fixture)
    hetero_state,
    homo_state,
    make_app,
    type_into,
)


@pytest.fixture
def app():
    return make_app()


def text_rect(painter, label, last=True):
    """The rectangle of the drawn text *label* (a button's caption)."""
    hits = [t[:4] for t in painter.texts if t[5] == label]
    assert hits, f"{label!r} is not drawn: {[t[5] for t in painter.texts][:40]}"
    return hits[-1] if last else hits[0]


def press_text(app, label, size=SIZE):
    """Click the button whose caption is *label*."""
    click(app, text_rect(draw(app, size), label), size)


def spin(app, name, direction, size=SIZE):
    """Click the upper (+1) or lower (-1) arrow of a field."""
    draw(app, size)
    x, y, w, h = app.active.form.rects[f"{name}.stepper"]
    app.press(x + w / 2, y + h * (0.25 if direction > 0 else 0.75))
    draw(app, size, frames=1)
    app.release()
    draw(app, size, frames=2)


# ── fields: arrows, wheel, click-away commit ----------------------------------------------------- #

HETERO_ARROWS = [
    ("tau0", "tau"),
    ("R0", "E"),
    ("R", "E"),
    ("tau", "R"),
    ("E", "R"),
    ("kFRET", "R"),
    ("sigma", "E"),
]
HOMO_ARROWS = [
    ("tau0", "R_DA"),
    ("R0", "R_DA"),
    ("t_RM", "R_DA"),
    ("rho", "R_DA"),
    ("R_DA", "t_RM"),
    ("sigma", None),
]


@pytest.mark.parametrize(("name", "follows"), HETERO_ARROWS)
def test_each_hetero_arrow_steps_its_field_up_and_down_and_runs_its_handler(app, name, follows):
    m = app.model.hetero
    section = next(
        s
        for sec in app.hetero.form_spec["sections"]
        for s in sec["sections"]
        if s.get("attr") == name
    )
    start = getattr(m, name)
    other = getattr(m, follows)
    spin(app, name, +1)
    up = getattr(m, name)
    assert up > start or up == section["maximum"], (name, start, up)
    assert getattr(m, follows) != other, f"the {name} arrow did not run its handler"
    spin(app, name, -1)
    spin(app, name, -1)
    down = getattr(m, name)
    assert down < up, (name, up, down)
    assert m.status == "" or name in (
        "E",
        "tau",
        "kFRET",
    )  # a stepped inverse may leave its range, then it says so


@pytest.mark.parametrize(("name", "follows"), HOMO_ARROWS)
def test_each_homo_arrow_steps_its_field_up_and_down_and_runs_its_handler(app, name, follows):
    app.select_tab(1)
    draw(app)
    m = app.model.homo
    start = getattr(m, name)
    other = getattr(m, follows) if follows else None
    spin(app, name, +1)
    up = getattr(m, name)
    assert up > start, (name, start, up)
    if follows:
        assert getattr(m, follows) != other, f"the {name} arrow did not run its handler"
    spin(app, name, -1)
    spin(app, name, -1)
    assert getattr(m, name) < up


def test_a_step_is_one_decade_below_the_value_when_the_spec_names_none(app):
    section = {"kind": "float"}
    assert (
        spin_step(50.0, section) == 1.0 and spin_step(4.0, section) == 0.1
    )  # what the arrows moved in the checks above


@pytest.mark.xfail(
    strict=True,
    reason="emtk gap: a DockManager window consumes the wheel, a spin field inside it never sees it "
    "(works in a plain im.begin window); see REPORT.md section 10",
)
def test_the_wheel_over_a_field_steps_it(app):
    m = app.model.hetero
    draw(app)
    x, y, w, h = app.active.form.rects["R"]
    app.pointer_move(x + w * 0.4, y + h / 2)
    draw(app, frames=1)
    before, e = m.R, m.E
    app.wheel(x + w * 0.4, y + h / 2, 1.0)
    draw(app, frames=2)
    assert m.R > before and m.E != e
    app.wheel(x + w * 0.4, y + h / 2, -1.0)
    draw(app, frames=2)
    assert m.R == pytest.approx(before)


def test_clicking_away_commits_a_typed_value_and_enter_on_an_unchanged_one_does_nothing(app):
    m = app.model.hetero
    draw(app)
    click(app, app.active.form.rects["R"], fx=0.3)
    app.key(0x41, "a", 0x04000000)
    for ch in "58":
        app.key(ord(ch), ch)
        draw(app, frames=1)
    assert m.R == 50.0  # typed, not committed yet
    click(app, app.active.form.rects["sigma"], fx=0.3)  # a click on another field commits it
    assert m.R == 58.0 and m.E != 0.560037
    status, e = m.status, m.E
    type_into(app, "R", "58")  # the same value again
    assert (m.R, m.E, m.status) == (58.0, e, status)


def test_a_clicked_field_takes_the_keyboard_and_a_read_only_one_ignores_typing(app):
    draw(app)
    assert not app.io.want_capture_keyboard
    click(app, app.active.form.rects["R0"], fx=0.3)
    assert app.io.want_capture_keyboard
    app.select_tab(1)
    draw(app)
    click(app, app.active.form.rects["k_homo"], fx=0.3)
    app.key(ord("7"), "7")
    draw(app, frames=2)
    assert app.model.homo.k_homo != 7.0 and "7" not in app.active.form.buffers.get("k_homo", "")


@pytest.mark.xfail(
    strict=True,
    reason="emtk gap: a text field keeps the keyboard after a click on a checkbox or button, "
    "so the next typed character lands in it; see REPORT.md section 10",
)
def test_clicking_a_checkbox_takes_the_keyboard_away_from_a_text_field(app):
    draw(app)
    click(app, app.active.form.rects["R0"], fx=0.3)
    click(app, app.active.form.rects["use_chi"])
    app.key(ord("9"), "9")
    draw(app, frames=2)
    assert app.active.form.buffers.get("R0") != "9"


# ── toggles, tabs, folds ---------------------------------------------------------------------------- #


def test_the_chi_toggle_is_a_checkbox_clicked_on_either_tab(app):
    for tab, model in ((0, app.model.hetero), (1, app.model.homo)):
        app.select_tab(tab)
        draw(app)
        before = model.use_chi
        click(app, app.active.form.rects["use_chi"])
        assert model.use_chi is (not before)
        click(app, app.active.form.rects["use_chi"])
        assert model.use_chi is before


def test_clicking_the_tab_labels_switches_the_window_and_the_selected_tab_is_kept(app):
    draw(app)
    assert "HeteroFRET" in " ".join(draw(app).strings)
    click(app, app.item_rects["tab_homofret"])
    strings = draw(app).strings
    assert (
        "Homo-FRET parameters" in strings and "k_homo" in strings and "Lifetime D0" not in strings
    )
    assert app.export_settings()["tab"] == 1
    click(app, app.item_rects["tab_heterofret"])
    assert "Lifetime D0" in draw(app).strings and app.export_settings()["tab"] == 0


def test_the_parameters_fold_header_hides_and_shows_the_fields(app):
    draw(app)
    assert "Lifetime D0" in draw(app).strings
    click(app, app.active.form.rects["Parameters.fold"])
    folded = draw(app).strings
    assert "Parameters" in folded and "Lifetime D0" not in folded and "kFRET" not in folded
    click(app, app.active.form.rects["Parameters.fold"])
    assert "Lifetime D0" in draw(app).strings


# ── the plots ----------------------------------------------------------------------------------------- #


def tick_labels(painter):
    return [s for s in painter.strings if s.replace(".", "").replace("-", "").isdigit()]


@pytest.mark.xfail(
    strict=True,
    reason="emtk gap: the wheel never reaches an implot inside a DockManager window, so no docked plot can be "
    "zoomed with it (works in a plain im.begin window); see REPORT.md section 10",
)
def test_the_wheel_zooms_a_plot(app):
    draw(app)
    before = tick_labels(draw(app))
    x, y, w, h = app.active.item_rects["distance"]
    cx, cy = x + w * 0.5, y + h * 0.5
    app.pointer_move(cx, cy)
    draw(app, frames=2)
    app.wheel(cx, cy, 3.0)
    assert tick_labels(draw(app, frames=2)) != before


def test_a_drag_pans_a_plot(app):
    draw(app)
    before = tick_labels(draw(app))
    x, y, w, h = app.active.item_rects["distance"]
    cx, cy = x + w * 0.5, y + h * 0.5
    app.pointer_move(cx, cy)
    draw(app, frames=2)
    app.press(cx, cy)
    draw(app, frames=1)
    for step in range(1, 8):
        app.drag(cx - 20 * step, cy)
        draw(app, frames=1)
    app.release()
    assert tick_labels(draw(app, frames=2)) != before, "dragging did not pan the distance plot"


def test_a_plot_redraws_with_the_curves_after_a_field_edit(app):
    first = draw(app)
    assert {"Gaussian", "chi"} <= set(first.strings)
    type_into(app, "sigma", "20")
    series = {s["name"]: s for s in app.model.hetero.distance_plot_series()}
    assert (
        max(series["Gaussian"]["y"]) < 0.02
    )  # a broad distribution: lower peak than the sigma = 6 default (0.0166)
    assert series["Gaussian"]["x"][0] == 0.0


# ── Guide, Help, the tour and the help window ------------------------------------------------------------ #


def test_the_guide_button_starts_the_tour_and_close_tour_ends_it(app):
    press_text(app, "Guide")
    assert app.tour.active and app.tour.step_idx == 0
    painter = draw(app)
    assert app.tour.awaiting and {"Next ►", "◄ Prev", "Close Tour"} <= set(painter.strings)
    type_into(
        app, "tau0", "3"
    )  # the highlighted field is operated by the user: the tour is released
    assert not app.tour.awaiting
    click(app, text_rect(draw(app), "Close Tour"))
    assert not app.tour.active


def test_the_tour_next_and_prev_buttons_can_be_clicked(app):
    press_text(app, "Guide")
    type_into(app, "tau0", "3")
    click(app, text_rect(draw(app), "Next ►"))
    assert app.tour.step_idx == 1
    click(app, text_rect(draw(app), "◄ Prev"))
    assert app.tour.step_idx == 0


def test_the_tour_is_walked_to_the_end_with_the_user_operating_each_highlighted_control(app):
    """Every awaited control is operated with real clicks and typing; Next is clicked in test_the_tour_next_and_prev_buttons_can_be_clicked."""
    press_text(app, "Guide")
    walked = 0
    while app.tour.active and walked < 3 * len(app.tour.steps):
        draw(app)
        step = app.tour.steps[app.tour.step_idx]
        target = step.get("target", {})
        name = target.get("attr") or target.get("name")
        if app.tour.awaiting:
            assert name, step
            if name == "tab_homofret":
                click(app, app.item_rects[name])
            elif name == "use_chi":
                click(app, app.active.form.rects[name])
            else:
                current = getattr(app.active.model, name)
                type_into(app, name, repr(round(current * 0.9, 3)) if current else "1")
            assert not app.tour.awaiting, (
                f"{step['title']}: operating {name} did not release the step"
            )
        app.tour.next()  # the Next button's callback (its click is the xfail test above)
        walked += 1
    assert not app.tour.active and app.active_tab == 1  # ended on the HomoFRET tab


def test_the_help_button_opens_a_window_with_working_buttons(app):
    press_text(app, "Help")
    assert app.help_window.open
    painter = draw(app)
    assert {"Start Guided Tour", "Close", "Close Help"} <= set(painter.strings)
    assert "HeteroFRET links the donor-acceptor" in " ".join(painter.strings)
    click(app, text_rect(draw(app), "Start Guided Tour"))
    assert not app.help_window.open and app.tour.active
    app.tour.stop()
    press_text(app, "Help")
    click(app, text_rect(draw(app), "Close Help"))
    assert not app.help_window.open
    press_text(app, "Help")
    click(app, text_rect(draw(app), "Close", last=False))
    assert not app.help_window.open
    press_text(app, "Help")
    app.key(keys.KEY_ESCAPE, "")
    draw(app)
    assert not app.help_window.open


@pytest.mark.xfail(
    strict=True,
    reason="emtk gap: the help window's section buttons are all '...##filter' (one id), so a click on any but "
    "the first never fires; see REPORT.md section 10",
)
def test_a_help_section_button_shows_only_that_section(app):
    press_text(app, "Help")
    click(app, text_rect(draw(app), "Plots"))
    shown = " ".join(draw(app).strings)
    assert (
        "The distance distribution and the induced rate" in shown
        and "HeteroFRET links the donor-acceptor" not in shown
    )


# ── file drop through the Qt host -------------------------------------------------------------------------- #


def test_a_file_dropped_on_the_host_reaches_the_app_and_says_the_calculator_has_no_file_input(app):
    QtWidgets = pytest.importorskip("qtpy.QtWidgets")
    from emtk.qt_host import ControlHost
    from qtpy import QtCore, QtGui

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    host = ControlHost(app)
    host.resize(*SIZE)
    host.show()
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile("/tmp/run.ptu")])
    enter = QtGui.QDragEnterEvent(
        QtCore.QPoint(10, 10),
        QtCore.Qt.CopyAction,
        mime,
        QtCore.Qt.LeftButton,
        QtCore.Qt.NoModifier,
    )
    host.dragEnterEvent(enter)
    assert enter.isAccepted(), "the host refuses a drop on this app"
    drop = QtGui.QDropEvent(
        QtCore.QPointF(10, 10),
        QtCore.Qt.CopyAction,
        mime,
        QtCore.Qt.LeftButton,
        QtCore.Qt.NoModifier,
    )
    host.dropEvent(drop)
    qapp.processEvents()
    assert drop.isAccepted()
    assert app.model.hetero.status == "The FRET Calculator takes no dropped files."
    assert "takes no dropped files" in " ".join(draw(app).strings)
    host.close()


# ── the same flow at the small size ------------------------------------------------------------------------- #


def test_the_flow_works_in_the_small_window_too(app):
    m = app.model.hetero
    draw(app, SMALL)
    type_into(app, "R", "57", size=SMALL)
    assert m.R == 57.0
    draw(app, SMALL)
    click(app, app.active.form.rects["use_chi"], SMALL)
    assert m.use_chi
    click(app, app.item_rects["tab_homofret"], SMALL)
    assert app.active_tab == 1
    type_into(app, "t_RM", "2", size=SMALL)
    assert (
        app.model.homo.t_RM == 2.0
        and hetero_state(m)["R"] == 57.0
        and homo_state(app.model.homo)["R_DA"] != 51.35
    )
    assert edit  # (re-exported helper kept for symmetry with the parity tests)
