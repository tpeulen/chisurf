"""The native FRET calculator against the values the Qt tool showed, and against the backend services.

Hermetic: settings in a temporary folder, no files, no network. The Qt tool is deleted: its numbers
are frozen in ``okf/plugins/emtk-ports/fret_calculator/qt_values.json`` and pinned below. Every edit
is typed into the real emtk field (click, type, Enter) so that the spec's ``call`` wiring is what is
tested.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
import pytest
from emtk import keys
from emtk.testing import RecordingPainter

from chisurf.plugins.calculator.fret_calculator.backend import services
from chisurf.plugins.calculator.fret_calculator.gui.app import FretCalcApp, make_app
from chisurf.plugins.calculator.fret_calculator.gui.model import (
    FretCalculatorModel,
    HeteroFretModel,
    HomoFretModel,
)
from chisurf.plugins.emtk_layout import action_caption

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
SIZE = (1200, 800)
SMALL = (800, 600)


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))


@pytest.fixture
def app():
    return make_app()


def draw(app, size=SIZE, frames=3):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def click(app, rect, size=SIZE, fx=0.5):
    x, y, w, h = rect
    app.press(x + w * fx, y + h / 2)
    draw(app, size, frames=1)
    app.release()
    draw(app, size, frames=1)


def press(app, name, size=SIZE):
    draw(app, size)
    click(app, app.target_rect(name), size)


def type_into(app, name, text, size=SIZE):
    """Click the field, type *text*, press Enter: the way a user edits a value."""
    draw(app, size)
    click(app, app.active.form.rects[name], size, fx=0.3)
    assert app.io.want_capture_keyboard, f"{name} did not take the keyboard"
    app.key(0x41, "a", 0x04000000)  # select all
    draw(app, size, frames=1)
    for ch in text:
        app.key(ord(ch), ch)
        draw(app, size, frames=1)
    app.key(keys.KEY_RETURN, "\r")
    draw(app, size, frames=2)


def edit(app, name, value):
    """Set a field (or the toggle) through the UI."""
    if name == "use_chi":
        draw(app)
        click(app, app.active.form.rects["use_chi"])
    else:
        type_into(app, name, repr(float(value)))


def hetero_state(m):
    return {k: getattr(m, k) for k in ("tau0", "R0", "tau", "R", "sigma", "E", "kFRET", "use_chi")}


def homo_state(m):
    return {
        k: getattr(m, k)
        for k in ("tau0", "R0", "t_RM", "rho", "sigma", "k_homo", "R_DA", "use_chi")
    }


# ── 1. numbers equal the frozen Qt values and the backend ----------------------------------------------- #

def test_the_numbers_the_qt_tool_showed_are_pinned(app):
    """Values read off the Qt window (okf/plugins/emtk-ports/fret_calculator/qt_values.json)."""
    m = app.model.hetero
    assert (m.tau, m.E, m.kFRET) == (1.7599, 0.560037, 0.31823)
    for attr, value in (("tau0", 3.5), ("R0", 60.0), ("R", 55.0), ("sigma", 8.0)):
        edit(app, attr, value)
    edit(app, "use_chi", True)
    assert (m.tau, m.E, m.kFRET) == (1.4182, 0.594792, 0.419391)
    edit(app, "E", 0.8)
    assert (m.R, m.tau, m.kFRET) == (47.62, 0.7, 1.143429)
    app.select_tab(1)
    h = app.model.homo
    for attr, value in (("tau0", 2.5), ("R0", 55.0), ("rho", 20.0), ("t_RM", 1.5)):
        edit(app, attr, value)
    assert (h.k_homo, h.R_DA) == (0.308333, 57.44)
    edit(app, "R_DA", 45.0)
    assert (h.t_RM, h.k_homo) == (0.3681, 1.333402)


def test_native_values_equal_the_backend_services_not_only_the_qt_tool():
    m = HeteroFretModel()
    m.R = 55.0
    m.compute_forward()
    expect = services.fret_compute_handler(R=55.0, R0=52.0, tau0=4.0, kappa2=0.667, sigma=6.0)[
        "result"
    ]
    assert m.E == pytest.approx(expect["E"], abs=5e-7)
    assert m.kFRET == pytest.approx(expect["kFRET"], abs=5e-7)
    assert m.tau == pytest.approx(expect["tau_DA"], abs=5e-5)
    # physics: sigma = 0 gives the textbook E = 1 / (1 + (R/R0)^6) and tau = tau0 (1 - E)
    m.sigma = 0.1
    m.R = 52.0
    m.compute_forward()
    assert m.E == pytest.approx(0.5, abs=1e-3)
    assert m.tau == pytest.approx(4.0 * (1.0 - m.E), abs=1e-3)
    # the inverse routes round-trip a single distance
    m.sigma = 0.1
    m.R = 47.0
    m.compute_forward()
    e, k = m.E, m.kFRET
    for route, field in ((m.from_efficiency, e), (m.from_rate, k)):
        m.R = 20.0
        route()
        assert m.R == pytest.approx(47.0, abs=0.2)


def test_homo_forward_and_backmap_are_inverse_on_the_time(app):
    h = app.model.homo
    t_rm = h.t_RM
    h.compute_forward()
    r_da = h.R_DA
    h.t_RM = 5.0
    h.backmap()
    assert h.R_DA == r_da
    assert h.t_RM == pytest.approx(t_rm, rel=2e-3)


# ── 2. actions, errors -------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("attr", "value", "message"),
    [
        ("E", 0.0, "FRET from efficiency failed"),
        ("E", 1.0, "FRET from efficiency failed"),
        ("tau", 0.0, "FRET from lifetime failed"),
        ("kFRET", 0.0, "FRET from rate failed"),
    ],
)
def test_a_failed_inverse_says_so_keeps_the_other_fields_and_the_next_edit_clears_it(
    app, attr, value, message
):
    m = app.model.hetero
    before = hetero_state(m)
    edit(app, attr, value)
    assert m.status.startswith(message)
    assert message in " ".join(draw(app).strings)
    kept = {k: v for k, v in hetero_state(m).items() if k not in (attr,)}
    assert kept == {k: v for k, v in before.items() if k not in (attr,)}
    edit(app, "R", 40.0)
    assert m.status == ""
    assert message not in " ".join(draw(app).strings)


def test_a_lifetime_longer_than_the_donor_only_lifetime_is_an_error_not_an_exception(app):
    m = app.model.hetero
    edit(app, "tau", 9.0)  # tau_DA > tau0: no distance (the backend raises a complex-number error)
    assert m.status.startswith("FRET from lifetime failed")
    assert m.tau == 9.0 and m.R == 50.0


def test_homo_with_no_finite_distance_keeps_the_fields_and_is_not_an_error(app):
    app.select_tab(1)
    h = app.model.homo
    before = homo_state(h)
    edit(app, "R_DA", 0.0)
    assert h.status == ""
    assert (h.R_DA, h.t_RM, h.k_homo) == (0.0, before["t_RM"], before["k_homo"])


def test_a_failing_backend_is_reported_for_every_route():
    class Broken:
        def __getattr__(self, name):
            return lambda **kwargs: {"ok": False, "error": "backend down"}

    model = FretCalculatorModel(Broken())
    assert model.hetero.status == "FRET from distance failed: backend down"
    assert model.homo.status == "Homo-FRET rate failed: backend down"
    model.homo.backmap()
    assert model.homo.status == "Homo-FRET back-map failed: backend down"
    model.hetero.from_rate()
    assert model.hetero.status == "FRET from rate failed: backend down"
    assert model.hetero.R == 50.0  # nothing was written


def test_typed_garbage_is_ignored_and_out_of_range_values_are_clamped(app):
    m = app.model.hetero
    type_into(app, "R", "abc")
    assert m.R == 50.0 and m.status == ""
    type_into(app, "R", "5000000")
    assert m.R == 9999.0
    type_into(app, "R", "-3")
    assert m.R == 0.1
    type_into(app, "E", "7")
    assert m.E == 1.0 and m.status.startswith("FRET from efficiency failed")
    type_into(app, "R", "55 A")  # the unit the field shows is accepted back
    assert m.R == 55.0


def test_the_arrows_step_the_value_and_run_the_handler(app):
    m = app.model.hetero
    draw(app)
    r, e = m.R, m.E
    x, y, w, h = app.active.form.rects["R.stepper"]
    app.press(x + w / 2, y + h * 0.25)  # upper half = up
    draw(app, frames=1)
    app.release()
    draw(app, frames=2)
    assert m.R > r and m.E != e


def test_the_chi_toggle_recomputes_and_swaps_the_solid_curve(app):
    m = app.model.hetero
    e = m.E
    assert {s["name"]: s["style"] for s in m.distance_plot_series()} == {
        "Gaussian": "solid",
        "chi": "dash",
    }
    edit(app, "use_chi", True)
    assert m.use_chi and m.E != e
    assert {s["name"]: s["style"] for s in m.distance_plot_series()} == {
        "Gaussian": "dash",
        "chi": "solid",
    }
    app.select_tab(1)
    h = app.model.homo
    t = h.t_RM
    edit(app, "use_chi", True)  # homo: the toggle only changes the plot
    assert h.use_chi and h.t_RM == t
    assert {s["name"]: s["style"] for s in h.aniso_time_plot_series()} == {
        "Gaussian": "dash",
        "chi": "solid",
    }


def test_k_homo_is_an_output_it_cannot_be_typed_into(app):
    app.select_tab(1)
    draw(app)
    k = app.model.homo.k_homo
    click(app, app.active.form.rects["k_homo"], fx=0.3)
    app.key(ord("9"), "9")
    app.key(keys.KEY_RETURN, "\r")
    draw(app, frames=2)
    assert app.model.homo.k_homo == k


def test_the_tab_bar_switches_tabs(app):
    draw(app)
    assert app.active_tab == 0
    click(app, app.item_rects["tab_homofret"])
    assert app.active_tab == 1 and "Homo-FRET parameters" in " ".join(draw(app).strings)
    click(app, app.item_rects["tab_heterofret"])
    assert app.active_tab == 0 and "FRET parameters" in " ".join(draw(app).strings)


def test_a_dropped_file_says_the_calculator_has_no_file_input(app):
    assert app.files_dropped([]) is False and app.model.hetero.status == ""
    assert app.on_files_dropped(["/tmp/run.ptu"]) is True
    assert app.model.hetero.status == "The FRET Calculator takes no dropped files."
    assert "takes no dropped files" in " ".join(draw(app).strings)
    app.select_tab(1)
    assert app.on_paths_dropped(["/tmp/x"]) and "takes no dropped files" in app.model.homo.status
    edit(app, "t_RM", 2.0)
    assert app.model.homo.status == ""
    # the Qt host reaches the drop through the same hooks
    assert callable(getattr(app, "files_dropped")) and callable(getattr(app, "on_paths_dropped"))


# ── 3. spec, tooltips, drawing ------------------------------------------------------------------ #


def _walk(sections):
    for section in sections:
        yield section
        yield from _walk(section.get("sections", []))


@pytest.mark.parametrize(
    ("spec_file", "model"),
    [("fret.view.json", HeteroFretModel), ("homofret.view.json", HomoFretModel)],
)
def test_every_spec_key_exists_on_the_model(spec_file, model):
    spec = json.loads((GUI / spec_file).read_text(encoding="utf-8"))
    m = model()
    found = set()
    for section in _walk(spec["sections"]):
        for key in ("attr", "call", "source"):
            if section.get(key):
                assert hasattr(m, section[key]), (key, section[key])
                found.add(section[key])
        if section.get("call"):
            assert callable(getattr(m, section["call"]))
    assert {"tau0", "R0", "R", "sigma", "use_chi"} <= found or {
        "tau0",
        "R0",
        "t_RM",
        "rho",
    } <= found


def test_every_field_has_the_qt_limits_and_decimals():
    """Spec ranges equal the Qt AutoForm spec (HEAD) and the model's result rounding."""
    for spec_file, model in (
        ("fret.view.json", HeteroFretModel),
        ("homofret.view.json", HomoFretModel),
    ):
        spec = json.loads((GUI / spec_file).read_text(encoding="utf-8"))
        fields = {s["attr"]: s for s in _walk(spec["sections"]) if s.get("type") == "value"}
        for attr, (decimals, lo, hi) in {**model.input_fields, **model.result_fields}.items():
            assert (fields[attr]["decimals"], fields[attr]["minimum"], fields[attr]["maximum"]) == (
                decimals,
                lo,
                hi,
            ), attr


