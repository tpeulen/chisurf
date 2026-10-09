"""The native FCS confocal calculator at parity with the Qt ConfocalCalcWidget.

The Qt widget replays an edit sequence in a subprocess (this process stays Qt-free).
After every step it reports its settings and which fields it leaves editable. The
native app replays the same sequence through the spec's commit path (``setattr``
then the section's ``call``, as a typed value does) and through pointer presses on
its radios, buttons and fold headers.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.fcs.fcs_calculator.gui.app import ConfocalApp
from chisurf.plugins.fcs.fcs_calculator.gui.model import ConfocalModel

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
SPEC = json.loads(
    (HERE.parent / "gui" / "fcs_calculator_emtk.view.json").read_text(encoding="utf-8")
)
DYE = "ATTO 655 (COOH)"
# (step, field or action, value); "fix" picks a constraint, "water" toggles the water model.
STEPS = [
    ("value", "tau_us", 120.0),
    ("value", "conc_nM", 2.0),
    ("value", "num_mols", 5.0),
    ("value", "invN", 0.5),
    ("fix", "rh", None),
    ("value", "rh_nm", 2.0),
    ("fix", "V", None),
    ("value", "veff_fL", 1.0),
    ("value", "S", 4.0),
    ("water", None, False),
    ("value", "eta_mPa_s", 1.2),
    ("value", "temp_C", 30.0),
    ("dye", True, None),
    ("dye", False, None),
    ("shape", "Ellipsoid", (4.0, 3.0)),
    ("shape", "Cylinder", (4.0, 3.0)),
    ("shape", "Sphere", (6.0, 3.0)),
    ("water", None, True),
]

_QT = r"""
import json, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.fcs.fcs_calculator.wizard import ConfocalCalcWidget
w = ConfocalCalcWidget()
steps, dye = json.loads(sys.argv[1]), sys.argv[2]
def editable():
    return {"D_um2_s": not w.D_um2_s.isReadOnly(), "rh_nm": not w.rh_nm.isReadOnly(),
            "veff_fL": not w.veff_fL.isReadOnly(), "eta_mPa_s": w.eta_mPa_s.isEnabled(),
            "shape_aspect": w.shape_aspect.isEnabled()}
facts = [{"settings": w._collect_settings(), "editable": editable(), "dyes": [w.dye_combo.itemText(i) for i in range(w.dye_combo.count())]}]
for kind, a, b in steps:
    if kind == "value":
        getattr(w, a).setValue(b)
    elif kind == "fix":
        {"D": w.rb_fix_D, "rh": w.rb_fix_rh, "V": w.rb_fix_V}[a].setChecked(True)
    elif kind == "water":
        w.use_water_eta.setChecked(b)
    elif kind == "dye":
        w.dye_combo.setCurrentText(dye)
        (w.scale_dref if a else w.scale_dref_none).setChecked(True)
        w.btn_apply_dref.click()
    elif kind == "shape":
        w.shape_combo.setCurrentText(a)
        w.shape_size_nm.setValue(b[0]); w.shape_aspect.setValue(b[1])
        w.btn_apply_shape.click()
    facts.append({"settings": w._collect_settings(), "editable": editable()})
data = dict(facts[-1]["settings"], fix_mode="rh", dye="Rhodamine 6G (Rh6G)", shape_type="Hexagon", tau_us=95.0)
w._apply_settings(data)
print("FACTS" + json.dumps({"steps": facts, "imported": w._collect_settings()}))
"""


@pytest.fixture(scope="module")
def qt():
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run(
        [sys.executable, "-c", _QT, json.dumps(STEPS), DYE],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        cwd=str(REPO),
    )
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None and (
        "No module named" in proc.stderr or "could not connect to display" in proc.stderr
    ):
        pytest.skip(f"no Qt here: {proc.stderr[-400:]}")
    # Any other failure is the Qt widget's own: skipping it hid a broken Qt host.
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    return json.loads(line[len("FACTS") :])


def _sections(sections=SPEC["sections"]):
    for section in sections:
        yield section
        yield from _sections(section.get("sections") or [])


DECIMALS = {s["attr"]: s.get("decimals", 6) for s in _sections() if s.get("type") == "value"}


def _commit(model, attr, value):
    """What the form does with a typed value: ``setattr``, then the section's ``call``."""
    section = next(s for s in _sections() if s.get("attr") == attr)
    setattr(model, attr, value)
    if section.get("call"):
        getattr(model, section["call"])(value)


