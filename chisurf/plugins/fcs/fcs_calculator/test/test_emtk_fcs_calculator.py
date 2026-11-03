"""The native FCS confocal calculator: an edit sequence checked against the confocal physics.

The app replays an edit sequence through the spec's commit path (``setattr`` then the
section's ``call``, as a typed value does) and through pointer presses on its radios,
buttons and fold headers. After every step the linked quantities must satisfy the
relations of a 3D-Gaussian focus, recomputed here independently of the engine:
``w0² = 4 D tau``, ``Veff = pi^(3/2) w0³ S``, ``N = c Veff NA``, ``1/N`` and
Stokes-Einstein ``rh = kT / (6 pi eta D)``; the constraint decides which field is typed.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.emtk_layout import action_caption
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


KB, NA = 1.380649e-23, 6.02214076e23


def _close(a, b, rel=2e-4, decimals=6):
    return a == pytest.approx(b, rel=rel, abs=1.5 * 10**-decimals)


def _physics_holds(s):
    """The settings obey the focus and Stokes-Einstein relations (to the fields' decimals)."""
    w0_m = math.sqrt(4.0 * s["D_um2_s"] * 1e-12 * s["tau_us"] * 1e-6)
    veff_fL = math.pi**1.5 * (w0_m * 1e6) ** 3 * s["S"]
    assert _close(s["veff_fL"], veff_fL, decimals=DECIMALS.get("veff_fL", 6)), (s, veff_fL)
    n = s["conc_nM"] * 1e-9 * s["veff_fL"] * 1e-15 * NA
    assert _close(s["num_mols"], n, rel=2e-3, decimals=DECIMALS.get("num_mols", 6)), (s, n)
    assert _close(s["invN"], 1.0 / s["num_mols"], rel=2e-3), s
    rh_nm = KB * (s["temp_C"] + 273.15) / (6 * math.pi * s["eta_mPa_s"] * 1e-3 * s["D_um2_s"] * 1e-12) * 1e9
    assert _close(s["rh_nm"], rh_nm, rel=2e-3, decimals=DECIMALS.get("rh_nm", 6)), (s, rh_nm)


def _expected_editable(s):
    typed = {"D": "D_um2_s", "rh": "rh_nm", "V": "veff_fL"}[s["fix_mode"]]
    return {
        "D_um2_s": typed == "D_um2_s",
        "rh_nm": typed == "rh_nm",
        "veff_fL": typed == "veff_fL",
        "eta_mPa_s": not s["use_water_eta"],
        "shape_aspect": s["shape_type"] != "Sphere",
    }


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


# 1. every step of an edit sequence: the typed value lands, the linked ones follow the physics,
# the constraint decides which fields are editable
def test_the_edit_sequence_obeys_the_confocal_physics():
    from chisurf.core.fluorescence.dyes import get_dye

    app = ConfocalApp()
    m = app.model
    try:
        assert DYE in m.dye_names()
        s = m.settings()
        assert s["fix_mode"] == "D" and s["tau_us"] == 70.0 and s["D_um2_s"] == 400.0
        _physics_holds(s)
        assert _editable(m) == _expected_editable(s)
        for kind, a, b in STEPS:
            if kind == "value":
                _commit(m, a, b)
                if m.enabled(a) or a in ("tau_us", "S", "temp_C", "conc_nM"):
                    assert getattr(m, a) == pytest.approx(b), a
            elif kind == "fix":
                _click(app, f"constraint.{['D', 'rh', 'V'].index(a)}")  # the radio itself
                assert m.constraint == a
            elif kind == "water":
                if m.use_water_eta != b:
                    _click(app, "use_water_eta")
                assert m.use_water_eta == b
            elif kind == "dye":
                m.dye = DYE
                _click(app, f"scale_dref.{0 if a else 1}")
                _click(app, "apply_dye")
                assert m.constraint == "D"
                if not a:  # unscaled: the table's D at 25 C, as listed
                    assert m.D_um2_s == pytest.approx(get_dye(DYE)["d25_um2_s"])
            elif kind == "shape":
                app.form.folds["Molecular shape"] = True
                m.shape_type = a
                _commit(m, "shape_size_nm", b[0])
                _commit(m, "shape_aspect", b[1])
                _click(app, "apply_shape")
                assert m.constraint == "D" and not m.error
                if a == "Sphere":  # Stokes-Einstein with the radius half the size
                    eta = m.eta_mPa_s * 1e-3
                    d = KB * (m.temp_C + 273.15) / (6 * math.pi * eta * b[0] / 2 * 1e-9) * 1e12
                    assert m.D_um2_s == pytest.approx(d, rel=1e-3)
            s = m.settings()
            _physics_holds(s)
            assert _editable(m) == _expected_editable(s), (kind, a)
    finally:
        app.close()


SETTINGS_KEYS = {
    "tau_us", "D_um2_s", "rh_nm", "S", "veff_fL", "temp_C", "eta_mPa_s", "conc_nM", "num_mols",
    "invN", "use_water_eta", "fix_mode", "dye", "scale_dref", "shape_type", "shape_size_nm",
    "shape_aspect",
}


# 2. settings: a fixed key set; an import applies known entries, resolves aliases, ignores the rest
def test_settings_round_trip_and_tolerant_import(tmp_path):
    m = ConfocalModel()
    assert set(m.settings()) == SETTINGS_KEYS
    for kind, a, b in STEPS[:8]:
        if kind == "value":
            _commit(m, a, b)
        elif kind == "fix":
            m.constraint = a
            m.recompute()
    path = m.export_json(tmp_path / "calc.json")
    # The settings, plus the schema that makes the file a workspace setup of this tool.
    from chisurf.plugins.fcs.fcs_calculator.gui.model import SETTINGS_SCHEMA

    assert json.loads(path.read_text()) == {"schema": SETTINGS_SCHEMA, **m.settings()}
    restored = ConfocalModel()
    restored.import_json(path)
    assert restored.settings().keys() == m.settings().keys()
    for key, value in m.settings().items():
        assert restored.settings()[key] == pytest.approx(value, rel=1e-6) if isinstance(
            value, float
        ) else restored.settings()[key] == value, key
    other = ConfocalModel()
    _replay(other)
    before = other.settings()
    other.apply_settings(
        dict(
            before,
            fix_mode="rh",
            dye="Rhodamine 6G (Rh6G)",  # an alias of a listed species
            shape_type="Hexagon",  # not a shape: ignored
            tau_us=95.0,
            unknown_key=1.0,  # ignored
        )
    )
    s = other.settings()
    assert s["fix_mode"] == "rh" and s["dye"] == "Rhodamine 6G"
    assert s["shape_type"] == before["shape_type"] and s["tau_us"] == 95.0
    assert s["rh_nm"] == pytest.approx(before["rh_nm"])  # the constrained field is kept
    assert "unknown_key" not in s
    _physics_holds(s)


# 3. export through its save dialog; settings come back through the workspace (a setup row);
# failures are reported, not swallowed
def test_export_and_import_through_the_workspace(tmp_path):
    from chisurf.core.fio.classify import classify
    from chisurf.core.plugin.workspace_input import register_result
    from chisurf.plugins.fcs.fcs_calculator.gui.app import receive_settings

    app = ConfocalApp()
    try:
        app.form.folds["Settings JSON"] = True
        _click(app, "export_json")
        assert app.dialog is not None and app.dialog.mode == "save"
        out = tmp_path / "out.json"
        app.file_chosen(str(out))
        assert app.dialog is None and out.exists() and not app.model.error
        assert classify(out) == "setup"  # a drop puts the exported settings in the workspace
        _commit(app.model, "tau_us", 300.0)
        register_result(str(out), kind="setup")
        named = app.workspace_input
        rows = [r for r in named.workspace_input_rows() if r.get("address") == str(out)]
        assert rows, "the exported settings are offered by the Input section"
        named.workspace_input_selected(rows[-1])
        assert app.model.tau_us == pytest.approx(70.0) and not app.model.error
        (tmp_path / "bad.json").write_text("[1, 2]")
        assert not receive_settings(app, {"settings": str(tmp_path / "bad.json")})
        assert "failed" in app.model.error
        assert any("failed" in s for s in _draw(app).strings)
        assert not hasattr(app, "files_dropped")  # files enter through the workspace only
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
            "Apply with Temp/η scaling",
            action_caption("guide"),
            action_caption("help"),
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