@pytest.mark.parametrize("size", [SIZE, SMALL])
@pytest.mark.parametrize("tab", [0, 1])
def test_draws_the_form_and_both_plots_at_both_sizes(size, tab):
    app = make_app()
    app.select_tab(tab)
    strings = " ".join(draw(app, size).strings)
    labels = (
        (
            "Lifetime D0",
            "Förster R0",
            "Distance DA",
            "Lifetime DA",
            "Efficiency",
            "kFRET",
            "σ",
            "χ distribution",
            "Distance distribution",
            "Rate-constant distribution",
            "HeteroFRET",
            "HomoFRET",
        )
        if tab == 0
        else (
            "τ0",
            "R0",
            "t_RM",
            "ρ",
            "k_homo",
            "R_DA",
            "σ",
            "χ distribution",
            "Distance distribution",
            "Anisotropy decay time",
            "HeteroFRET",
            "HomoFRET",
        )
    )
    for label in labels:
        assert label in strings, (tab, size, label)
    assert "Gaussian" in strings and "chi" in strings  # legends: the plots drew curves
    assert math.isfinite(app.model.hetero.E)


def test_draws_after_every_edit_even_at_the_ends_of_the_ranges(app):
    for attr, value in (
        ("R", 0.1),
        ("R", 9999.0),
        ("sigma", 999.0),
        ("sigma", 0.1),
        ("R0", 999.0),
        ("tau0", 0.001),
    ):
        edit(app, attr, value)
        assert draw(app).strings
        for series in app.model.hetero.distance_plot_series() + app.model.hetero.rate_plot_series():
            assert np.isfinite(series["x"]).all() and np.isfinite(series["y"]).all()


