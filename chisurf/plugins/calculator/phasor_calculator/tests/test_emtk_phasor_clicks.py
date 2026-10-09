"""Every control of the phasor calculator operated with simulated pointer and keyboard events.

Only ``press`` / ``release`` / ``pointer_move`` / ``wheel`` / ``key`` at the rectangles the controls were drawn in reach the
window; the assertions read what a person sees (the model fields, the reference table, the plot's legend and axis labels,
the folds). The control -> test list is in ``okf/plugins/emtk-ports/phasor_calculator/REPORT.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from emtk import keys

from chisurf.plugins.calculator.phasor_calculator.gui.app import SETTINGS, make_app

from .driving import (
    BIG,
    SMALL,
    PhasorDriver,
    clipped_texts,
    draw_clip,
    hermetic_env,
    layout_problems,
)

PLUGIN = Path(__file__).parents[1]


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)


@pytest.fixture(autouse=True)
def no_window_failed_to_draw(caplog):
    yield
    bad = [r.getMessage() for r in caplog.records if r.levelno >= 40]
    assert not bad, bad[:3]


@pytest.fixture
def app():
    return make_app()


@pytest.fixture
def drv(app):
    d = PhasorDriver(app, BIG)
    d.draw(3)
    return d


def model(drv):
    return drv.app.tool._model


def unfold(drv, title):
    """Open a folded group by clicking its header."""
    drv.click(f"{title}.fold")
    drv.draw(2)


def legend(drv):
    return set(drv.draw(2).strings)


def table_rows(drv):
    """The reference table's body: [(tau, g, s), ...] as drawn."""
    x, y, w, h = drv.rect("reference_rows")
    cells = [t for t in drv.draw(2).texts if x <= t[0] <= x + w and y + 12 < t[1] <= y + h]
    rows = {}
    for t in cells:
        rows.setdefault(round(t[1]), []).append((t[0], t[5]))
    return [tuple(s for _, s in sorted(r)) for _, r in sorted(rows.items())]


def effective(drv):
    return next(s for s in drv.draw(2).strings if s.startswith("Effective f"))


# -- the frequency, the harmonic and the lifetimes ------------------------------------------------------------- #


def test_typing_a_frequency_updates_the_effective_frequency_and_the_table(drv):
    drv.type_into("frequency", "40")
    assert model(drv).frequency == 40.0 and effective(drv) == "Effective f = 40 MHz"
    omega_tau = 2 * np.pi * 40e6 * 0.5e-9
    first = table_rows(drv)[0]
    assert float(first[1]) == pytest.approx(1 / (1 + omega_tau**2), abs=5e-4)
    assert float(first[2]) == pytest.approx(omega_tau / (1 + omega_tau**2), abs=5e-4)


def test_typed_garbage_in_the_frequency_is_ignored_and_a_huge_value_is_clamped(drv):
    drv.type_into("frequency", "abc")
    assert model(drv).frequency == 80.0
    drv.type_into("frequency", "99999")
    assert model(drv).frequency == 10000.0  # the Qt maximum
    drv.type_into("frequency", "0")
    assert model(drv).frequency == pytest.approx(0.001)  # the Qt minimum


def stepper(drv, name, direction):
    x, y, w, h = drv.rect(f"{name}.stepper")
    drv.click_at(x + w / 2, y + h * (0.25 if direction > 0 else 0.75))


def test_the_frequency_arrows_step_by_one_megahertz(drv):
    stepper(drv, "frequency", +1)
    assert model(drv).frequency == pytest.approx(81.0)
    stepper(drv, "frequency", -1)
    stepper(drv, "frequency", -1)
    assert model(drv).frequency == pytest.approx(79.0)
    assert effective(drv) == "Effective f = 79 MHz"


def test_the_harmonic_arrows_and_typing_multiply_the_effective_frequency(drv):
    stepper(drv, "harmonic", +1)
    assert model(drv).harmonic == 2 and effective(drv) == "Effective f = 160 MHz"
    stepper(drv, "harmonic", -1)
    stepper(drv, "harmonic", -1)
    assert model(drv).harmonic == 1  # the Qt minimum
    drv.type_into("harmonic", "99")
    assert model(drv).harmonic == 16  # the Qt maximum
    drv.type_into("harmonic", "3")
    assert model(drv).harmonic == 3 and effective(drv) == "Effective f = 240 MHz"


def test_the_lifetimes_field_sets_the_reference_rows(drv):
    drv.type_into("taus", "1, 3")
    assert [r[0] for r in table_rows(drv)] == ["1", "3"]
    drv.type_into("taus", "2; 5 ; x")
    assert [r[0] for r in table_rows(drv)] == [
        "2",
        "5",
    ]  # a bad token is skipped, as the Qt model did
    drv.type_into("taus", "nonsense")
    assert [r[0] for r in table_rows(drv)] == ["1"]  # nothing usable: the Qt model's fallback


# -- the reference geometry -------------------------------------------------------------------------------------- #


