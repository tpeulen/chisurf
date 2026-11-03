"""The FRET line generator: the mixture, the sweep targets, the computed lines, the CSV, the collection.

The lines are checked against the documented formula recomputed here: a Gaussian distance distribution
``p(R) ~ exp(-(R - R_DA)^2 / 2 sigma^2)`` weighted at the nodes of the engine's distance grid
(``geomspace(1, 130, 96)`` Å, normalised), each distance giving the donor lifetime
``tau(R) = tau_D0 / (1 + (R0 / R)^6)``; ``<tau>_x = sum p tau``, ``<tau>_F = sum p tau^2 / <tau>_x`` and
``E = 1 - <tau>_x / tau_D0``. A mixture adds the components' spectra weighted by their fractions.

Hermetic: settings, MMFDB and HOME are temporary folders, the CSV goes to ``tmp_path``, no network. A module guard
fails the run if anything appears in the real ``~/.chisurf`` other than its ``logs`` folder.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.core.project_browser.test.driving import (
    clipped_texts,
    draw_clip,
    layout_problems,
)
from chisurf.plugins.fret_line.gui.app import FRETLineApp, make_app
from chisurf.plugins.fret_line.gui.model import NO_NDX_WINDOW, PALETTE, FretLineModel

HERE = Path(__file__).parent
PLUGIN = HERE.parent
SPEC = PLUGIN / "gui/fret_line_emtk.view.json"
BIG, SMALL = (1200, 800), (800, 600)
REAL_CHISURF = Path(os.path.expanduser("~")) / ".chisurf"
#: The distance grid of the Gaussian FRET model's lifetime spectrum (Å).
R_GRID = np.geomspace(1.0, 130.0, 96)


def _snapshot(root: Path) -> dict:
    out = {}
    if root.exists():
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root)
            if (rel.parts and rel.parts[0] in ("logs", "cache")) or "__pycache__" in rel.parts:
                continue
            stat = path.stat()
            out[str(rel)] = (stat.st_size, stat.st_mtime_ns)
    return out


@pytest.fixture(scope="module", autouse=True)
def real_chisurf_untouched():
    before = _snapshot(REAL_CHISURF)
    yield
    assert _snapshot(REAL_CHISURF) == before


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    for name in ("settings", "mmfdb", "home"):
        (tmp_path / name).mkdir()
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def draw(app, size=BIG, frames=3):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


@pytest.fixture
def model():
    m = FretLineModel()
    yield m
    m.close()


# -- the documented formula ----------------------------------------------------------------------------------------- #


def gaussian_spectrum(r_mean, sigma=6.0, r0=52.0, tau_d0=4.0):
    """Amplitudes and lifetimes of a Gaussian distance distribution on the model's grid."""
    p = np.exp(-0.5 * ((R_GRID - r_mean) / sigma) ** 2)
    return p / p.sum(), tau_d0 / (1.0 + (r0 / R_GRID) ** 6)


def averaged(p, tau):
    tau_x = float(np.sum(p * tau))
    return tau_x, float(np.sum(p * tau * tau)) / tau_x


def expected_line(spectra, tau_d0=4.0):
    tau_x, tau_f = np.array([averaged(p, t) for p, t in spectra]).T
    return {"tau_x": tau_x, "tau_f": tau_f, "e_fret": 1.0 - tau_x / tau_d0}


def line_arrays(result):
    return {k: np.asarray(result[k]) for k in ("tau_f", "tau_x", "e_fret", "parameter_values")}


def assert_line(a, expected):
    for key, value in expected.items():
        np.testing.assert_allclose(a[key], value, rtol=1e-4, atol=1e-5, err_msg=key)


# -- the defaults and the mixture --------------------------------------------------------------------------------------- #


def test_one_gaussian_component_and_a_linear_sweep_by_default(model):
    assert (model.minimum, model.maximum, model.n_points, model.log_scale) == (0.0, 100.0, 100, False)
    assert model.weight == 1.0
    assert [c["model_name"] for c in model.components] == ["FRET: FD (Gaussian)"]
    assert {"FRET: FD (Gaussian)", "FRET: FD (Worm-like chain)", "FRET: FD (Discrete)", "Lifetime"} <= set(
        model.model_labels()
    )