def test_no_emoji_in_the_native_labels(app):
    """No pictogram except the shared Help/Guide vocabulary (chisurf.plugins.emtk_layout.ACTIONS)."""
    shared = {action_caption("guide"), action_caption("help")}
    for tab in (0, 1):
        app.select_tab(tab)
        strings = draw(app).strings
        own = [text for text in strings if text not in shared]
        assert all(ord(ch) < 0x2190 or ch in "τΔρσΣχ" for text in own for ch in text), strings
        assert shared <= set(strings)


def test_every_control_has_a_tooltip(app):
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inventory = emtk_inventory(build_emtk_app("fret_calculator"))
    assert inventory["controls_without_tooltip"] == []
    labels = {row["label"] for row in inventory["interactive"]}
    assert {
        action_caption("guide"),
        action_caption("help"),
        "R",
        "E",
        "tau0",
        "R0",
        "tau",
        "kFRET",
        "sigma",
        "χ distribution",
    } <= labels
    app.select_tab(1)
    assert emtk_inventory(app)["controls_without_tooltip"] == []
    for spec_file in ("fret.view.json", "homofret.view.json"):
        spec = json.loads((GUI / spec_file).read_text(encoding="utf-8"))
        for section in _walk(spec["sections"]):
            if section.get("type") in ("value", "choice", "toggle", "plot", "panel"):
                assert section.get("description"), section.get("attr") or section.get("title")