def _draw(app, size=(1200, 800), n=2):
    painter = None
    for _ in range(n):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def _click(app, key, size=(1200, 800)):
    _draw(app, size)
    x, y, w, h = app.item_rects[key]
    app.pointer_move(x + w / 2, y + h / 2)
    app.press(x + w / 2, y + h / 2)
    _draw(app, size, n=1)
    app.release()
    _draw(app, size, n=1)


def _same(native, qt_settings):
    """The Qt spin boxes keep a value at their decimals and recompute from it; allow that rounding."""
    for key, value in qt_settings.items():
        mine = native[key]
        if isinstance(value, float):
            tolerance = 1.5 * 10 ** -DECIMALS.get(key, 6) + 2e-4 * abs(value)
            assert mine == pytest.approx(value, abs=tolerance), key
        else:
            assert mine == value, key


def _replay(model):
    """STEPS through the model alone (no pointer)."""
    for kind, a, b in STEPS:
        if kind == "value":
            _commit(model, a, b)
        elif kind == "fix":
            _commit(model, "constraint", a)
        elif kind == "water":
            _commit(model, "use_water_eta", b)
        elif kind == "dye":
            model.dye, model.scale_dref = DYE, a
            model.apply_dye()
        elif kind == "shape":
            model.shape_type = a
            _commit(model, "shape_size_nm", b[0])
            _commit(model, "shape_aspect", b[1])
            model.apply_shape()


def _editable(model):
    return {
        name: model.enabled(name)
        for name in ("D_um2_s", "rh_nm", "veff_fL", "eta_mPa_s", "shape_aspect")
    }


# 1. every step of the Qt widget's edit sequence: the same numbers and the same editable fields
def test_the_edit_sequence_matches_the_qt_widget(qt):
    app = ConfocalApp()
    m = app.model
    try:
        assert m.dye_names() == qt["steps"][0]["dyes"]
        _same(m.settings(), qt["steps"][0]["settings"])
        assert _editable(m) == qt["steps"][0]["editable"]
        for (kind, a, b), expected in zip(STEPS, qt["steps"][1:]):
            if kind == "value":
                _commit(m, a, b)
            elif kind == "fix":
                _click(app, f"constraint.{['D', 'rh', 'V'].index(a)}")  # the radio itself
            elif kind == "water":
                if m.use_water_eta != b:
                    _click(app, "use_water_eta")
            elif kind == "dye":
                m.dye = DYE
                _click(app, f"scale_dref.{0 if a else 1}")
                _click(app, "apply_dye")
            elif kind == "shape":
                app.form.folds["Molecular shape"] = True
                m.shape_type = a
                _commit(m, "shape_size_nm", b[0])
                _commit(m, "shape_aspect", b[1])
                _click(app, "apply_shape")
            _same(m.settings(), expected["settings"])
            assert _editable(m) == expected["editable"], (kind, a)
    finally:
        app.close()


# 2. settings: the Qt keys; an import applies known entries, resolves aliases, ignores the rest
def test_settings_round_trip_and_tolerant_import(qt, tmp_path):
    m = ConfocalModel()
    assert set(m.settings()) == set(qt["steps"][0]["settings"])
    for kind, a, b in STEPS[:8]:
        if kind == "value":
            _commit(m, a, b)
        elif kind == "fix":
            m.constraint = a
            m.recompute()
    path = m.export_json(tmp_path / "calc.json")
    assert json.loads(path.read_text()) == m.settings()
    restored = ConfocalModel()
    restored.import_json(path)
    assert restored.settings().keys() == m.settings().keys()
    _same(restored.settings(), m.settings())
    # The Qt widget recomputes an import from whichever occupancy field was typed last (hidden
    # state), so the import is compared after the same history.
    other = ConfocalModel()
    _replay(other)
    other.apply_settings(
        dict(
            qt["steps"][-1]["settings"],
            fix_mode="rh",
            dye="Rhodamine 6G (Rh6G)",
            shape_type="Hexagon",
            tau_us=95.0,
        )
    )
    _same(other.settings(), qt["imported"])