def test_components_are_numbered_and_the_last_one_cannot_be_removed(model):
    model.add_component()
    rows = model.component_rows()
    assert [(r["name"], r["model"], r["weight"]) for r in rows] == [
        ("C0", "FRET: FD (Gaussian)", 1.0),
        ("C1", "FRET: FD (Gaussian)", 1.0),
    ]
    model.remove_component()
    model.remove_component()  # the last one stays
    assert len(model.components) == 1 and not model.enabled("remove_component")


def test_a_changed_weight_survives_a_model_change(model):
    model.weight = 2.5
    assert model.components[0]["weight"] == 2.5
    model.model_label = "Lifetime"
    assert model.components[0]["model_name"] == "Lifetime"
    assert model.components[0]["weight"] == 2.5


# -- the sweep targets and the lines --------------------------------------------------------------------------------------- #

NUISANCE = ("rho0", "b0", "r0", "g", "l1", "l2", "scatter", "background", "xDOnly")


@pytest.mark.parametrize("two", [False, True])
@pytest.mark.parametrize("all_parameters", [False, True])
def test_sweep_targets_are_the_component_parameters_and_the_fractions(model, two, all_parameters):
    if two:
        model.add_component()
    model.show_all_parameters = all_parameters
    labels = model.sweep_labels()
    names = {label.split(" · ")[-1] for label in labels if not label.startswith("fraction")}
    assert {"RDA0", "s0", "R0", "tD0", "kappa2"} <= names
    assert bool(names & set(NUISANCE)) is all_parameters
    prefixes = ["C0 [FRET: FD (Gaussian)] · "] + (["C1 [FRET: FD (Gaussian)] · "] if two else [])
    for prefix in prefixes:
        assert any(label.startswith(prefix) for label in labels)
    fractions = [label for label in labels if label.startswith("fraction")]
    assert fractions == (
        ["fraction · C0 [FRET: FD (Gaussian)]", "fraction · C1 [FRET: FD (Gaussian)]"] if two else []
    )


def test_the_filter_keeps_the_targets_containing_the_text_case_insensitively(model):
    model.sweep_filter = "rda"
    assert model.sweep_labels() and all("rda" in s.casefold() for s in model.sweep_labels())
    model.sweep_filter = "no such target"
    assert model.sweep_labels() == []


def test_the_static_line_follows_the_gaussian_distance_formula(model):
    model.minimum, model.maximum = 20.0, 120.0
    line = model.add_line()
    a = line_arrays(line["result"])
    np.testing.assert_allclose(a["parameter_values"], np.linspace(20.0, 120.0, 100))
    assert_line(a, expected_line([gaussian_spectrum(r) for r in a["parameter_values"]]))
    assert line["sweep_label"] == "C0 [FRET: FD (Gaussian)] · RDA0" and line["name"] == "Line 1"
    assert line["color"] == PALETTE[0]
    assert line["components"] == "C0=FRET: FD (Gaussian)(w=1)"


def test_a_log_sweep_and_a_user_tau_d0_follow_the_formula(model):
    model.minimum, model.maximum, model.log_scale, model.tau_d0, model.n_points = 20.0, 120.0, True, 3.5, 40
    line = model.add_line()
    a = line_arrays(line["result"])
    np.testing.assert_allclose(a["parameter_values"], np.geomspace(20.0, 120.0, 40))
    assert_line(a, expected_line([gaussian_spectrum(r) for r in a["parameter_values"]], tau_d0=3.5))
    assert line["log"] is True


def test_the_fraction_line_mixes_the_two_spectra(model):
    model.add_component()
    # the second component at another distance
    comp = model.components[1]["model"]
    next(p for p in comp.parameters_all if p.canonical_id == "distance.mean.0").value = 70.0
    model.sweep_label = next(
        label for label in model.sweep_labels() if label.startswith("fraction · C0")
    )
    model.minimum, model.maximum = 0.0, 1.0
    line = model.add_line()
    a = line_arrays(line["result"])
    (p0, tau), (p1, _) = gaussian_spectrum(50.0), gaussian_spectrum(70.0)
    assert_line(a, expected_line([(f * p0 + (1 - f) * p1, tau) for f in a["parameter_values"]]))
    assert line["sweep_label"] == "fraction · C0 [FRET: FD (Gaussian)]"


