"""The native FRET line generator against the Qt tool it replaces: sweep targets, computed lines, the CSV, the collection.

Hermetic: settings, MMFDB and HOME are temporary folders, the CSV goes to ``tmp_path``, no network. The Qt tool is the
committed ``FRETLineTool`` built offscreen (its message boxes and file dialog are replaced so nothing blocks). A module
guard fails the run if anything appears in the real ``~/.chisurf`` other than its ``logs`` folder.
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


def _snapshot(root: Path) -> dict:
    out = {}
    if root.exists():
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root)
            if (rel.parts and rel.parts[0] == "logs") or "__pycache__" in rel.parts:
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


@pytest.fixture
def qt(monkeypatch, tmp_path):
    QtWidgets = pytest.importorskip("qtpy.QtWidgets")
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chisurf.plugins.fret_line.gui import tool as tool_module

    shown = []
    monkeypatch.setattr(
        tool_module.dialogs, "information", lambda parent, title, text: shown.append((title, text))
    )
    monkeypatch.setattr(
        tool_module.dialogs, "warning", lambda parent, title, text: shown.append((title, text))
    )
    tool = tool_module.FRETLineTool()
    tool._shown, tool._tool_module, tool._qapp = shown, tool_module, qapp
    yield tool
    tool.close()


def qt_targets(tool):
    return [
        (tool._sweep_combo.itemData(i) or {}).get("label") for i in range(tool._sweep_combo.count())
    ]


def qt_pick(tool, predicate):
    index = next(
        i for i in range(tool._sweep_combo.count()) if predicate(tool._sweep_combo.itemData(i))
    )
    tool._sweep_combo.setCurrentIndex(index)


# -- the defaults and the mixture --------------------------------------------------------------------------------------- #


def test_defaults_equal_the_qt_tools(model, qt):
    assert (model.minimum, model.maximum, model.n_points, model.tau_d0, model.log_scale) == (
        qt._min_spin.value(),
        qt._max_spin.value(),
        qt._n_pts_spin.value(),
        qt._tau_d0_spin.value(),
        qt._log_check.isChecked(),
    )
    assert model.weight == qt._weight_spin.value() == 1.0
    assert [c["model_name"] for c in model.components] == [qt._components[0]["label"]]
    qt_models = [qt._model_combo.itemText(i) for i in range(qt._model_combo.count())]
    assert set(qt_models) <= set(
        model.model_labels()
    )  # the native list adds the backend's fixed-distance entry


def test_the_component_list_text_and_the_add_remove_rules_equal_the_qt_tools(model, qt):
    for tool_or_model in (qt, model):
        pass
    qt._add_component()
    model.add_component()
    qt_items = [qt._comp_list.item(i).text() for i in range(qt._comp_list.count())]
    rows = model.component_rows()
    assert qt_items == [f"{r['name']}: {r['model']}  (w={r['weight']:g})" for r in rows]
    qt._remove_component()
    model.remove_component()
    qt._remove_component()  # the last one stays
    model.remove_component()
    assert len(qt._components) == len(model.components) == 1 and not model.enabled(
        "remove_component"
    )


def test_a_changed_weight_and_model_follow_the_qt_rules(model, qt):
    qt._weight_spin.setValue(2.5)
    model.weight = 2.5
    assert qt._components[0]["weight"] == model.components[0]["weight"] == 2.5
    qt._model_combo.setCurrentText("Lifetime")
    model.model_label = "Lifetime"
    assert qt._components[0]["label"] == model.components[0]["model_name"] == "Lifetime"
    assert (
        qt._components[0]["weight"] == model.components[0]["weight"] == 2.5
    )  # the weight survives a model change


# -- the sweep targets and the lines --------------------------------------------------------------------------------------- #


@pytest.mark.parametrize("two", [False, True])
@pytest.mark.parametrize("all_parameters", [False, True])
def test_sweep_target_labels_equal_the_qt_tools(model, qt, two, all_parameters):
    if two:
        qt._add_component()
        model.add_component()
    qt._show_all_check.setChecked(all_parameters)
    model.show_all_parameters = all_parameters
    assert model.sweep_labels() == qt_targets(qt)
    if two:
        assert any(label.startswith("fraction") for label in model.sweep_labels())


def test_the_filter_keeps_the_targets_containing_the_text_case_insensitively(model):
    model.sweep_filter = "rda"
    assert model.sweep_labels() and all("rda" in s.casefold() for s in model.sweep_labels())
    model.sweep_filter = "no such target"
    assert model.sweep_labels() == []


def line_arrays(result):
    return {k: np.asarray(result[k]) for k in ("tau_f", "tau_x", "e_fret", "parameter_values")}


def test_the_static_line_equals_the_qt_tools_point_for_point(model, qt):
    qt_pick(qt, lambda d: "distance.mean" in (d or {}).get("name", ""))
    qt._min_spin.setValue(20.0)
    qt._max_spin.setValue(120.0)
    qt._do_compute()
    model.minimum, model.maximum = 20.0, 120.0
    line = model.add_line()
    a, b = line_arrays(line["result"]), line_arrays(qt._lines[0]["result"])
    for key in a:
        np.testing.assert_allclose(a[key], b[key], rtol=1e-12, err_msg=key)
    assert (
        line["sweep_label"] == qt._lines[0]["sweep_label"]
        and line["name"] == "Line 1" == qt._lines[0]["name"]
    )
    assert line["color"] == qt._lines[0]["color"] == PALETTE[0]
    assert line["components"] == qt._lines[0]["components"]
    assert len(a["tau_f"]) == 100


def test_a_log_sweep_and_a_user_tau_d0_equal_the_qt_tools(model, qt):
    qt_pick(qt, lambda d: "distance.mean" in (d or {}).get("name", ""))
    qt._min_spin.setValue(20.0)
    qt._max_spin.setValue(120.0)
    qt._log_check.setChecked(True)
    qt._tau_d0_spin.setValue(3.5)
    qt._n_pts_spin.setValue(40)
    qt._do_compute()
    model.minimum, model.maximum, model.log_scale, model.tau_d0, model.n_points = (
        20.0,
        120.0,
        True,
        3.5,
        40,
    )
    line = model.add_line()
    a, b = line_arrays(line["result"]), line_arrays(qt._lines[0]["result"])
    for key in a:
        np.testing.assert_allclose(a[key], b[key], rtol=1e-12, err_msg=key)
    assert (
        line["log"] is True
        and a["parameter_values"][0] == pytest.approx(20.0)
        and len(a["tau_f"]) == 40
    )


def test_the_dynamic_line_equals_the_qt_tools_from_the_same_start(model, qt):
    for tool_or_model in ("qt", "model"):
        pass
    qt._add_component()
    model.add_component()
    # one component at another distance, the same in both windows
    for comp in (qt._components[1]["model"], model.components[1]["model"]):
        next(p for p in comp.parameters_all if p.canonical_id == "distance.mean.0").value = 70.0
    qt_pick(qt, lambda d: (d or {}).get("kind") == "fraction" and d["component"] == 0)
    qt._min_spin.setValue(0.0)
    qt._max_spin.setValue(1.0)
    qt._do_compute()
    model.sweep_label = next(
        label for label in model.sweep_labels() if label.startswith("fraction · C0")
    )
    model.minimum, model.maximum = 0.0, 1.0
    line = model.add_line()
    a, b = line_arrays(line["result"]), line_arrays(qt._lines[0]["result"])
    for key in a:
        np.testing.assert_allclose(a[key], b[key], rtol=1e-12, err_msg=key)
    assert a["tau_f"].min() < a["tau_f"].max() and "fraction" in line["sweep_label"]


def test_a_sweep_leaves_the_users_parameters_where_they_were(model):
    parameter = next(
        p
        for p in model.components[0]["model"].parameters_all
        if p.canonical_id == "distance.mean.0"
    )
    parameter.value = 55.0
    model.minimum, model.maximum = 20.0, 120.0
    model.add_line()
    assert parameter.value == 55.0  # the Qt tool left the swept parameter at the last sweep value


def test_a_failing_compute_says_why_and_adds_no_line(model, qt):
    qt._log_check.setChecked(True)
    qt._min_spin.setValue(0.0)
    qt._do_compute()
    model.log_scale, model.minimum = True, 0.0
    assert model.add_line() is None and not model.lines and not qt._lines
    assert qt._shown[-1][0] == "Compute error" == model.dialog_title
    assert qt._shown[-1][1] == model.dialog_text and "Log-scale" in model.message


# -- the collection ---------------------------------------------------------------------------------------------------------- #


def three_lines(model):
    model.minimum, model.maximum = 20.0, 120.0
    for _ in range(3):
        model.add_line()


def test_visibility_remove_and_clear_follow_the_qt_rules(model, qt):
    qt_pick(qt, lambda d: "distance.mean" in (d or {}).get("name", ""))
    qt._min_spin.setValue(20.0)
    qt._max_spin.setValue(120.0)
    for _ in range(3):
        qt._do_compute()
    three_lines(model)
    assert [l["color"] for l in model.lines] == [l["color"] for l in qt._lines] == list(PALETTE[:3])
    qt._set_all_visible(False)
    model.hide_all()
    assert [l["visible"] for l in model.lines] == [l["visible"] for l in qt._lines] == [False] * 3
    qt._set_all_visible(True)
    model.show_all()
    assert all(l["visible"] for l in model.lines)
    qt._lines_list.setCurrentRow(1)
    qt._remove_line()
    model.line_index = 1
    model.remove_line()
    assert (
        [l["name"] for l in model.lines] == [l["name"] for l in qt._lines] == ["Line 1", "Line 3"]
    )
    qt._lines.pop()
    model.remove_line()  # nothing selected any more: the last one goes, as in the Qt tool
    model.line_index = -1
    qt._clear_lines()
    model.clear_lines()
    assert model.lines == [] and qt._lines == []
    assert not any(
        model.enabled(a)
        for a in ("save_csv", "push", "show_all", "hide_all", "remove_line", "clear_lines")
    )
    qt._do_compute()
    model.add_line()
    assert qt._lines[0]["name"] == "Line 4" == model.lines[0]["name"]  # the numbering continues


def test_the_csv_is_byte_equal_to_the_qt_writer(model, qt, tmp_path, monkeypatch):
    qt_pick(qt, lambda d: "distance.mean" in (d or {}).get("name", ""))
    qt._min_spin.setValue(20.0)
    qt._max_spin.setValue(120.0)
    qt._add_component()
    model.add_component()
    for _ in range(2):
        qt._do_compute()
    model.minimum, model.maximum = 20.0, 120.0
    for _ in range(2):
        model.add_line()
    qt_path = tmp_path / "qt.csv"
    monkeypatch.setattr(
        qt._tool_module.QtWidgets.QFileDialog, "getSaveFileName", lambda *a, **k: (str(qt_path), "")
    )
    qt._on_save()
    mine = tmp_path / "mine.csv"
    model.write_csv(mine)
    assert mine.read_bytes() == qt_path.read_bytes()
    assert qt._shown[-1][0] == "Saved" == model.dialog_title and model.dialog_text.startswith(
        "Saved 2 line(s) to:"
    )


def test_a_name_without_csv_gets_the_extension_and_an_unwritable_path_is_reported(model, tmp_path):
    three_lines(model)
    model.write_csv(tmp_path / "x")
    assert (tmp_path / "x.csv").exists()
    with pytest.raises(OSError):
        model.write_csv(tmp_path / "missing" / "x.csv")


def test_push_without_a_host_connection_gives_the_notice_and_with_one_calls_it(model, qt):
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

    assert emtk_inventory(build_emtk_app("fret_line"))["controls_without_tooltip"] == []


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
