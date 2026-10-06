"""The emtk saturation calculator equals the Qt tool: numbers, tables, summary, tooltips, layout, files and session.

``golden_qt.json`` holds what the Qt tool (``gui/tool.py``) computed for six states, written by
``okf/plugins/emtk-ports/fcs_saturation/scripts/capture_golden.py`` before any change to the Qt tool; the live Qt tool is also
constructed here for the cases that need it. The control -> test list is in the REPORT.md of the port.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.calculator.fcs_saturation_calc.gui.app import PLOT_TABS, SPEC, make_app
from chisurf.plugins.calculator.fcs_saturation_calc.gui.panel import TABS

from .driving import BIG, SMALL, clipped_texts, draw_clip, hermetic_env, layout_problems

GOLDEN = json.loads((Path(__file__).with_name("golden_qt.json")).read_text())
SERIES = (
    "fcs_curves_series",
    "fcs_residual_series",
    "volume_profile_series",
    "volume_power_series",
    "tau_d_power_series",
)


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def app():
    window = make_app(restore=False)
    yield window
    window.close()


def apply(model, settings):
    """Set what the Qt tool's setters took, in the same order."""
    for key, value in settings.items():
        setattr(model, key, value)


def plain(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", "", text)).strip()


# -- the numbers ----------------------------------------------------------------------------------------------- #


@pytest.mark.parametrize("state", list(GOLDEN))
def test_every_series_equals_what_the_qt_tool_computed(app, state):
    gold = GOLDEN[state]
    apply(app.model, gold["settings"])
    for source in SERIES:
        ours, theirs = getattr(app.model, source), gold["series"][source]
        assert [s["name"] for s in ours] == [s["name"] for s in theirs], source
        for a, b in zip(ours, theirs):
            assert np.allclose(a["x"], b["x"], rtol=1e-9, atol=0.0) and np.allclose(
                a["y"], b["y"], rtol=1e-9, atol=1e-12
            ), (state, source, a["name"])


@pytest.mark.parametrize("state", list(GOLDEN))
def test_the_scheme_rates_and_the_summary_equal_the_qt_tools(app, state):
    gold = GOLDEN[state]
    apply(app.model, gold["settings"])
    sat = app.model.saturation
    assert list(sat.state_labels) == gold["state_labels"]
    assert {k: float(p.value) for k, p in sat.dark.rates_by_name().items()} == pytest.approx(
        gold["dark"]
    )
    assert {k: float(p.value) for k, p in sat.exc.rates_by_name().items()} == pytest.approx(
        gold["exc"]
    )
    assert [float(p.value) for p in sat.brightness._brightness] == pytest.approx(gold["brightness"])
    assert app.model.info_text() == gold["info"]
    rows = app.panel.info_rows()
    assert rows, "the summary has rows"
    flat = " ".join(label + " " + value for label, value in rows)
    # every number of the Qt summary is shown
    for number in re.findall(r"\d+\.?\d*(?:e[+-]?\d+)?", plain(gold["info"])):
        assert number in flat + " " + app.panel.info_footer() + " " + app.panel.info_title(), number


@pytest.mark.parametrize("state", list(GOLDEN))
def test_the_tables_show_the_qt_tables_cells(app, state):
    gold = GOLDEN[state]
    apply(app.model, gold["settings"])
    panel = app.panel
    n = len(gold["state_labels"])
    for which, rows, prefix in (
        ("dark", panel.dark_rows(), "k"),
        ("exc", panel.exc_rows(), "sigma"),
    ):
        assert [r["state"] for r in rows] == gold["state_labels"]
        for i, row in enumerate(rows):
            for j in range(n):
                shown = row[f"c{j}"]
                if i == j:
                    assert shown is None  # the diagonal is derived, not a rate
                else:
                    assert shown == pytest.approx(gold[which].get(f"{prefix}{i + 1}_{j + 1}", 0.0))
    q = panel.brightness_rows()
    assert [r["value"] for r in q] == pytest.approx(gold["brightness"])
    assert [r["name"] for r in q] == [f"Q({s})" for s in gold["state_labels"]]
    optics = panel.optics_rows()
    symbols = {
        "P": "power",
        "λ_exc": "wavelength",
        "ε": "extinction",
        "τ_R1": "tau_R1",
        "τ_R2": "tau_R2",
    }
    assert [symbols.get(r["name"], r["name"]) for r in optics] == [p[0] for p in gold["parameters"]]
    for row, (name, value, fixed, bounds, bounds_on) in zip(optics, gold["parameters"]):
        assert row["value"] == pytest.approx(value)
        if row["_output"]:
            assert (
                row["fixed"] is None and row["lo"] is None and row["bounds"] is None
            )  # the Qt table leaves these blank
        else:
            assert (row["fixed"], row["bounds"], row["lo"], row["hi"]) == (
                fixed,
                bounds_on,
                bounds[0],
                bounds[1],
            )


@pytest.fixture
def qapp():
    QtWidgets = pytest.importorskip("qtpy.QtWidgets")
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield application  # held: a collected QApplication takes the Qt widgets down with it


def test_the_live_qt_tool_and_the_emtk_model_agree_on_every_preset(app, qapp):
    from chisurf.plugins.calculator.fcs_saturation_calc.gui.tool import SaturationCalculatorTool

    tool = SaturationCalculatorTool()
    try:
        for preset in tool.scheme_names():
            if preset == "Custom":
                continue
            tool.scheme_preset = preset
            app.model.scheme_preset = preset
            for source in SERIES:
                for a, b in zip(getattr(app.model, source), getattr(tool, source)):
                    assert np.allclose(a["y"], b["y"], rtol=1e-9, atol=1e-12), (preset, source)
        assert app.model.scheme_names() == tool.scheme_names() == list(tool.SCHEME_PRESETS)
        assert app.model.dye_names() == tool.dye_names()
    finally:
        tool.deleteLater()  # not close(): closing saves the session


def test_the_physical_anchors_of_the_guide_hold(app):
    """The worked example: no excitation gives the Gaussian, 0.05 mW 1.33x, 2 mW about 3.3x (guide steps 4 to 6)."""
    model = app.model
    for key, value in {
        "scheme_preset": "Rhodamine 6G (3-state, triplet)",
        "wavelength_nm": 488.0,
    }.items():
        setattr(model, key, value)
    sat = model.saturation
    sat._extinction.value, sat._w_r.value, sat._w_z.value, sat._D.value = 1e5, 250.0, 1000.0, 400.0

    def veff():
        model._on_changed()
        return model.volume_power_series[0]["y"], model.volume_power_series[0]["x"]

    model.power_mW = 0.0
    assert "1.000" in plain(model.info_text())
    model.power_mW = 0.05
    assert "1.3" in plain(model.info_text()).split("Volume expansion")[1][:30]
    model.power_mW = 2.0
    ratio = float(
        re.search(r"Volume expansion V_?eff/V_?0:\s*([\d.]+)", plain(model.info_text())).group(1)
    )
    assert 3.0 < ratio < 3.6


# -- the controls the Qt spec declared ------------------------------------------------------------------------ #


def qt_fields():
    spec = json.loads((Path(__file__).parents[1] / "gui" / "view.json").read_text())
    out = {}

    def walk(sections):
        for s in sections:
            if s.get("attr"):
                out[s["attr"]] = s
            walk(s.get("sections", []))

    walk(spec["sections"])
    return out


def our_fields():
    out = {}
    for block in SPEC.values():
        if not isinstance(block, dict):
            continue

        def walk(sections):
            for s in sections:
                if s.get("attr"):
                    out[s["attr"]] = s
                walk(s.get("sections", []))
                walk(s.get("items", []))

        walk(block.get("sections", []))
    return out


def test_every_field_of_the_qt_spec_is_in_the_emtk_spec_with_its_range_and_choices():
    qt, ours = qt_fields(), our_fields()
    for attr, section in qt.items():
        if section.get("type") not in ("value", "choice", "toggle"):
            continue
        assert attr in ours, f"{attr} of the Qt spec is not in the emtk spec"
        for key in ("kind", "maximum", "decimals"):
            if key in section and attr != "power_mW":
                assert ours[attr].get(key) == section[key], (attr, key)
        if "options" in section:
            assert ours[attr]["options"] == section["options"]
        if "options_source" in section:
            assert ours[attr].get("options_source") in (section["options_source"], "dye_options")
    assert (
        ours["power_mW"]["minimum"] == 0.0
    )  # the Qt setter takes zero although its slider starts at 0.001
    assert (
        ours["power_log"]["minimum"] == -3.0 and ours["power_log"]["maximum"] == 2.0
    )  # 0.001 .. 100 mW


def test_the_plot_tabs_draw_every_plot_of_the_qt_spec():
    qt_plots = {
        s["source"]
        for s in json.loads((Path(__file__).parents[1] / "gui" / "view.json").read_text())[
            "sections"
        ][0]["sections"]
        for s in _plots(s)
    }
    shown = {source for sources in PLOT_TABS.values() for source in sources}
    assert qt_plots == shown


def _plots(section):
    if section.get("type") == "plot":
        yield section
    for child in section.get("sections", []):
        yield from _plots(child)


def test_the_tabs_are_the_qt_dock_tabs_in_order():
    assert TABS == (
        "State diagram",
        "FCS curve",
        "Info",
        "Volume profile",
        "Volume(P)",
        "Diffusion time",
    )


# -- tooltips, descriptions, Qt-free ------------------------------------------------------------------------------ #


def walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item)