def test_the_editors_static_kappa2_moves_the_line_and_dynamic_kappa2_brings_it_back():
    """The editor's dynamic / static κ² radios set the orientation mode of the selected component.

    Pressed as a user presses it (at its drawn rectangle): static κ² averages the transfer over a static
    isotropic κ² distribution, which lowers E at short distances well away from the dynamic line; dynamic κ²
    brings the line of the formula back.
    """
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

    app = FRETLineApp()
    try:
        app.show_advanced("editor")
        drv = Driver(app, BIG)
        drawn = {t[5] for t in drv.draw(4).texts}
        assert {"dynamic κ²", "static κ²"} <= drawn
        app.model.minimum, app.model.maximum = 20.0, 120.0
        dynamic = expected_line([gaussian_spectrum(r) for r in np.linspace(20.0, 120.0, 100)])
        drv.click(app.form.rects["kappa2.static"])
        drv.draw(2)
        assert app.model.selected["model"].orientation_parameter.mode == "slow"
        line = app.model.add_line()
        a = line_arrays(line["result"])
        assert line["sweep_label"] == "C0 [FRET: FD (Gaussian)] · RDA0"
        assert np.max(np.abs(a["e_fret"] - dynamic["e_fret"])) > 0.1
        assert a["e_fret"][0] < dynamic["e_fret"][0]
        drv.click(app.form.rects["kappa2.dynamic"])
        drv.draw(2)
        assert app.model.selected["model"].orientation_parameter.mode == "fast"
        assert_line(line_arrays(app.model.add_line()["result"]), dynamic)
    finally:
        app.close()


def test_a_sweep_leaves_the_users_parameters_where_they_were(model):
    parameter = next(
        p
        for p in model.components[0]["model"].parameters_all
        if p.canonical_id == "distance.mean.0"
    )
    parameter.value = 55.0
    model.minimum, model.maximum = 20.0, 120.0
    model.add_line()
    assert parameter.value == 55.0


def test_a_failing_compute_says_why_and_adds_no_line(model):
    model.log_scale, model.minimum = True, 0.0
    assert model.add_line() is None and not model.lines
    assert model.dialog_title == "Compute error"
    assert model.dialog_text == "Log-scale sweep requires param_min and param_max > 0."
    assert "Log-scale" in model.message


# -- the collection ---------------------------------------------------------------------------------------------------------- #


def three_lines(model):
    model.minimum, model.maximum = 20.0, 120.0
    for _ in range(3):
        model.add_line()


def test_visibility_remove_and_clear(model):
    three_lines(model)
    assert [l["color"] for l in model.lines] == list(PALETTE[:3])
    model.hide_all()
    assert [l["visible"] for l in model.lines] == [False] * 3
    model.show_all()
    assert all(l["visible"] for l in model.lines)
    model.line_index = 1
    model.remove_line()
    assert [l["name"] for l in model.lines] == ["Line 1", "Line 3"]
    model.remove_line()  # nothing selected any more: the last one goes
    model.line_index = -1
    model.clear_lines()
    assert model.lines == []
    assert not any(
        model.enabled(a)
        for a in ("save_csv", "push", "show_all", "hide_all", "remove_line", "clear_lines")
    )
    model.add_line()
    assert model.lines[0]["name"] == "Line 4"  # the numbering continues


def test_the_csv_holds_every_point_of_every_line(model, tmp_path):
    model.add_component()
    model.minimum, model.maximum = 20.0, 120.0
    for _ in range(2):
        model.add_line()
    path = tmp_path / "mine.csv"
    model.write_csv(path)
    text = path.read_text().splitlines()
    assert text[:2] == ["# 2 FRET line(s)", "# line,sweep,log,components,parameter,tau_F_ns,tau_X_ns,E_FRET"]
    rows = [row.split(",") for row in text[2:]]
    assert len(rows) == 200
    for i, line in enumerate(model.lines):
        a = line_arrays(line["result"])
        block = rows[i * 100 : (i + 1) * 100]
        assert {(r[0], r[1], r[2], r[3]) for r in block} == {
            (line["name"], line["sweep_label"], "False", line["components"].replace(",", ";"))
        }
        values = np.array([[float(v) for v in r[4:]] for r in block])
        for col, key in enumerate(("parameter_values", "tau_f", "tau_x", "e_fret")):
            np.testing.assert_allclose(values[:, col], a[key], rtol=1e-7, err_msg=key)
    assert model.dialog_title == "Saved" and model.dialog_text.startswith("Saved 2 line(s) to:")