# ── 4. guide and help ---------------------------------------------------------------------------- #


def test_guide_steps_point_at_controls_the_app_draws(app):
    from chisurf.emtk.help_guide import EmTkGuidedTour

    steps = json.loads((GUI / "guide.json").read_text(encoding="utf-8"))["steps"]
    assert [s["title"] for s in steps if s.get("await")] == [
        "Donor lifetime",
        "Förster radius",
        "Distance",
        "Inverse calculation",
        "Distance distribution",
        "HomoFRET",
        "Migration time",
        "Back-map",
    ]
    app.tour.start()
    for index, step in enumerate(steps):
        app.tour.step_idx = index
        app.tour._notify_change()  # selects the tab the step lives on
        draw(app)
        name = EmTkGuidedTour._target_key(step["target"])
        assert app.target_rect(name), f"{step['title']}: nothing drawn for {name!r}"
    assert not any(re.search(r"[\U0001F300-\U0001FAFF]", s["text"]) for s in steps)


def test_the_tour_waits_for_the_user_and_walks_through_both_tabs(app):
    app.tour.start()
    draw(app)
    assert app.tour.awaiting and app.tour.step_idx == 0
    edit(app, "tau0", 3.0)
    assert not app.tour.awaiting
    app.tour.next()
    edit(app, "R0", 50.0)
    app.tour.next()
    edit(app, "R", 45.0)
    app.tour.next()
    edit(app, "E", 0.6)
    app.tour.next()
    edit(app, "use_chi", True)
    app.tour.next()
    draw(app)
    assert app.tour.awaiting and app.active_tab == 0  # waits for the HomoFRET tab, never presses it
    click(app, app.item_rects["tab_homofret"])
    assert not app.tour.awaiting and app.active_tab == 1
    app.tour.next()
    draw(app)
    assert app.active_tab == 1 and app.tour.awaiting
    edit(app, "t_RM", 2.0)
    app.tour.next()
    edit(app, "R_DA", 50.0)
    app.tour.next()
    draw(app)
    assert app.tour.step_idx == len(app.tour.steps) - 1 and not app.tour.awaiting