def test_every_section_button_and_column_of_the_spec_has_a_description(app):
    missing = []
    for node in walk(SPEC):
        kind = node.get("type")
        if kind in ("button_row", "toggle", "value", "choice", "table") and not node.get(
            "description"
        ):
            missing.append((kind, node.get("attr") or node.get("name")))
        if kind == "panel" and node.get("title") and not node.get("description"):
            missing.append(("panel", node["title"]))
        if "action" in node and not node.get("description"):
            missing.append(("button", node["action"]))
    for column in app.panel.matrix_columns() + app.panel.parameter_columns():
        if not column.get("description"):
            missing.append(("column", column["key"]))
    assert not missing, missing


@pytest.mark.parametrize("tab", TABS)
def test_every_control_has_a_tooltip(app, tab):
    from test.gui.emtk_port_parity import emtk_inventory

    app.select_tab(tab)
    inventory = emtk_inventory(app, BIG)
    assert inventory["controls_without_tooltip"] == []
    assert len(inventory["interactive"]) >= 12


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    verdict = qt_free("fcs_saturation")
    assert verdict["ok"], verdict["output"]


# -- the layout ------------------------------------------------------------------------------------------------------- #


@pytest.mark.parametrize("size", [BIG, SMALL])
@pytest.mark.parametrize("tab", TABS)
@pytest.mark.parametrize(
    "preset", ["Rhodamine 6G (3-state, triplet)", "Cyanine 5 (4-state, isomer + triplet)"]
)
def test_every_tab_draws_and_the_layout_is_clean(app, size, tab, preset):
    app.model.scheme_preset = preset
    app.select_tab(tab)
    painter = draw_clip(app, size)
    plots = [
        app.item_rects[k]
        for k in (
            "fcs_curves_series",
            "fcs_residual_series",
            "volume_profile_series",
            "volume_power_series",
            "tau_d_power_series",
            "state_scheme",
        )
        if k in app.item_rects
    ]
    problems = layout_problems(painter, size, ignore=plots) + clipped_texts(painter, ignore=plots)
    assert not problems, problems[:6]
    assert {
        "Compute",
        "Load scheme",
        "Save scheme",
        "Load session",
        "Save session",
        "Guide",
        "Help",
        "Scheme",
        "Laser power",
    } <= set(painter.strings)
    assert set(TABS) <= set(painter.strings)  # every tab button is whole
    state_labels = app.model.saturation.state_labels
    assert set(state_labels) <= set(
        painter.strings
    )  # the tables (and the diagram) name every state