def test_a_name_without_csv_gets_the_extension_and_an_unwritable_path_is_reported(model, tmp_path):
    three_lines(model)
    model.write_csv(tmp_path / "x")
    assert (tmp_path / "x.csv").exists()
    with pytest.raises(OSError):
        model.write_csv(tmp_path / "missing" / "x.csv")


def test_push_without_a_host_connection_gives_the_notice_and_with_one_calls_it(model):
    three_lines(model)
    model.push()
    assert (model.dialog_title, model.dialog_text) == ("Push to ndX", NO_NDX_WINDOW)
    model.dialog_ok()
    model.push_callback = lambda _lines: 0  # a connection, but no ndX window open
    model.push()
    assert model.dialog_text == NO_NDX_WINDOW
    sent = []
    wired = FretLineModel(push_callback=sent.append)
    wired.minimum, wired.maximum = 20.0, 120.0
    wired.add_line()
    wired.push()
    assert len(sent) == 1 and sent[0] is wired.lines
    wired.close()


# -- registry, settings, spec, drawing ------------------------------------------------------------------------------------------- #


def test_the_components_are_registered_for_the_global_view_and_dropped_on_close():
    from chisurf.core.registry.parameter_groups import iter_registered_parameter_groups

    m = FretLineModel()
    m.add_component()
    mine = [
        label
        for _, label, _ in iter_registered_parameter_groups()
        if label.startswith("FRET Line C")
    ]
    assert len(mine) == 2
    m.remove_component()
    assert (
        len(
            [
                1
                for _, label, _ in iter_registered_parameter_groups()
                if label.startswith("FRET Line C")
            ]
        )
        == 1
    )
    m.close()
    assert not [
        1 for _, label, _ in iter_registered_parameter_groups() if label.startswith("FRET Line C")
    ]


def test_settings_round_trip_and_invalid_values_are_ignored():
    app = FRETLineApp()
    (
        app.model.minimum,
        app.model.maximum,
        app.model.n_points,
        app.model.log_scale,
        app.model.tau_d0,
    ) = 25.0, 90.0, 50, True, 3.2
    saved = json.loads(json.dumps(app.export_settings()))
    other = FRETLineApp()
    other.restore_settings(saved)
    assert other.export_settings() == saved
    other.restore_settings({"minimum": "x", "n_points": 1, "tau_d0": -3, "log_scale": "yes"})
    assert other.export_settings() == saved
    app.close()
    other.close()


def _walk(sections):
    for s in sections:
        yield s
        yield from _walk(s.get("sections", []))


def test_every_spec_attribute_call_and_action_exists_on_the_model(model):
    spec = json.loads(SPEC.read_text())
    for section in _walk(spec["sections"]):
        opts = section.get("options") or {}
        for attr in (
            section.get("attr"),
            section.get("source"),
            section.get("options_source"),
            opts.get("source"),
            opts.get("selected_call"),
            opts.get("edited_call"),
        ):
            if attr:
                assert hasattr(model, attr), attr
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])) and button.get("description"), button
        assert section.get("description"), section
        for column in opts.get("columns", []):
            assert column.get("tooltip"), column


def test_every_control_has_a_tooltip():
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("fret_line")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("fret_line")
    assert result["ok"], result["output"]


@pytest.mark.parametrize("size", [BIG, SMALL])
def test_draws_empty_and_with_lines_without_clipped_or_overlapping_text(size):
    app = FRETLineApp()
    empty = draw_clip(app, size)
    assert "Add FRET line" in empty.strings
    three_lines(app.model)
    app.model.add_component()
    painter = draw_clip(app, size, frames=4)
    plots = [
        tuple(app.docks.region_boxes[name]) for name in ("efficiency", "lifetime")
    ]  # plots (rotated axis labels)
    assert layout_problems(painter, size, ignore=plots) == []
    assert clipped_texts(painter, ignore=plots) == []
    app.close()


def test_make_app_draws_and_a_second_draw_adds_no_frames_request():
    app = make_app()
    draw(app)
    assert not app.animating()
    app.close()