def test_the_tour_hides_nothing_when_it_starts_on_the_other_tab(app):
    app.select_tab(1)
    app.tour.start()
    draw(app)
    assert app.active_tab == 0  # step 1 lives on HeteroFRET and brings the window there


def test_guide_and_help_buttons_open_the_tour_and_the_help(app):
    press(app, "guide")
    assert app.tour.active
    app.tour.stop()
    press(app, "help")
    assert app.help_window.open and draw(app).strings


def test_help_text_is_plain_and_its_links_are_live(app):
    text = (GUI / "help.md").read_text(encoding="utf-8")
    assert "**" not in text and "`" not in text  # the native help window shows Markdown marks raw
    assert (
        "slider" not in text.lower()
    )  # the Qt-era text described sliders this window does not have
    links = re.findall(r"\]\((docs/[^)#]+)\)", text)
    assert links and all((REPO / link).is_file() for link in links)
    app.help_window.show()
    assert "FRET calculator" in " ".join(draw(app).strings) or draw(app).strings


# ── 5. persistence, manifest, no Qt, host ---------------------------------------------------------- #


def test_settings_round_trip_and_invalid_values_are_ignored(app):
    edit(app, "tau0", 3.5)
    edit(app, "R", 55.0)
    edit(app, "use_chi", True)
    app.select_tab(1)
    edit(app, "t_RM", 2.5)
    edit(app, "rho", 12.0)
    saved = json.loads(json.dumps(app.export_settings()))
    assert (
        saved["tab"] == 1 and saved["hetero"]["tau0"] == 3.5 and saved["hetero"]["use_chi"] is True
    )
    assert set(saved["homo"]) == {"tau0", "R0", "t_RM", "rho", "sigma", "use_chi"}
    other = make_app()
    other.restore_settings(saved)
    assert other.export_settings() == saved
    assert other.active_tab == 1
    assert (
        other.model.hetero.E == app.model.hetero.E
        and other.model.homo.k_homo == app.model.homo.k_homo
    )
    other.restore_settings(
        {
            "hetero": {"tau0": "x", "R0": float("nan"), "R": 1e9, "use_chi": "yes"},
            "homo": ["no"],
            "tab": 7,
        }
    )
    assert (
        other.model.hetero.tau0 == 3.5 and other.model.hetero.R0 == 52.0
    )  # unusable values change nothing
    assert (
        other.model.hetero.R == 55.0
        and other.model.hetero.use_chi is True
        and other.active_tab == 1
    )
    other.restore_settings("garbage")
    assert draw(other).strings


def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("fret_calculator")
    assert result["ok"], result["output"]


def test_the_manifest_opens_the_native_app_and_the_hub_kwargs_are_accepted():
    manifest = json.loads((HERE.parent / "manifest.json").read_text(encoding="utf-8"))
    assert (
        manifest["entrypoints"]["emtk"]
        == "chisurf.plugins.calculator.fret_calculator.gui.app:make_app"
    )
    assert isinstance(make_app(restore=False), FretCalcApp)


def test_the_app_runs_on_the_same_models_as_the_backend():
    app = make_app(restore=False)
    assert app.hetero.model is app.model.hetero
    app.hetero.model.R = 55.0
    app.hetero._compute_forward()
    assert app.hetero.model.E == pytest.approx(
        services.fret_compute_handler(R=55.0, R0=52.0, tau0=4.0, kappa2=0.667, sigma=6.0)["result"][
            "E"
        ],
        abs=5e-7,
    )