def test_a_six_state_scheme_draws_in_the_small_window(app):
    app.model.saturation.n_states = 6
    app.model._on_changed()
    for tab in TABS:
        app.select_tab(tab)
        painter = draw_clip(app, SMALL)
        problems = layout_problems(
            painter,
            SMALL,
            ignore=[
                app.item_rects[k]
                for k in app.item_rects
                if k.endswith("_series") or k == "state_scheme"
            ],
        )
        assert not problems, (tab, problems[:4])


def test_the_plots_have_titles_axes_and_the_data_is_framed(app):
    from emtk.testing import RecordingPainter

    for tab, labels in {
        "FCS curve": ("FCS Saturation Effect", "τ (ms)", "G(τ)"),
        "Volume profile": ("Radial Spatial Volume Profiles", "Radial Position r (nm)"),
        "Volume(P)": ("Volume Expansion vs Laser Power", "Power (mW)", "V_eff / V_0"),
        "Diffusion time": ("Diffusion Time vs Laser Power", "Power (mW)", "τ_D (ms)"),
    }.items():
        app.select_tab(tab)
        painter = draw_clip(app, BIG)
        for label in labels:
            assert label in painter.strings, (tab, label)
        ticks = [s for s in painter.strings if re.fullmatch(r"-?[\d.]+(e[+-]?\d+)?", s)]
        assert len(ticks) >= 4, (tab, ticks)