# 3. the dialogs: export and import through the buttons; failures are reported, not swallowed
def test_export_and_import_through_the_dialogs(tmp_path):
    app = ConfocalApp()
    try:
        app.form.folds["Settings JSON"] = True
        _click(app, "export_json")
        assert app.dialog is not None and app.dialog.mode == "save"
        app.file_chosen(str(tmp_path / "out.json"))
        assert app.dialog is None and (tmp_path / "out.json").exists() and not app.model.error
        _commit(app.model, "tau_us", 300.0)
        _click(app, "import_json")
        assert app.dialog.mode == "open"
        app.file_chosen(str(tmp_path / "out.json"))
        assert app.model.tau_us == pytest.approx(70.0)
        (tmp_path / "bad.json").write_text("[1, 2]")
        app.files_dropped([str(tmp_path / "bad.json")])
        assert "failed" in app.model.error
        assert any("failed" in s for s in _draw(app).strings)
        assert not app.files_dropped([str(tmp_path / "a.txt")])  # only settings files
    finally:
        app.close()


def test_a_reference_without_d_is_refused():
    m = ConfocalModel()
    before = m.D_um2_s
    m.dye = "no such dye"
    assert not m.enabled("apply_dye") and not m.apply_dye()
    assert m.error and m.D_um2_s == before


# 4. computed fields cannot be typed into: the form leaves them disabled
def test_computed_fields_are_not_editable_in_the_form():
    app = ConfocalApp()
    try:
        _draw(app)
        before = app.model.rh_nm
        x, y, w, h = app.item_rects["rh_nm"]
        app.pointer_move(x + w / 2, y + h / 2)
        app.press(x + w / 2, y + h / 2)
        _draw(app, n=1)
        app.release()
        app.key(0, "9")
        app.key(257, "")  # Enter
        _draw(app)
        assert app.model.rh_nm == before
    finally:
        app.close()


# 5. guide: every target drawn; the tau step waits for an edit of tau
def test_the_guide_points_at_real_controls_and_waits():
    app = ConfocalApp()
    try:
        app.form.folds["Molecular shape"] = False
        _draw(app)
        steps = app.tour.steps
        keys = {app.tour._target_key(s.get("target")) for s in steps} - {""}
        assert all(app.target_rect(key) is not None for key in keys), keys
        index = next(i for i, s in enumerate(steps) if s.get("await"))
        app.tour.start(index)
        assert app.tour.awaiting
        _commit(app.model, "temp_C", 21.0)
        app.form.used("temp_C")
        assert app.tour.awaiting  # not tau
        app.form.used("tau_us")
        assert not app.tour.awaiting
    finally:
        app.tour.active = False
        app.close()


def test_guide_and_help_buttons():
    app = ConfocalApp()
    try:
        _click(app, "help")
        assert app.help_window.open
        app.help_window.open = False
        _click(app, "guide")
        assert app.tour.active
    finally:
        app.close()


# 6. draws at both sizes with every panel open; nothing leaves the window
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_with_every_panel_open(size):
    app = ConfocalApp()
    try:
        app.form.folds.update({"Molecular shape": True, "Settings JSON": True})
        strings = _draw(app, size).strings
        for text in (
            "Fix D",
            "Fix rₕ",
            "Fix Veff",
            "Apply Dref",
            "Apply shape→D",
            "Export JSON",
            "Import JSON",
            "Apply with Temp/η scaling",
            "\U0001f4d6 Guide",
            "❓ Help",
        ):
            assert text in strings, text
        for name in (
            "guide",
            "help",
            "constraint",
            "tau_us",
            "S",
            "conc_nM",
            "apply_dye",
            "apply_shape",
            "import_json",
        ):
            x, y, w, h = app.item_rects[name]
            assert x >= -0.5 and x + w <= size[0] + 0.5 and y + h <= size[1] + 0.5, name
    finally:
        app.close()


# 7. no Qt, tooltips (inventory and the spec)
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("fcs_calculator")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("fcs_calculator")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
    buttons = [b for s in _sections() for b in s.get("buttons") or []]
    assert all(s.get("description") for s in _sections()) and all(
        b.get("description") for b in buttons
    )