def test_each_reference_toggle_flips_and_its_overlay_follows(drv):
    for name, legend_item in (("show_ticks", "lifetime ticks"), ("show_fret", "FRET trajectory")):
        before = getattr(model(drv), name)
        drv.click(name)
        assert getattr(model(drv), name) is (not before)
        assert (legend_item in legend(drv)) is (not before)
        drv.click(name)
        assert getattr(model(drv), name) is before
    for name in ("show_grid", "show_polar_grid"):
        before = getattr(model(drv), name)
        drv.click(name)
        assert getattr(model(drv), name) is (not before)


def test_the_donor_lifetime_is_typed_and_stepped(drv):
    stepper(drv, "tau_d0", +1)
    assert model(drv).tau_d0 == pytest.approx(4.1)
    drv.type_into("tau_d0", "2.5")
    assert model(drv).tau_d0 == 2.5
    drv.type_into("tau_d0", "5000")
    assert model(drv).tau_d0 == 1000.0  # the Qt maximum


# -- the folded groups ---------------------------------------------------------------------------------------- #


def test_groups_start_as_the_spec_declares_and_a_click_on_the_header_opens_one(drv):
    drawn = drv.app.phasor_gui.form.rects  # what the last frame drew
    assert "g1" not in drawn and "frac1" not in drawn and "cursor_g" not in drawn
    unfold(drv, "Two-component line")
    assert "g1" in drawn and "s2" in drawn
    unfold(drv, "Two-component line")  # and closes again
    assert "g1" not in drawn


def test_the_two_component_line_toggle_and_its_four_fields(drv):
    unfold(drv, "Two-component line")
    drv.click("show_component")
    assert model(drv).show_component and "component line" in legend(drv)
    for name, text, expected in (
        ("g1", "0.7", 0.7),
        ("s1", "0.4", 0.4),
        ("g2", "0.2", 0.2),
        ("s2", "0.5", 0.5),
    ):
        drv.type_into(name, text)
        assert getattr(model(drv), name) == expected
    drv.type_into("g1", "5")
    assert model(drv).g1 == 1.1  # the Qt maximum
    stepper(drv, "s2", -1)
    assert model(drv).s2 == pytest.approx(0.49)


def test_the_mixing_region_toggle_and_the_fraction_move_the_mixture_point(drv):
    unfold(drv, "Mixing region")
    drv.click("show_mixing")
    assert model(drv).show_mixing and "mixture" in legend(drv)
    mixture = lambda: next(o for o in drv.app.phasor_gui._overlays() if o["name"] == "mixture")  # noqa: E731
    half = (float(mixture()["x"][0]), float(mixture()["y"][0]))
    drv.type_into("frac1", "0.2")
    assert model(drv).frac1 == pytest.approx(0.2)
    moved = (float(mixture()["x"][0]), float(mixture()["y"][0]))
    m = model(drv)
    assert moved == pytest.approx(
        (0.2 * m.g1 + 0.8 * m.g2, 0.2 * m.s1 + 0.8 * m.s2)
    ) and moved != pytest.approx(half)
    drv.type_into("frac1", "7")
    assert model(drv).frac1 == 1.0  # the Qt maximum
    stepper(drv, "frac1", -1)
    assert model(drv).frac1 == pytest.approx(0.95)


def test_the_cursor_toggle_and_its_three_fields(drv):
    unfold(drv, "Cursor")
    drv.click("show_cursor")
    assert model(drv).show_cursor and "cursor" in legend(drv)
    drv.type_into("cursor_g", "0.6")
    drv.type_into("cursor_s", "0.25")
    drv.type_into("cursor_radius", "0.1")
    m = model(drv)
    assert (m.cursor_g, m.cursor_s, m.cursor_radius) == (0.6, 0.25, 0.1)
    cursor = next(o for o in drv.app.phasor_gui._overlays() if o["name"] == "cursor")
    xs = np.asarray(cursor["x"], float)
    assert xs.mean() == pytest.approx(0.6, abs=0.02) and (xs.max() - xs.min()) / 2 == pytest.approx(
        0.1, abs=0.01
    )
    stepper(drv, "cursor_radius", +1)
    assert m.cursor_radius == pytest.approx(0.11)


# -- the results table ------------------------------------------------------------------------------------------- #


def test_the_table_header_sorts_and_a_row_click_selects_without_changing_values(drv):
    drv.type_into("taus", "4, 1, 2")
    assert [r[0] for r in table_rows(drv)] == ["4", "1", "2"]
    x, y, w, h = drv.rect("reference_rows")
    head = next(t for t in drv.draw(2).texts if t[5] == "τ (ns)" and x <= t[0] <= x + w)
    drv.click_at(head[0] + 4, head[1] + 4)
    first = [r[0] for r in table_rows(drv)]
    drv.click_at(head[0] + 4, head[1] + 4)
    second = [r[0] for r in table_rows(drv)]
    assert sorted(first, key=float) in (first, first[::-1]) and first != second
    row = next(t for t in drv.draw(2).texts if t[5] == "2" and x <= t[0] <= x + w)
    drv.click_at(row[0] + 3, row[1] + 3)
    assert model(drv).taus == "4, 1, 2"


# -- the plot ------------------------------------------------------------------------------------------------------ #