# -- files and session ---------------------------------------------------------------------------------------------- #


def test_a_scheme_saved_and_loaded_gives_the_same_curves(app, tmp_path):
    app.model.scheme_preset = "Cyanine 5 (4-state, isomer + triplet)"
    app.model.power_mW = 0.7
    before = [np.array(s["y"]) for s in app.model.fcs_curves_series]
    app.model.save_scheme_to_file(str(tmp_path / "cy5.json"))
    other = make_app(restore=False)
    try:
        other.model.power_mW = 0.7
        other.model.load_scheme_from_file(str(tmp_path / "cy5.json"))
        after = [np.array(s["y"]) for s in other.model.fcs_curves_series]
        assert other.model.saturation.n_states == 4
        for a, b in zip(before, after):
            assert np.allclose(a, b, rtol=1e-9)
    finally:
        other.close()


def test_the_session_round_trips_through_the_settings_file(app, tmp_path):
    app.model.scheme_preset = "Two-state (ground + excited)"
    app.model.power_mW = 1.25
    app.model.wavelength_nm = 561.0
    app.model.normalize_fcs = True
    app.model.include_bunching = False
    app.model.show_power_profile = False
    app.save_session()
    path = Path(app.model.get_user_settings_path())
    assert path.is_file() and str(tmp_path) in str(
        path
    )  # the temporary settings folder, never ~/.chisurf
    saved = json.loads(path.read_text())
    assert (
        saved["power_mW"] == 1.25
        and saved["wavelength_nm"] == 561.0
        and saved["normalize_fcs"] is True
    )
    other = make_app(restore=True)
    try:
        m = other.model
        assert (
            m.power_mW,
            m.wavelength_nm,
            m.normalize_fcs,
            m.include_bunching,
            m.show_power_profile,
        ) == (1.25, 561.0, True, False, False)
        assert m.saturation.n_states == 2
    finally:
        other.close()


def test_the_real_user_settings_are_never_touched(app):
    """Saving a session and closing the window write into the temporary settings folder, not the account's ~/.chisurf."""
    import os
    import pwd

    real = (
        Path(pwd.getpwuid(os.getuid()).pw_dir)
        / ".chisurf"
        / "plugins"
        / "fcs_saturation_calc"
        / "settings.json"
    )
    before = real.stat().st_mtime_ns if real.exists() else None
    app.model.power_mW = 3.0
    app.save_session()
    app.close()
    assert (real.stat().st_mtime_ns if real.exists() else None) == before
    assert Path(app.model.get_user_settings_path()) != real