def tick_labels(drv):
    left = drv.size[0] * 0.36  # the plot window starts here; its axis labels are numbers
    return [
        (t[5], round(t[0]), round(t[1]))
        for t in drv.draw(2).texts
        if t[0] >= left and t[5].replace("-", "").replace(".", "").isdigit()
    ]


def test_dragging_the_plot_pans_it(drv):
    x, y, w, h = drv.rect("plot")
    before = tick_labels(drv)
    drv.drag((x + w / 2, y + h / 2), (x + w / 2 - 120, y + h / 2 + 60))
    assert tick_labels(drv) != before


def test_the_wheel_zooms_the_plot(drv):
    x, y, w, h = drv.rect("plot")
    before = tick_labels(drv)
    drv.wheel(x + w / 2, y + h / 2, 3)
    assert tick_labels(drv) != before


# -- guide, help, persistence ----------------------------------------------------------------------------------- #


def test_guide_button_starts_the_tour_and_the_frequency_step_waits_for_a_typed_value(drv):
    drv.click("guide")
    tour = drv.app.phasor_gui.tour
    assert tour.active and tour.step_idx == 0
    drv.click_text("Next ►")
    assert tour.step_idx == 1 and tour.awaiting  # the frequency step
    drv.type_into("frequency", "50")
    assert not tour.awaiting
    drv.click_text("Next ►")
    assert tour.step_idx == 2 and tour.awaiting  # the lifetimes step
    drv.type_into("taus", "1, 2")
    assert not tour.awaiting


def test_escape_ends_the_tour_and_help_opens_and_closes(drv):
    drv.click("guide")
    assert drv.app.phasor_gui.tour.active
    drv.escape()
    assert not drv.app.phasor_gui.tour.active
    drv.click("help")
    assert drv.app.phasor_gui.help_window.open
    assert any("Phasor calculator" in s for s in drv.draw(2).strings)
    drv.escape()
    assert not drv.app.phasor_gui.help_window.open


def test_every_guide_target_is_a_drawn_control_after_the_step_unfolds_its_group(drv):
    gui = drv.app.phasor_gui
    for index, step in enumerate(gui.tour.steps):
        key = gui.tour._target_key(step.get("target"))
        if not key:
            continue
        gui.tour.start(index)
        drv.draw(3)
        assert key in drv.app.item_rects, key
    gui.tour.active = False


def test_settings_round_trip_clamp_and_ignore_garbage(app):
    m = app.tool._model
    m.frequency, m.harmonic, m.show_fret, m.taus, m.frac1 = 33.0, 3, True, "1, 2", 0.25
    saved = json.loads(json.dumps(app.export_settings()))
    assert set(saved) == set(SETTINGS)
    other = make_app()
    other.restore_settings(saved)
    o = other.tool._model
    assert (o.frequency, o.harmonic, o.show_fret, o.taus, o.frac1) == (33.0, 3, True, "1, 2", 0.25)
    other.restore_settings(
        {"frequency": 1e9, "harmonic": "x", "show_fret": 3, "taus": 5, "frac1": float("nan")}
    )
    assert (
        o.frequency == 10000.0
        and o.harmonic == 3
        and o.show_fret is True
        and o.taus == "1, 2"
        and o.frac1 == 0.25
    )
    other.restore_settings("garbage")  # does not raise


def test_every_label_of_the_qt_spec_is_drawn(drv):
    """The Qt tool rendered phasor.view.json with AutoForm: each of its field labels is on screen (groups opened)."""
    spec = json.loads((PLUGIN / "gui/phasor.view.json").read_text())
    labels = []

    def walk(sections):
        for section in sections:
            if section.get("type") in ("value", "toggle") and section.get("label"):
                labels.append(
                    section["label"].replace("tau", "τ")
                )  # AutoForm shows "Donor tau0" as "Donor τ0"
            walk(section.get("sections", []))

    walk(spec["sections"])
    assert len(labels) == 19
    for title in ("Two-component line", "Mixing region", "Cursor"):
        unfold(drv, title)
    shown = set(drv.draw(3).strings)
    assert not [label for label in labels if label not in shown], [
        label for label in labels if label not in shown
    ]


# -- layout --------------------------------------------------------------------------------------------------------- #


@pytest.mark.parametrize("size", [BIG, SMALL])
@pytest.mark.parametrize("open_groups", [False, True])
def test_the_layout_is_clean(app, size, open_groups):
    drv = PhasorDriver(app, size)
    drv.draw(3)
    if open_groups:
        for t in ("Two-component line", "Mixing region", "Cursor"):
            unfold(drv, t)
        for name in ("show_fret", "show_component", "show_mixing", "show_cursor"):
            setattr(app.tool._model, name, True)
    painter = draw_clip(app, size)
    plot = app.item_rects[
        "plot"
    ]  # the whole plot window: its axis labels and legend are the plot's own
    problems = layout_problems(painter, size, ignore=[plot]) + clipped_texts(painter, ignore=[plot])
    assert not problems, problems[:6]
    assert {
        "Controls",
        "Reference lifetimes",
        "Phasor plot",
        "Frequency",
        "Effective f = 80 MHz",
    } <= set(painter.strings)
